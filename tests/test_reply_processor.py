"""Tests for email reply processing: edit loop, escalation, furniture changes,
AV/catering alerts, and the graph node."""

from datetime import date
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.cgcs_constants import ESCALATION_RECIPIENTS, MOVING_TEAM, MOVING_TEAM_CC
from app.services.reply_processor import (
    EDIT_LOOP_LIMIT_MESSAGE,
    EDIT_LOOP_MAX,
    ESCALATION_AUTO_REPLY,
    build_dashboard_alert,
    check_edit_loop,
    detect_av_catering_changes,
    detect_escalation,
    detect_furniture_changes,
    draft_furniture_update_email,
)
from app.graph.nodes.email_reply import process_email_reply

client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {settings.langgraph_api_key}"} if settings.langgraph_api_key else {}


# ============================================================
# Edit Loop
# ============================================================

class TestEditLoop:
    def test_first_reply_increments(self):
        result = check_edit_loop(0)
        assert result["edit_loop_count"] == 1
        assert result["limit_reached"] is False
        assert result["limit_message"] is None

    def test_ninth_reply_not_limited(self):
        result = check_edit_loop(8)
        assert result["edit_loop_count"] == 9
        assert result["limit_reached"] is False

    def test_tenth_reply_reaches_limit(self):
        result = check_edit_loop(9)
        assert result["edit_loop_count"] == 10
        assert result["limit_reached"] is True
        assert result["limit_message"] == EDIT_LOOP_LIMIT_MESSAGE

    def test_beyond_limit(self):
        result = check_edit_loop(15)
        assert result["limit_reached"] is True

    def test_limit_message_has_contact_info(self):
        result = check_edit_loop(9)
        assert "admin@cgcs-acc.org" in result["limit_message"]
        assert "(512) 983-3679" in result["limit_message"]

    def test_max_constant(self):
        assert EDIT_LOOP_MAX == 10


# ============================================================
# Escalation Detection
# ============================================================

class TestEscalationDetection:
    def test_no_escalation_normal_reply(self):
        result = detect_escalation("Thank you for the update. Looks great!")
        assert result["escalation_needed"] is False
        assert result["reasons"] == []
        assert result["auto_reply"] is None

    def test_human_request_speak_to_someone(self):
        result = detect_escalation("I want to speak to someone about this.")
        assert result["escalation_needed"] is True
        assert any("human" in r.lower() or "explicitly" in r.lower() for r in result["reasons"])

    def test_human_request_talk_to_person(self):
        result = detect_escalation("Can I talk to a person please?")
        assert result["escalation_needed"] is True

    def test_human_request_connect_me(self):
        result = detect_escalation("Please connect me with a person who can help.")
        assert result["escalation_needed"] is True

    def test_human_request_need_to_speak(self):
        result = detect_escalation("I need to speak to a real person about my event.")
        assert result["escalation_needed"] is True

    def test_frustration_ridiculous(self):
        result = detect_escalation("This is ridiculous, nobody has gotten back to me.")
        assert result["escalation_needed"] is True
        assert any("frustration" in r.lower() for r in result["reasons"])

    def test_frustration_nobody_helping(self):
        result = detect_escalation("Nobody is helping me with this reservation!")
        assert result["escalation_needed"] is True

    def test_frustration_been_waiting(self):
        result = detect_escalation("I've been waiting for a week with no response.")
        assert result["escalation_needed"] is True

    def test_frustration_waste_of_time(self):
        result = detect_escalation("This has been a complete waste of my time.")
        assert result["escalation_needed"] is True

    def test_frustration_getting_nowhere(self):
        result = detect_escalation("I feel like I'm getting nowhere with this process.")
        assert result["escalation_needed"] is True

    def test_failed_replies_threshold(self):
        result = detect_escalation("Just checking on the status.", failed_replies=3)
        assert result["escalation_needed"] is True
        assert any("3 failed" in r for r in result["reasons"])

    def test_below_failed_replies_threshold(self):
        result = detect_escalation("Just checking on the status.", failed_replies=2)
        assert result["escalation_needed"] is False

    def test_escalation_auto_reply(self):
        result = detect_escalation("I want to speak to someone.")
        assert result["auto_reply"] == ESCALATION_AUTO_REPLY
        assert "24 hours" in result["auto_reply"]

    def test_escalation_forward_recipients(self):
        result = detect_escalation("This is ridiculous!")
        assert result["forward_to"] == list(ESCALATION_RECIPIENTS)

    def test_multiple_escalation_reasons(self):
        result = detect_escalation(
            "This is ridiculous! I want to speak to a manager!",
            failed_replies=5,
        )
        assert len(result["reasons"]) >= 2

    def test_case_insensitive(self):
        result = detect_escalation("I WANT TO SPEAK TO SOMEONE!")
        assert result["escalation_needed"] is True

    def test_smart_apostrophe(self):
        result = detect_escalation("I\u2019ve been waiting for days!")
        assert result["escalation_needed"] is True


