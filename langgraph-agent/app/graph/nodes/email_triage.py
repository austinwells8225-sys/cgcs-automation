"""Email triage nodes — classify incoming emails, draft replies, check auto-send."""

from __future__ import annotations

import json
import logging

from app.config import settings
from app.cgcs_constants import (
    AUTO_SEND_ALLOWLIST,
    is_adastra_email,
    is_vip_sender,
)
from app.graph.nodes.shared import (
    _invoke_with_retry,
    _parse_json_response,
    _sanitize_string,
)
from app.graph.state import AgentState
from app.prompts.templates import EMAIL_TRIAGE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _detect_calendar_invite(subject: str, body: str) -> bool:
    """Detect if an email is a calendar invite based on common markers."""
    markers = [".ics", "text/calendar", "BEGIN:VCALENDAR", "VEVENT"]
    combined = (subject + " " + body).lower()
    return any(m.lower() in combined for m in markers)


def classify_email(state: AgentState) -> dict:
    """Classify an incoming email by priority and category."""
    email_from = _sanitize_string(state.get("email_from", ""))
    email_subject = _sanitize_string(state.get("email_subject", ""))
    email_body = _sanitize_string(state.get("email_body", ""))

    if not email_body and not email_subject:
        return {
            "errors": state.get("errors", []) + ["Email has no subject or body"],
            "decision": "needs_review",
        }

    # --- Ad Astra auto-classification ---
    if is_adastra_email(email_from):
        logger.info("Ad Astra email detected from %s", email_from)
        # Only surface if subject contains "has been approved"
        if "has been approved" in email_subject.lower():
            return {
                "email_priority": "medium",
                "email_category": "aais_receipt",
            }
        # Otherwise mark read and don't process further
        return {
            "email_priority": "low",
            "email_category": "aais_receipt",
            "decision": "approve",
            "draft_response": "Ad Astra receipt — auto-classified, marked read.",
            "email_auto_send": False,
        }

    # --- Calendar invite detection ---
    if _detect_calendar_invite(email_subject, email_body):
        logger.info("Calendar invite detected — leaving for manual handling")
        return {
            "email_priority": "low",
            "email_category": "calendar_invite",
            "decision": "approve",
            "draft_response": "Calendar invite detected — left for Austin to handle manually.",
            "email_auto_send": False,
        }

    # --- Standard LLM classification ---
    user_message = (
        f"From: {email_from}\n"
        f"Subject: {email_subject}\n\n"
        f"Body:\n{email_body}"
    )

    try:
        content = _invoke_with_retry([
            {"role": "system", "content": EMAIL_TRIAGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ])
        result = _parse_json_response(content)
        priority = result.get("priority", "medium")
        category = result.get("category", "other")

        # VIP priority boost
        if is_vip_sender(email_from, email_subject):
            priority = "high"
            logger.info("VIP sender detected: %s — boosting to high priority", email_from)

        return {
            "email_priority": priority,
            "email_category": category,
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse email classification: %s", e)
        return {
            "email_priority": "medium",
            "email_category": "other",
            "errors": state.get("errors", []) + ["Email classification parse failed"],
            "decision": "needs_review",
        }
    except Exception as e:
        logger.error("Email classification failed: %s", e)
        return {
            "email_priority": "medium",
            "email_category": "other",
            "errors": state.get("errors", []) + [f"Email classification LLM failed: {e}"],
            "decision": "needs_review",
        }


def draft_email_reply(state: AgentState) -> dict:
    """Draft a reply to the classified email."""
    email_from = _sanitize_string(state.get("email_from", ""))
    email_subject = _sanitize_string(state.get("email_subject", ""))
    email_body = _sanitize_string(state.get("email_body", ""))
    category = state.get("email_category", "other")
    priority = state.get("email_priority", "medium")

    user_message = (
        f"From: {email_from}\n"
        f"Subject: {email_subject}\n"
        f"Category: {category}\n"
        f"Priority: {priority}\n\n"
        f"Original email body:\n{email_body}\n\n"
        f"Draft a professional reply on behalf of CGCS at Austin Community College."
    )

    try:
        content = _invoke_with_retry([
            {"role": "system", "content": EMAIL_TRIAGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ])
        return {
            "email_draft_reply": content,
            "draft_response": content,
            "requires_approval": True,
        }
    except Exception as e:
        logger.error("Email reply drafting failed: %s", e)
        return {
            "email_draft_reply": None,
            "draft_response": None,
            "decision": "needs_review",
            "errors": state.get("errors", []) + [f"Email reply LLM failed: {e}"],
        }


def check_auto_send(state: AgentState) -> dict:
    """Check if the email reply can be auto-sent based on the allowlist."""
    email_from = (state.get("email_from") or "").strip().lower()
    category = state.get("email_category", "")

    # Never auto-send for calendar invites or aais_receipt
    if category in ("calendar_invite", "aais_receipt"):
        return {
            "email_auto_send": False,
            "approved": True,
            "decision": "approve",
        }

    if email_from in AUTO_SEND_ALLOWLIST:
        logger.info("Auto-send approved for allowlisted sender: %s", email_from)
        return {
            "email_auto_send": True,
            "approved": True,
            "decision": "approve",
        }

    logger.info("Email reply requires admin approval (sender: %s)", email_from)
    return {
        "email_auto_send": False,
        "approved": False,
        "requires_approval": True,
        "decision": "needs_review",
    }
