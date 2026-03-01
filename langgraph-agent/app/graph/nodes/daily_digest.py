"""Daily digest node — generates the 8am CT summary email for admin."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.cgcs_constants import ADMIN_EMAIL, DEADLINES
from app.graph.nodes.shared import _invoke_with_retry
from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def build_daily_digest(state: AgentState) -> dict:
    """Generate the daily digest email for the CGCS admin.

    Includes:
    - All pending approval items with preview
    - New intakes with 3 suggested reply prompts each
    - Events in next 30 days with status, lead, and overdue action flags
    - Due reminders for today
    - Pending user agreements (sent but not returned)
    - Overdue deadline warnings (TDX 15 biz days, catering 25 biz days, walkthrough 12 biz days)
    """
    today = datetime.now().date()
    today_str = today.isoformat()

    # Collect data from state (in production, these come from DB queries)
    pending_approvals = state.get("digest_pending_approvals", [])
    new_intakes = state.get("digest_new_intakes", [])
    upcoming_events = state.get("digest_upcoming_events", [])
    due_reminders = state.get("reminders_due", [])
    pending_agreements = state.get("digest_pending_agreements", [])
    overdue_deadlines = state.get("digest_overdue_deadlines", [])

    sections: list[str] = []
    sections.append(f"CGCS Daily Digest — {today_str}")
    sections.append("=" * 50)

    # Section 1: Pending Approvals
    sections.append("\n## PENDING APPROVALS")
    if pending_approvals:
        for item in pending_approvals:
            sections.append(
                f"  - [{item.get('type', 'unknown')}] {item.get('summary', 'No summary')} "
                f"(ID: {item.get('id', 'N/A')})"
            )
    else:
        sections.append("  No pending approvals.")

    # Section 2: New Intakes
    sections.append("\n## NEW INTAKES")
    if new_intakes:
        for intake in new_intakes:
            sections.append(
                f"  - {intake.get('event_name', 'Unknown Event')} | "
                f"{intake.get('requester_name', 'Unknown')} | "
                f"{intake.get('requested_date', 'No date')}"
            )
            suggestions = intake.get("suggested_replies", [])
            for i, s in enumerate(suggestions[:3], 1):
                sections.append(f"    Reply Option {i}: {s}")
    else:
        sections.append("  No new intakes.")

    # Section 3: Upcoming Events (next 30 days)
    sections.append("\n## UPCOMING EVENTS (Next 30 Days)")
    if upcoming_events:
        for event in upcoming_events:
            flags = []
            if event.get("overdue_actions"):
                flags.append("OVERDUE")
            if not event.get("lead"):
                flags.append("NO LEAD")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            sections.append(
                f"  - {event.get('date', 'TBD')} | {event.get('event_name', 'Unknown')}"
                f" | Lead: {event.get('lead', 'Unassigned')}"
                f" | Status: {event.get('status', 'Unknown')}{flag_str}"
            )
    else:
        sections.append("  No upcoming events in the next 30 days.")

    # Section 4: Due Reminders
    sections.append("\n## DUE REMINDERS TODAY")
    if due_reminders:
        for reminder in due_reminders:
            sections.append(
                f"  - {reminder.get('reminder_type', 'unknown')} reminder for "
                f"reservation {reminder.get('reservation_id', 'N/A')} "
                f"(staff: {reminder.get('staff_email', 'N/A')})"
            )
    else:
        sections.append("  No reminders due today.")

    # Section 5: Pending User Agreements
    sections.append("\n## PENDING USER AGREEMENTS")
    if pending_agreements:
        for agreement in pending_agreements:
            sections.append(
                f"  - {agreement.get('event_name', 'Unknown')} | "
                f"Sent: {agreement.get('sent_date', 'N/A')} | "
                f"Contact: {agreement.get('contact', 'N/A')}"
            )
    else:
        sections.append("  No pending user agreements.")

    # Section 6: Overdue Deadline Warnings
    sections.append("\n## OVERDUE DEADLINE WARNINGS")
    if overdue_deadlines:
        for dl in overdue_deadlines:
            sections.append(
                f"  - {dl.get('event_name', 'Unknown')} | "
                f"Deadline: {dl.get('deadline_type', 'Unknown')} "
                f"({dl.get('days_overdue', 0)} days overdue)"
            )
    else:
        sections.append("  No overdue deadlines.")

    # Section 7: Deadline Reference
    sections.append("\n## DEADLINE REFERENCE")
    sections.append(f"  CGCS Response: {DEADLINES['cgcs_response']} business days")
    sections.append(f"  TDX AV Request: {DEADLINES['tdx_av']} business days")
    sections.append(f"  Walkthrough: {DEADLINES['walkthrough']} business days")
    sections.append(f"  ACC Catering: {DEADLINES['catering_acc']} business days")
    sections.append(f"  Run of Show/Furniture: {DEADLINES['run_of_show_furniture']} business days")

    digest_body = "\n".join(sections)

    return {
        "draft_response": digest_body,
        "decision": "approve",
        "email_draft_reply": digest_body,
    }