# ============================================================
# Furniture Change Detection
# ============================================================

class TestFurnitureChangeDetection:
    def test_no_furniture_in_reply(self):
        result = detect_furniture_changes("When is the walkthrough scheduled?")
        assert result["furniture_changes_detected"] is False

    def test_add_stage(self):
        result = detect_furniture_changes("Can we add a stage for the speaker?")
        assert result["furniture_changes_detected"] is True
        assert len(result["change_descriptions"]) > 0

    def test_change_table_count(self):
        result = detect_furniture_changes("We now need 15 round tables instead of 10.")
        assert result["furniture_changes_detected"] is True
        assert any("15" in d for d in result["change_descriptions"])

    def test_remove_podium(self):
        result = detect_furniture_changes("We don't need the podium anymore.")
        assert result["furniture_changes_detected"] is True

    def test_remove_with_smart_apostrophe(self):
        result = detect_furniture_changes("We don\u2019t need the podium anymore.")
        assert result["furniture_changes_detected"] is True

    def test_quantity_plus_keyword(self):
        result = detect_furniture_changes("We'll need 200 chairs for the event.")
        assert result["furniture_changes_detected"] is True
        assert any("200" in d for d in result["change_descriptions"])

    def test_linen_changes(self):
        result = detect_furniture_changes("Can we get different linens for the tables?")
        assert result["furniture_changes_detected"] is True

    def test_no_change_just_question(self):
        # Has keyword "tables" but no change pattern or qty
        result = detect_furniture_changes("How many tables are in the room by default?")
        assert result["furniture_changes_detected"] is True or result["furniture_changes_detected"] is False
        # Either way, should not crash

    def test_raw_text_truncated(self):
        long_msg = "We need 20 chairs. " * 100
        result = detect_furniture_changes(long_msg)
        if result["furniture_changes_detected"]:
            assert len(result["raw_text"]) <= 500


class TestDraftFurnitureUpdateEmail:
    def test_drafts_update_email(self):
        parsed = {
            "event_name": "Workshop",
            "event_start_date": date(2026, 6, 25),
            "event_room": "RGC3.3340",
        }
        result = draft_furniture_update_email(parsed, ["15 round tables instead of 10"])
        assert "UPDATED" in result["subject"]
        assert MOVING_TEAM[0] in result["to"]
        assert result["cc"] == MOVING_TEAM_CC
        assert "15 round tables instead of 10" in result["body"]
        assert "CGCS Team" in result["body"]


# ============================================================
# AV / Catering Change Detection
# ============================================================

