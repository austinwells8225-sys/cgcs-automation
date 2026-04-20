"""Smartsheet inbox poller — Gmail → agent → draft.

Scans admin@cgcs-acc.org's inbox for unread Smartsheet event notifications,
runs them through the existing intake graph, and saves the agent's drafted
reply as a Gmail Draft threaded to the original email. Marks originals as
read so we don't reprocess.

Runs on a schedule (see scheduler). Purely additive — does not send
anything, only drafts. Human review happens in Gmail.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.services import gmail_service
from app.services.smartsheet_parser import is_smartsheet_intake, parse_smartsheet_intake

logger = logging.getLogger(__name__)

# Gmail search query: unread Smartsheet event notifications.
# Uses the subject prefix and Smartsheet sender domain as filter criteria.
SMARTSHEET_QUERY = (
    'is:unread '
    'from:@app.smartsheet.com '
    'subject:"Notice of Event Space Request"'
)


async def poll_smartsheet_inbox(compiled_graph, max_emails: int = 10) -> dict:
    """Scan inbox for Smartsheet notifications, draft replies, mark read.

    Args:
        compiled_graph: the compiled LangGraph agent graph (shared with the
            FastAPI app). Passed in to avoid rebuilding on every poll.
        max_emails: safety cap per poll — no more than N emails per run.

    Returns:
        {
            "checked": int,          # total emails matched
            "processed": int,        # successfully drafted
            "skipped": int,          # not a valid Smartsheet email
            "errors": list[dict],    # failures with email_id + reason
        }
    """
    results = {
        "checked": 0,
        "processed": 0,
        "skipped": 0,
        "errors": [],
    }

    try:
        emails = await gmail_service.read_inbox(
            query=SMARTSHEET_QUERY,
            max_results=max_emails,
        )
    except Exception as e:
        logger.exception("Failed to read Smartsheet inbox")
        results["errors"].append({"email_id": None, "reason": f"read_inbox failed: {e}"})
        return results

    results["checked"] = len(emails)
    if not emails:
        return results

    for email in emails:
        email_id = email.get("id") or email.get("message_id") or ""
        thread_id = email.get("thread_id") or ""
        subject = email.get("subject") or ""
        body = email.get("body_text") or ""
        from_addr = email.get("from") or ""

        try:
            # Belt-and-suspenders: the Gmail query filter already restricts
            # to Smartsheet senders + subject, but double-check with the
            # parser's own detector so we don't try to draft off a spoofed
            # or malformed one.
            if not is_smartsheet_intake(subject, from_addr):
                logger.info("Skipping email %s — not a valid Smartsheet email", email_id)
                results["skipped"] += 1
                await _mark_safely(email_id)
                continue

            draft_id = await _process_one(
                compiled_graph=compiled_graph,
                email_id=email_id,
                thread_id=thread_id,
                subject=subject,
                body=body,
                from_addr=from_addr,
            )
            if draft_id:
                results["processed"] += 1
                await _mark_safely(email_id)
            else:
                results["errors"].append({
                    "email_id": email_id,
                    "reason": "graph returned no draft",
                })

        except Exception as e:
            logger.exception("Failed to process Smartsheet email %s", email_id)
            results["errors"].append({"email_id": email_id, "reason": str(e)})

    logger.info(
        "Smartsheet inbox poll complete: checked=%d processed=%d skipped=%d errors=%d",
        results["checked"], results["processed"], results["skipped"], len(results["errors"]),
    )
    return results


async def _process_one(
    compiled_graph,
    email_id: str,
    thread_id: str,
    subject: str,
    body: str,
    from_addr: str,
) -> Optional[str]:
    """Run one Smartsheet email through the graph, save the drafted reply.

    Returns the Gmail draft ID on success, None on failure.
    """
    request_id = f"smartsheet-{uuid.uuid4().hex[:12]}"
    logger.info("Processing Smartsheet email %s (request_id=%s)", email_id, request_id)

    # Parse once here so we can pull the requestor email for the draft's
    # To: field. The graph will typically re-parse as part of its flow.
    parsed = parse_smartsheet_intake(subject, body)
    to_addr = (parsed or {}).get("requestor_email") or from_addr

    initial_state = {
        "task_type": "smartsheet_intake",
        "request_id": request_id,
        "email_id": email_id,
        "email_subject": subject,
        "email_body": body,
        "email_from": from_addr,
        "smartsheet_parsed": parsed or {},
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config={
                "configurable": {"thread_id": request_id},
                "recursion_limit": 50,
            },
        )
    except Exception:
        logger.exception("Graph invocation failed for %s", request_id)
        return None

    draft_body = result.get("draft_response") or ""
    if not draft_body:
        logger.warning("Graph produced no draft_response for %s", request_id)
        return None

    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"

    try:
        draft_result = await gmail_service.create_draft_reply(
            thread_id=thread_id,
            to=to_addr,
            subject=reply_subject,
            body=draft_body,
        )
        draft_id = draft_result.get("draft_id", "")
        logger.info(
            "Created Gmail draft %s for request %s (thread=%s)",
            draft_id, request_id, thread_id,
        )
        return draft_id
    except Exception:
        logger.exception("Failed to create Gmail draft for %s", request_id)
        return None


async def _mark_safely(email_id: str) -> None:
    """Mark email as read, swallow errors (non-fatal)."""
    if not email_id:
        return
    try:
        await gmail_service.mark_as_read(email_id)
    except Exception:
        logger.exception("Failed to mark email %s as read (non-fatal)", email_id)
