"""Smartsheet intake graph nodes — classify parsed intake and draft responses."""

from __future__ import annotations

import logging

from app.graph.state import AgentState
from app.services.intake_classifier import (
    classify_request,
    draft_furniture_email,
    draft_intake_response,
    draft_police_email,
)

logger = logging.getLogger(__name__)


def classify_intake_request(state: AgentState) -> dict:
    """Classify a parsed Smartsheet intake as easy/mid/hard."""
    parsed = state.get("smartsheet_parsed", {})

    if not parsed:
        return {
            "errors": state.get("errors", []) + ["No parsed intake data to classify"],
            "decision": "needs_review",
        }

    classification = classify_request(parsed)

    logger.info(
        "Intake %s classified as %s (confidence: %.2f): %s",
        parsed.get("event_code", "unknown"),
        classification["difficulty"],
        classification["confidence"],
        classification["reasoning"],
    )

    return {
        "intake_classification": classification,
        "intake_difficulty": classification["difficulty"],
    }


def draft_intake_emails(state: AgentState) -> dict:
    """Draft the response email, plus furniture/police emails if needed."""
    parsed = state.get("smartsheet_parsed", {})
    classification = state.get("intake_classification", {})

    if not parsed:
        return {
            "errors": state.get("errors", []) + ["No parsed intake data for drafting"],
            "decision": "needs_review",
        }

    # Main response
    response = draft_intake_response(parsed, classification)

    # Coordination emails
    furniture_email = draft_furniture_email(parsed)
    police_email = draft_police_email(parsed)

    draft_emails = [response]
    if furniture_email:
        draft_emails.append(furniture_email)
        logger.info("Furniture email drafted for %s", parsed.get("event_name"))
    if police_email:
        draft_emails.append(police_email)
        logger.info("Police email drafted for %s", parsed.get("event_name"))

    auto_send = response.get("auto_send", False)

    return {
        "draft_response": response["body"],
        "intake_draft_emails": draft_emails,
        "email_auto_send": auto_send,
        "decision": "approve" if auto_send else "needs_review",
    }