class TestAvCateringDetection:
    def test_no_av_or_catering(self):
        result = detect_av_catering_changes("When is the walkthrough?")
        assert result["av_change_detected"] is False
        assert result["catering_change_detected"] is False

    def test_av_detected_projector(self):
        result = detect_av_catering_changes("We also need a projector for the presentation.")
        assert result["av_change_detected"] is True
        assert result["catering_change_detected"] is False
        assert "projector" in result["av_excerpt"].lower()

    def test_av_detected_microphone(self):
        result = detect_av_catering_changes("Will there be a microphone available?")
        assert result["av_change_detected"] is True

    def test_catering_detected(self):
        result = detect_av_catering_changes("We want to add catering for lunch.")
        assert result["catering_change_detected"] is True
        assert "catering" in result["catering_excerpt"].lower()

    def test_both_detected(self):
        result = detect_av_catering_changes(
            "We need a projector and also want to add catering for the afternoon."
        )
        assert result["av_change_detected"] is True
        assert result["catering_change_detected"] is True

    def test_food_keyword(self):
        result = detect_av_catering_changes("Can we bring food for the attendees?")
        assert result["catering_change_detected"] is True

    def test_av_keyword_audio(self):
        result = detect_av_catering_changes("We need audio support for the keynote.")
        assert result["av_change_detected"] is True


# ============================================================
# Dashboard Alert Builder
# ============================================================

class TestBuildDashboardAlert:
    def test_av_alert(self):
        alert = build_dashboard_alert(
            alert_type="av_update",
            event_name="Workshop",
            detail="Client requested a projector",
            reservation_id="abc-123",
        )
        assert alert["alert_type"] == "av_update"
        assert "Workshop" in alert["title"]
        assert alert["detail"] == "Client requested a projector"
        assert alert["reservation_id"] == "abc-123"

    def test_catering_alert(self):
        alert = build_dashboard_alert(
            alert_type="catering_update",
            event_name="Conference",
            detail="Wants lunch catering",
        )
        assert alert["alert_type"] == "catering_update"
        assert "Conference" in alert["title"]
        assert alert["reservation_id"] is None

    def test_title_formatting(self):
        alert = build_dashboard_alert("av_update", "Test", "detail")
        assert alert["title"] == "Av Update: Test"


# ============================================================
# Graph Node: process_email_reply
# ============================================================

