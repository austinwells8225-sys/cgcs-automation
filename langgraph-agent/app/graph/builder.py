from langgraph.graph import END, START, StateGraph

from app.graph.edges import (
    after_eligibility,
    after_email_classification,
    after_hold_validation,
    after_lead_assignment,
    after_pet_read,
    after_routing,
    after_validation,
)
from app.graph.nodes import (
    assign_event_lead,
    check_auto_send,
    check_calendar_availability,
    classify_email,
    create_calendar_hold,
    determine_pricing,
    draft_approval_response,
    draft_email_reply,
    draft_rejection,
    evaluate_eligibility,
    evaluate_room_setup,
    find_due_reminders,
    handle_error,
    prepare_pet_update,
    read_pet_tracker,
    route_task,
    schedule_reminders,
    send_reminders,
    validate_hold_request,
    validate_input,
)
from app.graph.state import AgentState


def build_graph() -> StateGraph:
    """Construct the unified CGCS agent graph with all capabilities."""
    graph = StateGraph(AgentState)

    # --- Router ---
    graph.add_node("route_task", route_task)

    # --- Event intake nodes ---
    graph.add_node("validate_input", validate_input)
    graph.add_node("evaluate_eligibility", evaluate_eligibility)
    graph.add_node("determine_pricing", determine_pricing)
    graph.add_node("evaluate_room_setup", evaluate_room_setup)
    graph.add_node("draft_approval_response", draft_approval_response)
    graph.add_node("draft_rejection", draft_rejection)

    # --- Email triage nodes ---
    graph.add_node("classify_email", classify_email)
    graph.add_node("draft_email_reply", draft_email_reply)
    graph.add_node("check_auto_send", check_auto_send)

    # --- Calendar nodes ---
    graph.add_node("check_calendar_availability", check_calendar_availability)

    # --- Calendar hold nodes ---
    graph.add_node("validate_hold_request", validate_hold_request)
    graph.add_node("create_calendar_hold", create_calendar_hold)

    # --- P.E.T. tracker nodes ---
    graph.add_node("read_pet_tracker", read_pet_tracker)
    graph.add_node("prepare_pet_update", prepare_pet_update)

    # --- Event lead nodes ---
    graph.add_node("assign_event_lead", assign_event_lead)
    graph.add_node("schedule_reminders", schedule_reminders)

    # --- Reminder nodes ---
    graph.add_node("find_due_reminders", find_due_reminders)
    graph.add_node("send_reminders", send_reminders)

    # --- Shared error handler ---
    graph.add_node("handle_error", handle_error)

    # ============================================================
    # Edges
    # ============================================================

    # Entry: START → route_task → conditional routing
    graph.add_edge(START, "route_task")
    graph.add_conditional_edges("route_task", after_routing)

    # --- Event intake edges ---
    graph.add_conditional_edges("validate_input", after_validation)
    graph.add_conditional_edges("evaluate_eligibility", after_eligibility)
    graph.add_edge("determine_pricing", "evaluate_room_setup")
    graph.add_edge("evaluate_room_setup", "draft_approval_response")
    graph.add_edge("draft_approval_response", END)
    graph.add_edge("draft_rejection", END)

    # --- Email triage edges ---
    graph.add_conditional_edges("classify_email", after_email_classification)
    graph.add_edge("draft_email_reply", "check_auto_send")
    graph.add_edge("check_auto_send", END)

    # --- Calendar edges ---
    graph.add_edge("check_calendar_availability", END)

    # --- Calendar hold edges ---
    graph.add_conditional_edges("validate_hold_request", after_hold_validation)
    graph.add_edge("create_calendar_hold", END)

    # --- P.E.T. tracker edges ---
    graph.add_conditional_edges("read_pet_tracker", after_pet_read)
    graph.add_edge("prepare_pet_update", END)

    # --- Event lead edges ---
    graph.add_conditional_edges("assign_event_lead", after_lead_assignment)
    graph.add_edge("schedule_reminders", END)

    # --- Reminder edges ---
    graph.add_edge("find_due_reminders", "send_reminders")
    graph.add_edge("send_reminders", END)

    # --- Error handler ---
    graph.add_edge("handle_error", END)

    return graph
