"""Calendar hold nodes — validate and create calendar holds."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from app.cgcs_constants import build_calendar_description, build_calendar_title
from app.graph.nodes.shared import _sanitize_string
from app.graph.state import AgentState
from app.services.google_calendar import create_hold

logger = logging.getLogger(__name__)


def validate_hold_request(state: AgentState) -> dict:
    """Validate the calendar hold request fields."""
    errors: list[str] = []

    org_name = state.get("hold_org_name")
    hold_date = state.get("hold_date")
    start_time = state.get("hold_start_time")
    end_time = state.get("hold_end_time")

    if not org_name:
        errors.append("Missing required field: hold_org_name")
    if not hold_date:
        errors.append("Missing required field: hold_date")
    if not start_time:
        errors.append("Missing required field: hold_start_time")
    if not end_time:
        errors.append("Missing required field: hold_end_time")

    # Date format
    if hold_date:
        try:
            datetime.strptime(hold_date, "%Y-%m-%d")
        except ValueError:
            errors.append("Invalid hold_date format. Expected YYYY-MM-DD.")

    # Time format
    for field, val in [("hold_start_time", start_time), ("hold_end_time", end_time)]:
        if val and not re.match(r"^\d{2}:\d{2}$", val):
            errors.append(f"Invalid time format for {field}. Expected HH:MM.")

    # Start before end
    if start_time and end_time and start_time >= end_time:
        errors.append("Hold start time must be before end time.")

    sanitized = {}
    if org_name:
        sanitized["hold_org_name"] = _sanitize_string(org_name)

    return {**sanitized, "errors": errors}


def create_calendar_hold(state: AgentState) -> dict:
    """Create a hold event on Google Calendar."""
    if state.get("errors"):
        return {"decision": "needs_review"}

    org_name = state.get("hold_org_name", "Unknown")
    hold_date = state["hold_date"]
    start_time = state["hold_start_time"]
    end_time = state["hold_end_time"]
    event_type = state.get("hold_event_type", "HOLD")

    title = build_calendar_title(event_type, org_name)
    description = build_calendar_description(
        event_name=org_name,
        status="HOLD",
        date_time=f"{hold_date} {start_time}-{end_time}",
    )

    try:
        result = create_hold(
            title=title,
            date=hold_date,
            start_time=start_time,
            end_time=end_time,
            description=description,
        )
        return {
            "hold_event_id": result["event_id"],
            "decision": "approve",
            "draft_response": f"Calendar hold created: {title} ({start_time}-{end_time})",
        }
    except Exception as e:
        logger.error("Failed to create calendar hold: %s", e)
        return {
            "errors": state.get("errors", []) + [f"Calendar hold creation failed: {e}"],
            "decision": "needs_review",
        }