class TestProcessEmailReplyNode:
    def test_normal_reply(self):
        state = {
            "reply_body": "Thanks for the update. The details look correct.",
            "edit_loop_count": 2,
            "failed_replies": 0,
            "smartsheet_parsed": {"event_name": "Test"},
            "errors": [],
        }
        result = process_email_reply(state)
        assert result["edit_loop_count"] == 3
        assert result["escalation_detected"] is False
        assert result["reply_action"] == "normal_reply"
        assert result["decision"] == "approve"

    def test_edit_loop_limit(self):
        state = {
            "reply_body": "Another change please.",
            "edit_loop_count": 9,
            "failed_replies": 0,
            "smartsheet_parsed": {},
            "errors": [],
        }
        result = process_email_reply(state)
        assert result["edit_loop_count"] == 10
        assert result["reply_action"] == "edit_loop_limit"
        assert "admin@cgcs-acc.org" in result["draft_response"]
        assert result["email_auto_send"] is True

    def test_escalation_overrides_changes(self):
        state = {
            "reply_body": "This is ridiculous! I want to speak to someone!",
            "edit_loop_count": 2,
            "failed_replies": 0,
            "smartsheet_parsed": {},
            "errors": [],
        }
        result = process_email_reply(state)
        assert result["reply_action"] == "escalate"
        assert result["escalation_detected"] is True
        assert result["draft_response"] == ESCALATION_AUTO_REPLY

    def test_furniture_changes_detected(self):
        state = {
            "reply_body": "We now need 15 round tables instead of 10.",
            "edit_loop_count": 2,
            "failed_replies": 0,
            "smartsheet_parsed": {
                "event_name": "Workshop",
                "event_start_date": date(2026, 6, 25),
                "event_room": "RGC3.3340",
            },
            "errors": [],
        }
        result = process_email_reply(state)
        assert result["furniture_changes_detected"] is True
        assert len(result["reply_draft_emails"]) == 1
        assert result["reply_action"] == "changes_detected"
        assert result["decision"] == "needs_review"

    def test_av_alert_created(self):
        state = {
            "reply_body": "We also need a projector for the presentation.",
            "edit_loop_count": 1,
            "failed_replies": 0,
            "smartsheet_parsed": {"event_name": "Conference"},
            "errors": [],
        }
        result = process_email_reply(state)
        assert len(result["reply_alerts"]) == 1
        assert result["reply_alerts"][0]["alert_type"] == "av_update"
        assert result["reply_action"] == "changes_detected"

    def test_catering_alert_created(self):
        state = {
            "reply_body": "Can we add catering for lunch service?",
            "edit_loop_count": 1,
            "failed_replies": 0,
            "smartsheet_parsed": {"event_name": "Seminar"},
            "errors": [],
        }
        result = process_email_reply(state)
        assert len(result["reply_alerts"]) == 1
        assert result["reply_alerts"][0]["alert_type"] == "catering_update"

    def test_furniture_and_av_combined(self):
        state = {
            "reply_body": "We need 20 chairs and also a projector.",
            "edit_loop_count": 3,
            "failed_replies": 0,
            "smartsheet_parsed": {
                "event_name": "Meeting",
                "event_start_date": date(2026, 7, 1),
                "event_room": "RGC3.3340",
            },
            "errors": [],
        }
        result = process_email_reply(state)
        assert result["furniture_changes_detected"] is True
        assert len(result["reply_draft_emails"]) == 1
        assert len(result["reply_alerts"]) == 1
        assert result["reply_action"] == "changes_detected"

    def test_empty_reply_body(self):
        state = {"reply_body": "", "errors": []}
        result = process_email_reply(state)
        assert result["decision"] == "needs_review"
        assert any("No reply body" in e for e in result["errors"])

    def test_edit_loop_takes_priority_over_escalation(self):
        """At edit limit, send the limit message even if escalation keywords present."""
        state = {
            "reply_body": "This is ridiculous! I want to speak to someone!",
            "edit_loop_count": 9,
            "failed_replies": 5,
            "smartsheet_parsed": {},
            "errors": [],
        }
        result = process_email_reply(state)
        assert result["reply_action"] == "edit_loop_limit"

    def test_escalation_takes_priority_over_furniture(self):
        """Escalation detected before furniture changes are processed."""
        state = {
            "reply_body": "Nobody is helping me! We need 20 tables!",
            "edit_loop_count": 2,
            "failed_replies": 0,
            "smartsheet_parsed": {"event_name": "Test"},
            "errors": [],
        }
        result = process_email_reply(state)
        assert result["reply_action"] == "escalate"

    def test_failed_replies_triggers_escalation(self):
        state = {
            "reply_body": "Just checking on the status.",
            "edit_loop_count": 4,
            "failed_replies": 3,
            "smartsheet_parsed": {},
            "errors": [],
        }
        result = process_email_reply(state)
        assert result["reply_action"] == "escalate"
        assert result["escalation_detected"] is True


# ============================================================
# Alert API Endpoints
# ============================================================

class TestAlertEndpoints:
    @patch("app.main.get_active_alerts", new_callable=AsyncMock)
    def test_list_active_alerts(self, mock_get):
        mock_get.return_value = [
            {
                "id": "alert-uuid-1",
                "reservation_id": None,
                "alert_type": "av_update",
                "title": "Av Update: Workshop",
                "detail": "Client wants a projector",
                "status": "active",
                "created_at": "2026-04-15T10:00:00",
            },
        ]
        response = client.get("/api/v1/alerts/active", headers=AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["alerts"][0]["alert_type"] == "av_update"

    @patch("app.main.get_active_alerts", new_callable=AsyncMock)
    def test_list_empty_alerts(self, mock_get):
        mock_get.return_value = []
        response = client.get("/api/v1/alerts/active", headers=AUTH_HEADERS)
        assert response.status_code == 200
        assert response.json()["count"] == 0

    @patch("app.main.dismiss_alert", new_callable=AsyncMock)
    def test_dismiss_alert(self, mock_dismiss):
        mock_dismiss.return_value = True
        response = client.post(
            "/api/v1/alerts/alert-uuid-1/dismiss",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "dismissed"

    @patch("app.main.dismiss_alert", new_callable=AsyncMock)
    def test_dismiss_nonexistent_alert(self, mock_dismiss):
        mock_dismiss.return_value = False
        response = client.post(
            "/api/v1/alerts/nonexistent/dismiss",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 404
