from langgraph.graph import END, START, StateGraph

from app.graph.edges import after_eligibility, after_validation
from app.graph.nodes import (
    determine_pricing,
    draft_approval_response,
    draft_rejection,
    evaluate_eligibility,
    evaluate_room_setup,
    handle_error,
    validate_input,
)
from app.graph.state import ReservationState


def build_graph() -> StateGraph:
    """Construct the reservation evaluation graph."""
    graph = StateGraph(ReservationState)

    # Add nodes
    graph.add_node("validate_input", validate_input)
    graph.add_node("evaluate_eligibility", evaluate_eligibility)
    graph.add_node("determine_pricing", determine_pricing)
    graph.add_node("evaluate_room_setup", evaluate_room_setup)
    graph.add_node("draft_approval_response", draft_approval_response)
    graph.add_node("draft_rejection", draft_rejection)
    graph.add_node("handle_error", handle_error)

    # Add edges
    graph.add_edge(START, "validate_input")
    graph.add_conditional_edges("validate_input", after_validation)
    graph.add_conditional_edges("evaluate_eligibility", after_eligibility)
    graph.add_edge("determine_pricing", "evaluate_room_setup")
    graph.add_edge("evaluate_room_setup", "draft_approval_response")
    graph.add_edge("draft_approval_response", END)
    graph.add_edge("draft_rejection", END)
    graph.add_edge("handle_error", END)

    return graph
