"""Event lead nodes — assign staff leads and schedule reminders."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.graph.nodes.shared import _sanitize_string
from app.graph.state import AgentState

logger = logging.getLogger(__name__)

REMINDER_INTERVALS = [
    {"label": "30_day", "days": 30},
    {"label": "14_day", "days": 14},
    {"label": "7_day", "days": 7},
    {"label": "48_hour", "days": 2},
]


def assign_event_lead(state: AgentState) -> dict:
    """Assign a staff member as the event lead for a reservation."""
    staff_name = state.get("lead_staff_name")
    staff_email = state.get("lead_staff_email")
    reservation_id = state.get("lead_reservation_id")

    errors: list[str] = []

    if not staff_name:
        errors.append("Missing required field: lead_staff_name")
    if not staff_email:
        errors.append("Missing required field: lead_staff_email")
    if not reservation_id:
        errors.append("Missing required field: lead_reservation_id")

    if errors:
        return {
            "errors": state.get("errors", []) + errors,
            "decision": "needs_review",
        }

    return {
        "lead_staff_name": _sanitize_string(staff_name),
        "lead_staff_email": _sanitize_string(staff_email),
        "lead_reservation_id": reservation_id,
        "decision": "approve",
        "draft_response": f"Event lead assigned: {staff_name} ({staff_email}) for reservation {reservation_id}",
    }


def schedule_reminders(state: AgentState) -> dict:
    """Schedule reminder notifications at 30d/14d/7d/48h before the event."""
    event_date_str = state.get("lead_event_date")
    staff_email = state.get("lead_staff_email")
    reservation_id = state.get("lead_reservation_id")

    if not event_date_str or not staff_email:
        return {
            "errors": state.get("errors", []) + ["Cannot schedule reminders: missing event date or staff email"],
            "decision": "needs_review",
        }

    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
    except ValueError:
        return {
            "errors": state.get("errors", []) + [f"Invalid lead_event_date format: {event_date_str}"],
            "decision": "needs_review",
        }

    reminders = []
    today = datetime.now().date()
    for interval in REMINDER_INTERVALS:
        remind_date = event_date - timedelta(days=interval["days"])
        if remind_date >= today:
            reminders.append({
                "reservation_id": reservation_id,
                "staff_email": staff_email,
                "reminder_type": interval["label"],
                "remind_date": remind_date.isoformat(),
                "status": "pending",
            })

    return {
        "reminders_due": reminders,
        "draft_response": f"Scheduled {len(reminders)} reminders for reservation {reservation_id}",
    }
