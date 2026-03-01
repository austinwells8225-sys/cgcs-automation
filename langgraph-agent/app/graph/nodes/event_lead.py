"""Event lead nodes — assign staff leads and schedule reminders."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.cgcs_constants import (
    MAX_LEADS_PER_STAFF_PER_MONTH,
    REMINDER_INTERVALS,
    STAFF_ROSTER,
)
from app.graph.nodes.shared import _sanitize_string
from app.graph.state import AgentState

logger = logging.getLogger(__name__)

# Build a set of valid staff emails for quick lookup
_VALID_STAFF_EMAILS = {s["email"].lower() for s in STAFF_ROSTER}


def assign_event_lead(state: AgentState) -> dict:
    """Assign a staff member as the event lead for a reservation.

    Validates against STAFF_ROSTER and enforces MAX_LEADS_PER_STAFF_PER_MONTH cap.
    """
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

    # Validate staff is in the roster
    if staff_email and staff_email.lower() not in _VALID_STAFF_EMAILS:
        errors.append(
            f"Staff member {staff_email} is not in the CGCS staff roster. "
            f"Valid staff: {', '.join(s['name'] for s in STAFF_ROSTER)}"
        )

    if errors:
        return {
            "errors": state.get("errors", []) + errors,
            "decision": "needs_review",
        }

    # Check monthly lead cap (in production, query DB for current month count)
    current_month_leads = state.get("lead_current_month_count", 0)
    if current_month_leads >= MAX_LEADS_PER_STAFF_PER_MONTH:
        return {
            "errors": state.get("errors", []) + [
                f"{staff_name} has reached the monthly lead cap "
                f"({MAX_LEADS_PER_STAFF_PER_MONTH} leads per month). "
                f"Please assign a different staff member."
            ],
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
    for interval in REMINDER_INTERVALS:  # from cgcs_constants
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
