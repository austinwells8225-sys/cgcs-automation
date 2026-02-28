"""Email triage nodes — classify incoming emails, draft replies, check auto-send."""

import json
import logging

from app.config import settings
from app.graph.nodes.shared import (
    _invoke_with_retry,
    _parse_json_response,
    _sanitize_string,
)
from app.graph.state import AgentState
from app.prompts.templates import EMAIL_TRIAGE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

AUTO_SEND_ALLOWLIST = {
    "stefano.casafrancalaos@austincc.edu",
    "marisela.perez@austincc.edu",
}


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
        return {
            "email_priority": result.get("priority", "medium"),
            "email_category": result.get("category", "other"),
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
