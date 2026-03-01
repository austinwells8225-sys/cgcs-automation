"""Graph nodes package — re-exports all node functions for backward compatibility."""

from app.graph.nodes.shared import (
    _invoke_with_retry,
    _parse_json_response,
    _sanitize_string,
    llm,
)
from app.graph.nodes.intake import (
    validate_input,
    evaluate_eligibility,
    determine_pricing,
    evaluate_room_setup,
    draft_approval_response,
    draft_rejection,
    handle_error,
)
from app.graph.nodes.router import route_task
from app.graph.nodes.email_triage import (
    classify_email,
    draft_email_reply,
    check_auto_send,
)
from app.graph.nodes.calendar import check_calendar_availability
from app.graph.nodes.calendar_hold import (
    validate_hold_request,
    create_calendar_hold,
)
from app.graph.nodes.pet_tracker import (
    read_pet_tracker,
    prepare_pet_update,
)
from app.graph.nodes.event_lead import (
    assign_event_lead,
    schedule_reminders,
)
from app.graph.nodes.reminders import (
    find_due_reminders,
    send_reminders,
)
from app.graph.nodes.daily_digest import build_daily_digest

__all__ = [
    # Shared
    "_invoke_with_retry",
    "_parse_json_response",
    "_sanitize_string",
    "llm",
    # Router
    "route_task",
    # Intake
    "validate_input",
    "evaluate_eligibility",
    "determine_pricing",
    "evaluate_room_setup",
    "draft_approval_response",
    "draft_rejection",
    "handle_error",
    # Email triage
    "classify_email",
    "draft_email_reply",
    "check_auto_send",
    # Calendar
    "check_calendar_availability",
    # Calendar hold
    "validate_hold_request",
    "create_calendar_hold",
    # P.E.T. tracker
    "read_pet_tracker",
    "prepare_pet_update",
    # Event lead
    "assign_event_lead",
    "schedule_reminders",
    # Reminders
    "find_due_reminders",
    "send_reminders",
    # Daily digest
    "build_daily_digest",
]
