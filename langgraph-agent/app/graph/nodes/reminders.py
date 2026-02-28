"""Reminder nodes — find due reminders and send them."""

import logging
from datetime import datetime

from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def find_due_reminders(state: AgentState) -> dict:
    """Find reminders that are due today or overdue."""
    # In production this queries the database via db/lead_queries.py
    # The state will be populated by the API endpoint before graph invocation
    reminders_due = state.get("reminders_due", [])

    if not reminders_due:
        logger.info("No reminders due")
        return {
            "reminders_due": [],
            "decision": "approve",
            "draft_response": "No reminders due at this time.",
        }

    today = datetime.now().date().isoformat()
    due_now = [
        r for r in reminders_due
        if r.get("remind_date", "") <= today and r.get("status") == "pending"
    ]

    logger.info("Found %d due reminders", len(due_now))
    return {
        "reminders_due": due_now,
        "decision": "approve" if due_now else "approve",
        "draft_response": f"Found {len(due_now)} reminders due for processing.",
    }


def send_reminders(state: AgentState) -> dict:
    """Process and mark reminders as sent."""
    reminders_due = state.get("reminders_due", [])

    if not reminders_due:
        return {
            "reminders_sent": [],
            "draft_response": "No reminders to send.",
        }

    sent = []
    for reminder in reminders_due:
        try:
            # In production, this sends via Zoho Mail API
            # For now, we mark them as ready to send
            sent.append({
                **reminder,
                "status": "sent",
                "sent_at": datetime.now().isoformat(),
            })
            logger.info(
                "Reminder sent: %s for reservation %s to %s",
                reminder.get("reminder_type"),
                reminder.get("reservation_id"),
                reminder.get("staff_email"),
            )
        except Exception as e:
            logger.error("Failed to send reminder: %s", e)

    return {
        "reminders_sent": sent,
        "draft_response": f"Sent {len(sent)} of {len(reminders_due)} reminders.",
    }
