"""Tests for N8N webhook endpoints, error handler, and updated daily digest."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.error_handler import classify_error, build_error_alert
from app.graph.nodes.daily_digest import build_daily_digest
from app.services.reply_processor import EDIT_LOOP_MAX

client = TestClient(app)
WEBHOOK_HEADERS = {"X-Webhook-Secret": settings.webhook_secret} if settings.webhook_secret else {}
AUTH_HEADERS = {"Authorization": f"Bearer {settings.langgraph_api_key}"} if settings.langgraph_api_key else {}


# ============================================================
# Error Classification
# ============================================================

class TestErrorClassification:
    def test_timeout_is_retryable(self):
        result = classify_error(TimeoutError("Connection timeout"))
        assert result["error_type"] == "retryable"
        assert result["should_dlq"] is False
        assert result["should_alert"] is False

    def test_rate_limit_is_retryable(self):
        result = classify_error("429 Too Many Requests")
        assert result["error_type"] == "retryable"

    def test_503_is_retryable(self):
        result = classify_error("503 Service Unavailable")
        assert result["error_type"] == "retryable"

    def test_connection_refused_is_retryable(self):
        result = classify_error(ConnectionError("Connection refused"))
        assert result["error_type"] == "retryable"

    def test_validation_error_is_fatal(self):
        result = classify_error(ValueError("Invalid date format"))
        assert result["error_type"] == "fatal"
        assert result["should_dlq"] is True
        assert result["should_alert"] is True

    def test_key_error_is_fatal(self):
        result = classify_error(KeyError("missing_field"))
        assert result["error_type"] == "fatal"

    def test_unknown_error_is_fatal(self):
        result = classify_error(RuntimeError("Something went wrong"))
        assert result["error_type"] == "fatal"

    def test_error_message_preserved(self):
        result = classify_error(ValueError("bad input"))
        assert "bad input" in result["error_message"]

    def test_error_class_captured(self):
        result = classify_error(TypeError("wrong type"))
        assert result["error_class"] == "TypeError"

    def test_string_error(self):
        result = classify_error("some generic error")
        assert result["error_class"] == "str"


class TestBuildErrorAlert:
    def test_alert_structure(self):
        alert = build_error_alert(ValueError("bad"), "intake processing", "req-123")
        assert alert["alert_type"] == "pipeline_error"
        assert "intake processing" in alert["title"]
        assert "bad" in alert["detail"]
        assert alert["reservation_id"] == "req-123"

    def test_alert_without_request_id(self):
        alert = build_error_alert("timeout error", "email reply")
        assert alert["reservation_id"] is None


# ============================================================
# Smartsheet Webhook
# ============================================================

class TestSmartsheetWebhook:
    def test_rejects_non_smartsheet_email(self):
        response = client.post(
            "/webhook/smartsheet-new-entry",
            headers=WEBHOOK_HEADERS,
            json={
                "subject": "Re: Meeting tomorrow",
                "body": "See you there",
                "sender": "user@gmail.com",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "skipped"

    @patch("app.main.compiled_graph")
    def test_full_pipeline_success(self, mock_graph):
        mock_graph.invoke.return_value = {
            "intake_difficulty": "easy",
            "email_auto_send": True,
            "draft_response": "Thank you for your request...",
            "intake_draft_emails": [{"to": "test@test.com", "body": "..."}],
        }

        response = client.post(
            "/webhook/smartsheet-new-entry",
            headers=WEBHOOK_HEADERS,
            json={
                "subject": "Notice of Event Space Request - Center for Government and Civic Service - RGC | Test Event | 12/15/26 | 9:00 AM-5:00 PM",
                "body": (
                    "REQUESTOR - Event Requestor Name - Test Person "
                    "- Request Type - Internal Request "
                    "- Event Requestor Email - test@austincc.edu "
                    "EVENT - Event Code - 9999 "
                    "- Event Name - Test Event "
                    "- Event Date: 12/15/26 (1 Day) "
                    "- Event Start Time - 9:00 AM "
                    "- Event End Time - 5:00 PM "
                    "CGCS Dashboard Link: https://app.smartsheet.com/b/publish?EQBCT=abc123 "
                    "Thank you, Events Team"
                ),
                "sender": "automations@app.smartsheet.com",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["difficulty"] == "easy"

    def test_14_day_rejection(self):
        # Event date is tomorrow — should be rejected
        import datetime
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%m/%d/%y")

        response = client.post(
            "/webhook/smartsheet-new-entry",
            headers=WEBHOOK_HEADERS,
            json={
                "subject": f"Notice of Event Space Request - Center for Government and Civic Service - RGC | Urgent Event | {tomorrow} | 9:00 AM-5:00 PM",
                "body": (
                    f"REQUESTOR - Event Requestor Name - Test "
                    f"- Request Type - Internal Request "
                    f"- Event Requestor Email - test@austincc.edu "
                    f"EVENT - Event Name - Urgent Event "
                    f"- Event Date: {tomorrow} (1 Day) "
                    f"- Event Start Time - 9:00 AM "
                    f"- Event End Time - 5:00 PM "
                    f"Thank you"
                ),
                "sender": "automations@app.smartsheet.com",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert "14" in data["reason"] or "business days" in data["reason"]


# ============================================================
# Email Reply Webhook
# ============================================================

class TestEmailReplyWebhook:
    @patch("app.main.compiled_graph")
    @patch("app.main.create_alert", new_callable=AsyncMock)
    def test_normal_reply(self, mock_alert, mock_graph):
        mock_graph.invoke.return_value = {
            "reply_action": "normal_reply",
            "edit_loop_count": 3,
            "escalation_detected": False,
            "draft_response": "Thank you...",
            "reply_draft_emails": [],
            "reply_alerts": [],
            "decision": "approve",
        }

        response = client.post(
            "/webhook/email-reply",
            headers=WEBHOOK_HEADERS,
            json={
                "thread_id": "thread-abc",
                "reply_body": "Looks good, thanks!",
                "sender": "test@example.com",
                "edit_loop_count": 2,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["action"] == "normal_reply"
        assert data["edit_loop_count"] == 3

    @patch("app.main.compiled_graph")
    @patch("app.main.create_alert", new_callable=AsyncMock)
    def test_reply_with_av_alert(self, mock_alert, mock_graph):
        mock_graph.invoke.return_value = {
            "reply_action": "changes_detected",
            "edit_loop_count": 2,
            "escalation_detected": False,
            "reply_draft_emails": [],
            "reply_alerts": [
                {"alert_type": "av_update", "title": "AV Update: Test", "detail": "needs projector"},
            ],
            "decision": "needs_review",
        }

        response = client.post(
            "/webhook/email-reply",
            headers=WEBHOOK_HEADERS,
            json={
                "thread_id": "thread-abc",
                "reply_body": "We also need a projector.",
                "sender": "test@example.com",
            },
        )

        assert response.status_code == 200
        assert response.json()["alerts_created"] == 1
        mock_alert.assert_called_once()


# ============================================================
# Admin Response Webhook
# ============================================================

class TestAdminResponseWebhook:
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    def test_approve(self, mock_audit):
        response = client.post(
            "/webhook/admin-response",
            headers=WEBHOOK_HEADERS,
            json={"email_id": "email-123", "action": "approve"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    def test_reject(self, mock_audit):
        response = client.post(
            "/webhook/admin-response",
            headers=WEBHOOK_HEADERS,
            json={"email_id": "email-123", "action": "reject"},
        )
        assert response.status_code == 200
        assert response.json()["action"] == "reject"

    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    def test_edit(self, mock_audit):
        response = client.post(
            "/webhook/admin-response",
            headers=WEBHOOK_HEADERS,
            json={
                "email_id": "email-123",
                "action": "edit",
                "edited_text": "Updated draft text",
            },
        )
        assert response.status_code == 200
        assert response.json()["edited"] is True

    def test_invalid_action(self):
        response = client.post(
            "/webhook/admin-response",
            headers=WEBHOOK_HEADERS,
            json={"email_id": "email-123", "action": "maybe"},
        )
        assert response.status_code == 422


# ============================================================
# Police Confirmed Webhook
# ============================================================

class TestPoliceConfirmedWebhook:
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    def test_confirmation(self, mock_audit):
        response = client.post(
            "/webhook/police-confirmed",
            headers=WEBHOOK_HEADERS,
            json={
                "reply_body": "Confirmed, we can provide coverage for June 27.",
                "sender": "james.ortiz@austincc.edu",
                "request_id": "ss-abc123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert data["sender"] == "james.ortiz@austincc.edu"
        mock_audit.assert_called_once()


# ============================================================
# Updated Daily Digest
# ============================================================

class TestUpdatedDailyDigest:
    def test_has_11_sections(self):
        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_active_alerts": [],
            "digest_edit_loop_threads": [],
            "digest_monthly_stats": {},
            "digest_intern_leads": {},
            "errors": [],
        }
        result = build_daily_digest(state)
        body = result["draft_response"]
        # Check all 11 numbered sections exist
        for i in range(1, 12):
            assert f"## {i}." in body, f"Section {i} missing from digest"

    def test_active_alerts_section(self):
        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_active_alerts": [
                {"alert_type": "av_update", "title": "AV Update: Workshop", "detail": "Needs projector"},
            ],
            "digest_edit_loop_threads": [],
            "digest_monthly_stats": {},
            "digest_intern_leads": {},
            "errors": [],
        }
        result = build_daily_digest(state)
        body = result["draft_response"]
        assert "ACTIVE DASHBOARD ALERTS" in body
        assert "AV Update: Workshop" in body
        assert "Needs projector" in body

    def test_edit_loop_section(self):
        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_active_alerts": [],
            "digest_edit_loop_threads": [
                {"event_name": "Big Conference", "edit_loop_count": 8, "thread_id": "thread-xyz"},
            ],
            "digest_monthly_stats": {},
            "digest_intern_leads": {},
            "errors": [],
        }
        result = build_daily_digest(state)
        body = result["draft_response"]
        assert "EDIT LOOP STATUS" in body
        assert "Big Conference" in body
        assert f"8/{EDIT_LOOP_MAX}" in body
        assert "APPROACHING LIMIT" in body

    def test_edit_loop_no_warning_when_far(self):
        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_active_alerts": [],
            "digest_edit_loop_threads": [
                {"event_name": "Workshop", "edit_loop_count": 3, "thread_id": "thread-abc"},
            ],
            "digest_monthly_stats": {},
            "digest_intern_leads": {},
            "errors": [],
        }
        result = build_daily_digest(state)
        body = result["draft_response"]
        assert "APPROACHING LIMIT" not in body

    def test_intern_leads_section(self):
        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_active_alerts": [],
            "digest_edit_loop_threads": [],
            "digest_monthly_stats": {},
            "digest_intern_leads": {
                "Brenden Fogg": 2,
                "Catherine Thomason": 3,
            },
            "errors": [],
        }
        result = build_daily_digest(state)
        body = result["draft_response"]
        assert "EVENT LEADS PER INTERN" in body
        assert "Brenden Fogg: 2/3" in body
        assert "Catherine Thomason: 3/3" in body
        assert "AT CAP" in body

    def test_intern_leads_default_to_zero(self):
        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_active_alerts": [],
            "digest_edit_loop_threads": [],
            "digest_monthly_stats": {},
            "digest_intern_leads": {},
            "errors": [],
        }
        result = build_daily_digest(state)
        body = result["draft_response"]
        assert "Brenden Fogg: 0/3" in body
        assert "Vanessa Trujano: 0/3" in body

    def test_budget_tracking_with_data(self):
        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_active_alerts": [],
            "digest_edit_loop_threads": [],
            "digest_monthly_stats": {
                "events_this_month": 12,
                "revenue_this_month": 5250.00,
                "pending_approvals": 3,
                "on_time_checklist_rate": 87.5,
            },
            "digest_intern_leads": {},
            "errors": [],
        }
        result = build_daily_digest(state)
        body = result["draft_response"]
        assert "BUDGET TRACKING" in body
        assert "$5,250.00" in body
        assert "87.5%" in body

    def test_checklist_status_in_upcoming_events(self):
        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [
                {
                    "date": "2026-06-25",
                    "event_name": "Workshop",
                    "lead": "Brenden Fogg",
                    "status": "approved",
                    "checklist_complete_pct": 60,
                },
            ],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_active_alerts": [],
            "digest_edit_loop_threads": [],
            "digest_monthly_stats": {},
            "digest_intern_leads": {},
            "errors": [],
        }
        result = build_daily_digest(state)
        body = result["draft_response"]
        assert "Checklist: 60%" in body

    def test_deadline_reference_still_present(self):
        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_active_alerts": [],
            "digest_edit_loop_threads": [],
            "digest_monthly_stats": {},
            "digest_intern_leads": {},
            "errors": [],
        }
        result = build_daily_digest(state)
        body = result["draft_response"]
        assert "DEADLINE REFERENCE" in body
        assert "TDX AV Request: 15 business days" in body
