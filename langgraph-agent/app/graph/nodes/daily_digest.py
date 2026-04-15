"""Daily digest node — generates the 8am CT summary email for admin."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.cgcs_constants import ADMIN_EMAIL, DEADLINES, INTERN_EMAILS
from app.graph.nodes.shared import _invoke_with_retry
from app.graph.state import AgentState
from app.services.reply_processor import EDIT_LOOP_MAX

logger = logging.getLogger(__name__)


def build_daily_digest(state: AgentState) -> dict:
    """Generate the daily digest email for the CGCS admin.

    11 sections:
    1.  Pending approvals
    2.  New intakes since last digest
    3.  Upcoming events (next 30 days) with checklist status
    4.  Due reminders
    5.  Pending user agreements
    6.  Overdue deadline warnings
    7.  Checklist items due this week
    8.  Active dashboard alerts (AV/catering updates)
    9.  Edit loop status (threads approaching 10-reply limit)
    10. Budget tracking (revenue this month/quarter)
    11. Event leads per intern this month
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
    checklist_due = state.get("digest_checklist_items_due", [])
    active_alerts = state.get("digest_active_alerts", [])
    edit_loop_threads = state.get("digest_edit_loop_threads", [])
    monthly_stats = state.get("digest_monthly_stats", {})
    intern_leads = state.get("digest_intern_leads", {})

    sections: list[str] = []
    sections.append(f"CGCS Daily Digest \u2014 {today_str}")
    sections.append("=" * 50)

    # Section 1: Pending Approvals
    sections.append("\n## 1. PENDING APPROVALS")
    if pending_approvals:
        for item in pending_approvals:
            sections.append(
                f"  - [{item.get('type', 'unknown')}] {item.get('summary', 'No summary')} "
                f"(ID: {item.get('id', 'N/A')})"
            )
    else:
        sections.append("  No pending approvals.")

    # Section 2: New Intakes
    sections.append("\n## 2. NEW INTAKES")
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
    sections.append("\n## 3. UPCOMING EVENTS (Next 30 Days)")
    if upcoming_events:
        for event in upcoming_events:
            flags = []
            if event.get("overdue_actions"):
                flags.append("OVERDUE")
            if not event.get("lead"):
                flags.append("NO LEAD")
            checklist_pct = event.get("checklist_complete_pct")
            checklist_str = f" | Checklist: {checklist_pct}%" if checklist_pct is not None else ""
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            sections.append(
                f"  - {event.get('date', 'TBD')} | {event.get('event_name', 'Unknown')}"
                f" | Lead: {event.get('lead', 'Unassigned')}"
                f" | Status: {event.get('status', 'Unknown')}{checklist_str}{flag_str}"
            )
    else:
        sections.append("  No upcoming events in the next 30 days.")

    # Section 4: Due Reminders
    sections.append("\n## 4. DUE REMINDERS TODAY")
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
    sections.append("\n## 5. PENDING USER AGREEMENTS")
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
    sections.append("\n## 6. OVERDUE DEADLINE WARNINGS")
    if overdue_deadlines:
        for dl in overdue_deadlines:
            sections.append(
                f"  - {dl.get('event_name', 'Unknown')} | "
                f"Deadline: {dl.get('deadline_type', 'Unknown')} "
                f"({dl.get('days_overdue', 0)} days overdue)"
            )
    else:
        sections.append("  No overdue deadlines.")

    # Section 7: Checklist Items Due This Week
    sections.append("\n## 7. CHECKLIST ITEMS DUE THIS WEEK")
    if checklist_due:
        for item in checklist_due:
            dl_date = item.get("deadline_date", "N/A")
            days = item.get("days_until_due")
            days_str = f" ({days} days)" if days is not None else ""
            sections.append(
                f"  - {item.get('event_name', 'Unknown')} | "
                f"{item.get('item_label', item.get('checklist_task', 'Unknown'))} | "
                f"Due: {dl_date}{days_str}"
            )
    else:
        sections.append("  No checklist items due this week.")

    # Section 8: Active Dashboard Alerts
    sections.append("\n## 8. ACTIVE DASHBOARD ALERTS")
    if active_alerts:
        for alert in active_alerts:
            sections.append(
                f"  - [{alert.get('alert_type', 'unknown')}] {alert.get('title', 'No title')}"
            )
            if alert.get("detail"):
                sections.append(f"    Detail: {alert['detail'][:200]}")
    else:
        sections.append("  No active alerts.")

    # Section 9: Edit Loop Status
    sections.append("\n## 9. EDIT LOOP STATUS")
    if edit_loop_threads:
        for thread in edit_loop_threads:
            count = thread.get("edit_loop_count", 0)
            remaining = EDIT_LOOP_MAX - count
            warning = " \u26a0\ufe0f APPROACHING LIMIT" if remaining <= 2 else ""
            sections.append(
                f"  - {thread.get('event_name', 'Unknown')} | "
                f"Replies: {count}/{EDIT_LOOP_MAX}{warning} | "
                f"Thread: {thread.get('thread_id', 'N/A')}"
            )
    else:
        sections.append("  No active edit loops.")

    # Section 10: Budget Tracking
    sections.append("\n## 10. BUDGET TRACKING")
    if monthly_stats:
        events = monthly_stats.get("events_this_month", "N/A")
        revenue = monthly_stats.get("revenue_this_month")
        pending = monthly_stats.get("pending_approvals", "N/A")
        rate = monthly_stats.get("on_time_checklist_rate")

        sections.append(f"  Events this month: {events}")
        sections.append(f"  Revenue this month: ${revenue:,.2f}" if revenue is not None else "  Revenue this month: N/A")
        sections.append(f"  Pending approvals: {pending}")
        sections.append(f"  On-time checklist rate: {rate}%" if rate is not None else "  On-time checklist rate: N/A")
    else:
        sections.append("  Stats unavailable.")

    # Section 11: Event Leads Per Intern
    sections.append("\n## 11. EVENT LEADS PER INTERN THIS MONTH")
    if intern_leads:
        for name, count in sorted(intern_leads.items()):
            cap_warning = " (AT CAP)" if count >= 3 else ""
            sections.append(f"  - {name}: {count}/3{cap_warning}")
    else:
        # Show all interns with 0
        for name in sorted(INTERN_EMAILS.keys()):
            sections.append(f"  - {name}: 0/3")

    # Deadline reference footer
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
