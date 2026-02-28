from app.graph.state import ReservationState


def after_validation(state: ReservationState) -> str:
    """Route based on validation results."""
    if state.get("errors"):
        return "handle_error"
    return "evaluate_eligibility"


def after_eligibility(state: ReservationState) -> str:
    """Route based on eligibility evaluation."""
    if state.get("decision") == "needs_review":
        return "handle_error"
    if not state.get("is_eligible"):
        return "draft_rejection"
    return "determine_pricing"
