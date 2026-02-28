"""P.E.T. tracker nodes — read and prepare updates for the P.E.T. tracking spreadsheet."""

import logging

from app.graph.nodes.shared import _sanitize_string
from app.graph.state import AgentState
from app.services.google_sheets import read_sheet, prepare_update

logger = logging.getLogger(__name__)


def read_pet_tracker(state: AgentState) -> dict:
    """Read data from the P.E.T. tracker spreadsheet."""
    query = state.get("pet_query", "")
    operation = state.get("pet_operation", "read")

    try:
        result = read_sheet(query=_sanitize_string(query))
        return {
            "pet_result": result,
            "decision": "approve",
            "draft_response": f"P.E.T. tracker query completed. Found {len(result.get('rows', []))} rows.",
        }
    except Exception as e:
        logger.error("P.E.T. tracker read failed: %s", e)
        return {
            "pet_result": None,
            "errors": state.get("errors", []) + [f"P.E.T. tracker read failed: {e}"],
            "decision": "needs_review",
        }


def prepare_pet_update(state: AgentState) -> dict:
    """Stage a P.E.T. tracker update for admin approval."""
    row_data = state.get("pet_row_data")

    if not row_data:
        return {
            "errors": state.get("errors", []) + ["No pet_row_data provided for update"],
            "decision": "needs_review",
        }

    try:
        result = prepare_update(row_data=row_data)
        return {
            "pet_result": result,
            "requires_approval": True,
            "approved": False,
            "decision": "needs_review",
            "draft_response": f"P.E.T. update staged for approval: {result.get('staged_id', 'unknown')}",
        }
    except Exception as e:
        logger.error("P.E.T. tracker update staging failed: %s", e)
        return {
            "pet_result": None,
            "errors": state.get("errors", []) + [f"P.E.T. update staging failed: {e}"],
            "decision": "needs_review",
        }
