"""Email reply graph nodes — edit loop, escalation, and change detection."""

from __future__ import annotations

import logging

from app.graph.state import AgentState
from app.services.reply_processor import (
    check_edit_loop,
    detect_av_catering_changes,
    detect_escalation,
    detect_furniture_changes,
    draft_furniture_update_email,
    build_dashboard_alert,
)

logger = logging.getLogger(__name__)


def process_email_reply(state: AgentState) -> dict:
    """Process an incoming email reply: edit loop, escalation, change detection.

    Runs all detection in sequence and returns combined results.
    """
    reply_body = state.get("reply_body") or ""
    edit_count = state.get("edit_loop_count") or 0
    failed_replies = state.get("failed_replies") or 0
    parsed = state.get("smartsheet_parsed") or {}

    if not reply_body:
        return {
            "errors": state.get("errors", []) + ["No reply body to process"],
            "decision": "needs_review",
        }

    # 1. Edit loop check
    loop = check_edit_loop(edit_count)
    if loop["limit_reached"]:
        logger.info("Edit loop limit reached (%d)", loop["edit_loop_count"])
        return {
            "edit_loop_count": loop["edit_loop_count"],
            "draft_response": loop["limit_message"],
            "decision": "approve",
            "email_auto_send": True,
            "reply_action": "edit_loop_limit",
        }

    # 2. Escalation detection
    escalation = detect_escalation(reply_body, failed_replies)
    if escalation["escalation_needed"]:
        logger.info("Escalation detected: %s", escalation["reasons"])
        return {
            "edit_loop_count": loop["edit_loop_count"],
            "escalation_detected": True,
            "escalation_reasons": escalation["reasons"],
            "escalation_forward_to": escalation["forward_to"],
            "draft_response": escalation["auto_reply"],
            "decision": "needs_review",
            "reply_action": "escalate",
        }

    # 3. Furniture change detection
    furniture = detect_furniture_changes(reply_body)
    draft_emails: list[dict] = []
    if furniture["furniture_changes_detected"]:
        logger.info("Furniture changes detected: %s", furniture["change_descriptions"])
        furn_email = draft_furniture_update_email(parsed, furniture["change_descriptions"])
        draft_emails.append(furn_email)

    # 4. AV / catering change detection
    av_catering = detect_av_catering_changes(reply_body)
    alerts: list[dict] = []
    event_name = parsed.get("event_name") or state.get("event_name") or "Unknown Event"

    if av_catering["av_change_detected"]:
        logger.info("AV change detected for %s", event_name)
        alerts.append(build_dashboard_alert(
            alert_type="av_update",
            event_name=event_name,
            detail=av_catering["av_excerpt"],
            reservation_id=state.get("request_id"),
        ))

    if av_catering["catering_change_detected"]:
        logger.info("Catering change detected for %s", event_name)
        alerts.append(build_dashboard_alert(
            alert_type="catering_update",
            event_name=event_name,
            detail=av_catering["catering_excerpt"],
            reservation_id=state.get("request_id"),
        ))

    return {
        "edit_loop_count": loop["edit_loop_count"],
        "escalation_detected": False,
        "furniture_changes_detected": furniture["furniture_changes_detected"],
        "furniture_change_descriptions": furniture.get("change_descriptions", []),
        "reply_draft_emails": draft_emails,
        "reply_alerts": alerts,
        "decision": "needs_review" if (draft_emails or alerts) else "approve",
        "reply_action": "changes_detected" if (draft_emails or alerts) else "normal_reply",
    }
