"""Router node — determines which capability to invoke based on task_type."""

import logging

from app.graph.state import AgentState

logger = logging.getLogger(__name__)

VALID_TASK_TYPES = {
    "event_intake",
    "email_triage",
    "calendar_check",
    "calendar_hold",
    "pet_tracker",
    "event_lead",
    "reminder_check",
    "daily_digest",
}


def route_task(state: AgentState) -> dict:
    """Validate task_type and pass through. Routing is done via conditional edges."""
    task_type = state.get("task_type", "event_intake")

    if task_type not in VALID_TASK_TYPES:
        logger.error("Unknown task_type: %s", task_type)
        return {
            "errors": state.get("errors", []) + [f"Unknown task_type: {task_type}"],
            "decision": "needs_review",
        }

    logger.info("Routing task: %s (request_id=%s)", task_type, state.get("request_id"))
    return {"task_type": task_type}
