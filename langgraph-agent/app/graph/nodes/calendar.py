"""Calendar availability check node."""

import logging

from app.graph.state import AgentState
from app.services.google_calendar import check_availability

logger = logging.getLogger(__name__)


def check_calendar_availability(state: AgentState) -> dict:
    """Check Google Calendar availability for the requested time slot."""
    query_date = state.get("calendar_query_date")
    query_start = state.get("calendar_query_start")
    query_end = state.get("calendar_query_end")

    if not query_date or not query_start or not query_end:
        return {
            "errors": state.get("errors", []) + [
                "Missing calendar query fields: calendar_query_date, calendar_query_start, calendar_query_end"
            ],
            "decision": "needs_review",
        }

    try:
        result = check_availability(query_date, query_start, query_end)
        return {
            "calendar_is_available": result["is_available"],
            "calendar_events": result.get("events", []),
            "decision": "approve" if result["is_available"] else "reject",
        }
    except Exception as e:
        logger.error("Calendar availability check failed: %s", e)
        return {
            "calendar_is_available": None,
            "calendar_events": [],
            "errors": state.get("errors", []) + [f"Calendar API failed: {e}"],
            "decision": "needs_review",
        }
