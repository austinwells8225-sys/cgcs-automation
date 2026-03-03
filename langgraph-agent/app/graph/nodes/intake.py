"""Event intake nodes — moved verbatim from the original nodes.py."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from app.cgcs_constants import (
    AMI_FACILITY_PRICING,
    DEADLINES,
    DEPOSIT_RATE,
    EVENT_PREFIXES,
    HOURS,
)
from app.data.pricing import PRICING_TIERS, compute_cost
from app.data.room_setup import ROOM_CONFIGS, find_suitable_room
from app.graph.nodes.shared import (
    _invoke_with_retry,
    _parse_json_response,
    _sanitize_string,
)
from app.graph.state import AgentState
from app.prompts.templates import (
    APPROVAL_RESPONSE_SYSTEM_PROMPT,
    ELIGIBILITY_SYSTEM_PROMPT,
    PRICING_SYSTEM_PROMPT,
    REJECTION_RESPONSE_SYSTEM_PROMPT,
    SETUP_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def validate_input(state: AgentState) -> dict:
    """Validate and sanitize all required fields. Pure Python, no LLM call."""
    errors: list[str] = []

    # Required fields
    for field in ["request_id", "requester_name", "requester_email", "event_name",
                  "requested_date", "requested_start_time", "requested_end_time"]:
        if not state.get(field):
            errors.append(f"Missing required field: {field}")

    # Sanitize string inputs
    sanitized = {}
    for field in ["requester_name", "requester_email", "requester_organization",
                  "event_name", "event_description", "setup_requirements_raw"]:
        raw = state.get(field)
        if raw:
            sanitized[field] = _sanitize_string(str(raw))

    # Date format
    if state.get("requested_date"):
        try:
            datetime.strptime(state["requested_date"], "%Y-%m-%d")
        except ValueError:
            errors.append("Invalid date format. Expected YYYY-MM-DD.")

    # Time format
    for time_field in ["requested_start_time", "requested_end_time"]:
        val = state.get(time_field)
        if val:
            if not re.match(r"^\d{2}:\d{2}$", val):
                errors.append(f"Invalid time format for {time_field}. Expected HH:MM.")

    # Start before end
    start = state.get("requested_start_time", "")
    end = state.get("requested_end_time", "")
    if start and end and start >= end:
        errors.append("Start time must be before end time.")

    # Email basic check
    email = state.get("requester_email", "")
    if email and "@" not in email:
        errors.append("Invalid email format.")

    # Attendee count
    attendees = state.get("estimated_attendees")
    if attendees is not None and (attendees < 1 or attendees > 500):
        errors.append("Estimated attendees must be between 1 and 500.")

    # Room type
    room = state.get("room_requested")
    if room and room not in ROOM_CONFIGS:
        errors.append(f"Unknown room type: {room}. Valid types: {', '.join(ROOM_CONFIGS.keys())}")

    # Request ID format check (prevent injection via request_id)
    request_id = state.get("request_id", "")
    if request_id and not re.match(r"^[a-zA-Z0-9_-]{1,64}$", request_id):
        errors.append("Invalid request_id format. Use alphanumeric, hyphens, underscores only.")

    return {**sanitized, "errors": errors}


def evaluate_eligibility(state: AgentState) -> dict:
    """Use Claude to evaluate whether the request meets CGCS eligibility criteria."""
    user_message = (
        f"Organization: {_sanitize_string(state.get('requester_organization', 'Not specified'))}\n"
        f"Event Name: {_sanitize_string(state.get('event_name', ''))}\n"
        f"Event Description: {_sanitize_string(state.get('event_description', 'Not provided'))}\n"
        f"Requester: {_sanitize_string(state.get('requester_name', ''))} ({state.get('requester_email', '')})"
    )

    try:
        content = _invoke_with_retry([
            {"role": "system", "content": ELIGIBILITY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ])
        result = _parse_json_response(content)
        return {
            "is_eligible": result["is_eligible"],
            "eligibility_reason": result["reason"],
            "pricing_tier": result.get("tier_suggestion"),
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse eligibility response: %s", e)
        return {
            "is_eligible": None,
            "eligibility_reason": "Failed to parse AI evaluation",
            "errors": state.get("errors", []) + ["Eligibility evaluation failed"],
            "decision": "needs_review",
        }
    except Exception as e:
        logger.error("Eligibility evaluation failed after retries: %s", e)
        return {
            "is_eligible": None,
            "eligibility_reason": f"AI evaluation unavailable: {type(e).__name__}",
            "errors": state.get("errors", []) + [f"Eligibility LLM call failed: {e}"],
            "decision": "needs_review",
        }


def determine_pricing(state: AgentState) -> dict:
    """Use Claude to classify pricing tier and compute cost."""
    user_message = (
        f"Organization: {_sanitize_string(state.get('requester_organization', 'Not specified'))}\n"
        f"Event Name: {_sanitize_string(state.get('event_name', ''))}\n"
        f"Event Description: {_sanitize_string(state.get('event_description', 'Not provided'))}\n"
        f"Suggested Tier from Eligibility Check: {state.get('pricing_tier', 'Not determined')}"
    )

    try:
        content = _invoke_with_retry([
            {"role": "system", "content": PRICING_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ])
        result = _parse_json_response(content)
        tier = result["pricing_tier"]
        if tier not in PRICING_TIERS:
            tier = "external"

        cost = compute_cost(tier, state["requested_start_time"], state["requested_end_time"])

        # For A-EVENT (AMI/paid), calculate deposit
        event_type = state.get("event_type", "")
        deposit = 0.0
        if event_type == "A-EVENT" and cost > 0:
            deposit = round(cost * DEPOSIT_RATE, 2)

        return {
            "pricing_tier": tier,
            "estimated_cost": cost,
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse pricing response: %s", e)
        return {
            "pricing_tier": state.get("pricing_tier", "external"),
            "estimated_cost": 0.0,
            "errors": state.get("errors", []) + ["Pricing determination had issues"],
        }
    except Exception as e:
        logger.error("Pricing determination failed after retries: %s", e)
        return {
            "pricing_tier": state.get("pricing_tier", "external"),
            "estimated_cost": 0.0,
            "errors": state.get("errors", []) + [f"Pricing LLM call failed: {e}"],
        }


def evaluate_room_setup(state: AgentState) -> dict:
    """Use Claude to parse setup requirements and validate room suitability."""
    room_key = state.get("room_requested") or "multipurpose"
    room = ROOM_CONFIGS.get(room_key, ROOM_CONFIGS["multipurpose"])

    attendees = state.get("estimated_attendees", 0) or 0
    suitable_room = find_suitable_room(attendees, room_key)
    if suitable_room and suitable_room != room_key:
        room_key = suitable_room
        room = ROOM_CONFIGS[room_key]

    setup_raw = _sanitize_string(state.get("setup_requirements_raw", "Standard setup"))
    prompt = SETUP_SYSTEM_PROMPT.format(
        room_name=room["display_name"],
        max_capacity=room["max_capacity"],
        available_equipment=json.dumps(room["equipment"]),
        setup_options=json.dumps(room["setups"]),
    )

    user_message = (
        f"Setup requirements: {setup_raw}\n"
        f"Estimated attendees: {attendees}\n"
        f"Event: {_sanitize_string(state.get('event_name', ''))}"
    )

    try:
        content = _invoke_with_retry([
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message},
        ])
        result = _parse_json_response(content)
        final_room = room_key
        if not result.get("room_suitable", True) and result.get("alternative_room"):
            final_room = result["alternative_room"]

        return {
            "room_assignment": final_room,
            "setup_config": result.get("setup_config", {}),
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse room setup response: %s", e)
        return {"room_assignment": room_key, "setup_config": {}}
    except Exception as e:
        logger.error("Room setup evaluation failed after retries: %s", e)
        return {"room_assignment": room_key, "setup_config": {}}


def draft_approval_response(state: AgentState) -> dict:
    """Use Claude to draft an approval email."""
    room_key = state.get("room_assignment", "multipurpose")
    room_name = ROOM_CONFIGS.get(room_key, {}).get("display_name", room_key)

    quote_snippet = state.get("quote_email_snippet", "")
    prompt = APPROVAL_RESPONSE_SYSTEM_PROMPT.format(
        requester_name=_sanitize_string(state.get("requester_name", "")),
        organization=_sanitize_string(state.get("requester_organization", "Not specified")),
        event_name=_sanitize_string(state.get("event_name", "")),
        requested_date=state.get("requested_date", ""),
        start_time=state.get("requested_start_time", ""),
        end_time=state.get("requested_end_time", ""),
        room_name=room_name,
        setup_details=json.dumps(state.get("setup_config", {}), indent=2),
        pricing_tier=state.get("pricing_tier", "external"),
        estimated_cost=state.get("estimated_cost", 0),
        quote_details=quote_snippet if quote_snippet else "No itemized quote available.",
    )

    try:
        content = _invoke_with_retry([
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Draft the approval email now."},
        ])
        return {"draft_response": content, "decision": "approve"}
    except Exception as e:
        logger.error("Draft approval failed after retries: %s", e)
        return {
            "draft_response": None,
            "decision": "needs_review",
            "errors": state.get("errors", []) + [f"Draft approval LLM call failed: {e}"],
        }


def draft_rejection(state: AgentState) -> dict:
    """Use Claude to draft a rejection email."""
    prompt = REJECTION_RESPONSE_SYSTEM_PROMPT.format(
        requester_name=_sanitize_string(state.get("requester_name", "")),
        organization=_sanitize_string(state.get("requester_organization", "Not specified")),
        event_name=_sanitize_string(state.get("event_name", "")),
        rejection_reason=state.get("eligibility_reason", "Does not meet eligibility criteria"),
    )

    try:
        content = _invoke_with_retry([
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Draft the rejection email now."},
        ])
        return {"draft_response": content, "decision": "reject"}
    except Exception as e:
        logger.error("Draft rejection failed after retries: %s", e)
        return {
            "draft_response": None,
            "decision": "needs_review",
            "errors": state.get("errors", []) + [f"Draft rejection LLM call failed: {e}"],
        }


def handle_error(state: AgentState) -> dict:
    """Generate a fallback response for manual review."""
    errors = state.get("errors", [])
    return {
        "draft_response": (
            f"This reservation request requires manual review.\n\n"
            f"Request ID: {state.get('request_id', 'unknown')}\n"
            f"Requester: {state.get('requester_name', 'unknown')} "
            f"({state.get('requester_email', 'unknown')})\n"
            f"Event: {state.get('event_name', 'unknown')}\n\n"
            f"Issues found:\n" + "\n".join(f"- {e}" for e in errors)
        ),
        "decision": "needs_review",
    }
