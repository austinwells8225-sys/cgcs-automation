"""Smartsheet intake graph nodes — classify parsed intake and draft responses."""

from __future__ import annotations

import logging

from app.graph.state import AgentState
from app.services.google_calendar import create_hold
from app.services.google_sheets import append_row
from app.services.intake_classifier import (
    classify_request,
    draft_furniture_email,
    draft_intake_response,
    draft_police_email,
)
from app.services.intake_processor import build_calendar_hold, build_pet_row

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


def create_hold_from_intake(state: AgentState) -> dict:
    """Create a Google Calendar HOLD event from parsed Smartsheet intake.

    Failures do not abort the flow — drafting proceeds regardless because the
    edge out of this node is unconditional.
    """
    parsed = state.get("smartsheet_parsed", {})
    if not parsed:
        logger.warning("No parsed intake data for hold creation; skipping")
        return {}

    hold = build_calendar_hold(parsed)

    if not (hold["title"] and hold["start_date"] and hold["start_time"] and hold["end_time"]):
        logger.warning(
            "Missing required fields for hold creation (event=%s); skipping",
            parsed.get("event_code", "unknown"),
        )
        return {}

    try:
        result = create_hold(
            title=hold["title"],
            date=hold["start_date"],
            start_time=hold["start_time"],
            end_time=hold["end_time"],
            description=hold["description"],
        )
    except Exception as e:
        logger.error(
            "Calendar hold creation failed for %s: %s",
            parsed.get("event_code", "unknown"),
            e,
        )
        return {
            "errors": state.get("errors", []) + [f"Calendar hold creation failed: {e}"],
        }

    logger.info(
        "Calendar hold created for %s: event_id=%s",
        parsed.get("event_code", "unknown"),
        result.get("event_id"),
    )
    return {
        "hold_event_id": result.get("event_id"),
        "hold_html_link": result.get("html_link"),
    }


def write_pet_row_from_intake(state: AgentState) -> dict:
    """Append a row to the P.E.T. tracker spreadsheet from parsed Smartsheet intake.

    Failures do not abort the flow — drafting proceeds regardless because the
    edge out of this node is unconditional.
    """
    parsed = state.get("smartsheet_parsed", {})
    if not parsed:
        logger.warning("No parsed intake data for P.E.T. row write; skipping")
        return {}

    row = build_pet_row(parsed)

    try:
        result = append_row(row)
    except Exception as e:
        logger.error(
            "P.E.T. row write failed for %s: %s",
            parsed.get("event_code", "unknown"),
            e,
        )
        return {
            "errors": state.get("errors", []) + [f"P.E.T. row write failed: {e}"],
        }

    logger.info(
        "P.E.T. row written for %s: range=%s rows=%s",
        parsed.get("event_code", "unknown"),
        result.get("updated_range"),
        result.get("updated_rows"),
    )
    return {"pet_row_written": True}


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
