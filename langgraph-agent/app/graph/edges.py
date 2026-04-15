from langgraph.graph import END

from app.graph.state import AgentState


def after_routing(state: AgentState) -> str:
    """Route to the correct capability subgraph based on task_type."""
    if state.get("errors"):
        return "handle_error"

    task_type = state.get("task_type", "event_intake")

    routes = {
        "event_intake": "validate_input",
        "email_triage": "classify_email",
        "calendar_check": "check_calendar_availability",
        "calendar_hold": "validate_hold_request",
        "pet_tracker": "read_pet_tracker",
        "event_lead": "assign_event_lead",
        "reminder_check": "find_due_reminders",
        "daily_digest": "build_daily_digest",
        "smartsheet_intake": "classify_intake_request",
        "email_reply": "process_email_reply",
    }

    return routes.get(task_type, "handle_error")


def after_validation(state: AgentState) -> str:
    """Route based on validation results."""
    if state.get("errors"):
        return "handle_error"
    return "evaluate_eligibility"


def after_eligibility(state: AgentState) -> str:
    """Route based on eligibility evaluation."""
    if state.get("decision") == "needs_review":
        return "handle_error"
    if not state.get("is_eligible"):
        return "draft_rejection"
    return "determine_pricing"


def after_email_classification(state: AgentState) -> str:
    """Route based on email classification results."""
    if state.get("errors"):
        return "handle_error"
    return "draft_email_reply"


def after_hold_validation(state: AgentState) -> str:
    """Route based on hold validation results."""
    if state.get("errors"):
        return "handle_error"
    return "create_calendar_hold"


def after_pet_read(state: AgentState) -> str:
    """Route based on P.E.T. operation type."""
    if state.get("errors"):
        return "handle_error"
    if state.get("pet_operation") == "update":
        return "prepare_pet_update"
    return END


def after_intake_classification(state: AgentState) -> str:
    """Route after intake classification."""
    if state.get("errors"):
        return "handle_error"
    return "draft_intake_emails"


def after_lead_assignment(state: AgentState) -> str:
    """Route after lead assignment."""
    if state.get("errors"):
        return "handle_error"
    return "schedule_reminders"
