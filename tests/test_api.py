"""Integration tests for FastAPI endpoints."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)

WEBHOOK_HEADERS = {"X-Webhook-Secret": settings.webhook_secret} if settings.webhook_secret else {}
AUTH_HEADERS = {"Authorization": f"Bearer {settings.langgraph_api_key}"} if settings.langgraph_api_key else {}


class TestHealthEndpoint:
    def test_health_returns_200(self):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestAuthSecurity:
    @patch("app.main.compiled_graph")
    @patch("app.main.create_reservation", new_callable=AsyncMock)
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    def test_evaluate_rejects_without_webhook_secret(
        self, mock_audit, mock_create, mock_graph
    ):
        if not settings.webhook_secret:
            return  # Skip if no secret configured
        response = client.post(
            "/api/v1/evaluate",
            json={
                "request_id": "form-test123",
                "requester_name": "Jane Doe",
                "requester_email": "jane@txgov.gov",
                "event_name": "Staff Meeting",
                "requested_date": "2026-04-15",
                "requested_start_time": "09:00",
                "requested_end_time": "12:00",
                "calendar_available": True,
            },
        )
        assert response.status_code == 401

    def test_approve_rejects_without_api_key(self):
        if not settings.langgraph_api_key:
            return
        response = client.post(
            "/api/v1/approve/form-test123",
            json={"action": "approve"},
        )
        assert response.status_code == 401

    def test_reservation_rejects_without_api_key(self):
        if not settings.langgraph_api_key:
            return
        response = client.get("/api/v1/reservation/form-test123")
        assert response.status_code == 401

    def test_dead_letter_rejects_without_api_key(self):
        if not settings.langgraph_api_key:
            return
        response = client.get("/api/v1/dead-letter")
        assert response.status_code == 401


class TestEvaluateEndpoint:
    @patch("app.main.compiled_graph")
    @patch("app.main.create_reservation", new_callable=AsyncMock)
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    def test_evaluate_returns_evaluation(
        self, mock_audit, mock_create, mock_graph
    ):
        mock_graph.invoke.return_value = {
            "decision": "approve",
            "is_eligible": True,
            "eligibility_reason": "Government agency",
            "pricing_tier": "government_agency",
            "estimated_cost": 0.0,
            "room_assignment": "large_conference",
            "setup_config": {"chairs": 40, "projector": True},
            "draft_response": "Dear Jane, your request is approved...",
            "errors": [],
        }
        mock_create.return_value = "test-uuid"

        response = client.post(
            "/api/v1/evaluate",
            headers=WEBHOOK_HEADERS,
            json={
                "request_id": "form-test123",
                "requester_name": "Jane Doe",
                "requester_email": "jane@txgov.gov",
                "requester_organization": "Texas DOE",
                "event_name": "Staff Meeting",
                "requested_date": "2026-04-15",
                "requested_start_time": "09:00",
                "requested_end_time": "12:00",
                "room_requested": "large_conference",
                "estimated_attendees": 35,
                "calendar_available": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "approve"
        assert data["request_id"] == "form-test123"
        assert data["is_eligible"] is True

    def test_evaluate_rejects_missing_fields(self):
        response = client.post(
            "/api/v1/evaluate",
            headers=WEBHOOK_HEADERS,
            json={"request_id": "test"},
        )
        assert response.status_code == 422

    def test_evaluate_rejects_invalid_request_id(self):
        response = client.post(
            "/api/v1/evaluate",
            headers=WEBHOOK_HEADERS,
            json={
                "request_id": "'; DROP TABLE reservations;--",
                "requester_name": "Jane Doe",
                "requester_email": "jane@txgov.gov",
                "event_name": "Staff Meeting",
                "requested_date": "2026-04-15",
                "requested_start_time": "09:00",
                "requested_end_time": "12:00",
                "calendar_available": True,
            },
        )
        assert response.status_code == 422

    @patch("app.main.compiled_graph")
    @patch("app.main.add_dead_letter", new_callable=AsyncMock)
    def test_evaluate_dead_letters_on_graph_failure(
        self, mock_dlq, mock_graph
    ):
        mock_graph.invoke.side_effect = RuntimeError("LLM service unavailable")
        mock_dlq.return_value = 1

        response = client.post(
            "/api/v1/evaluate",
            headers=WEBHOOK_HEADERS,
            json={
                "request_id": "form-fail123",
                "requester_name": "Jane Doe",
                "requester_email": "jane@txgov.gov",
                "event_name": "Staff Meeting",
                "requested_date": "2026-04-15",
                "requested_start_time": "09:00",
                "requested_end_time": "12:00",
                "calendar_available": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "needs_review"
        mock_dlq.assert_called_once()


class TestApproveEndpoint:
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    @patch("app.main.approve_reservation", new_callable=AsyncMock)
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    def test_approve_reservation(self, mock_audit, mock_approve, mock_get):
        mock_get.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "pending_review",
        }
        mock_approve.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "approved",
            "ai_draft_response": "Approved email draft",
            "requester_email": "jane@txgov.gov",
            "requester_name": "Jane Doe",
            "event_name": "Staff Meeting",
        }

        response = client.post(
            "/api/v1/approve/form-test123",
            headers=AUTH_HEADERS,
            json={"action": "approve", "admin_notes": "Looks good"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"

    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_approve_nonexistent_reservation(self, mock_get):
        mock_get.return_value = None

        response = client.post(
            "/api/v1/approve/nonexistent",
            headers=AUTH_HEADERS,
            json={"action": "approve"},
        )

        assert response.status_code == 404

    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_approve_already_approved(self, mock_get):
        mock_get.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "approved",
        }

        response = client.post(
            "/api/v1/approve/form-test123",
            headers=AUTH_HEADERS,
            json={"action": "approve"},
        )

        assert response.status_code == 400
        assert "already" in response.json()["detail"].lower()

    def test_approve_rejects_invalid_action(self):
        response = client.post(
            "/api/v1/approve/form-test123",
            headers=AUTH_HEADERS,
            json={"action": "maybe"},
        )
        assert response.status_code == 422


class TestReservationLookup:
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_get_reservation(self, mock_get):
        mock_get.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "pending_review",
            "requester_name": "Jane Doe",
        }

        response = client.get(
            "/api/v1/reservation/form-test123",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["request_id"] == "form-test123"

    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_get_nonexistent_reservation(self, mock_get):
        mock_get.return_value = None

        response = client.get(
            "/api/v1/reservation/nonexistent",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 404


class TestDeadLetterQueue:
    @patch("app.main.get_dead_letter_entries", new_callable=AsyncMock)
    def test_list_dead_letters(self, mock_dlq):
        mock_dlq.return_value = [
            {"id": 1, "request_id": "form-fail", "error_message": "timeout", "status": "pending"}
        ]

        response = client.get(
            "/api/v1/dead-letter",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1

    @patch("app.main.resolve_dead_letter", new_callable=AsyncMock)
    def test_resolve_dead_letter(self, mock_resolve):
        mock_resolve.return_value = True

        response = client.post(
            "/api/v1/dead-letter/1/resolve",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "resolved"


# ============================================================
# New endpoint tests
# ============================================================

class TestEmailTriageEndpoint:
    @patch("app.main.compiled_graph")
    def test_email_triage_returns_classification(self, mock_graph):
        mock_graph.invoke.return_value = {
            "email_priority": "medium",
            "email_category": "event_request",
            "email_draft_reply": "Thank you for your inquiry...",
            "email_auto_send": False,
            "decision": "needs_review",
            "errors": [],
        }

        response = client.post(
            "/api/v1/email/triage",
            headers=WEBHOOK_HEADERS,
            json={
                "email_from": "test@example.com",
                "email_subject": "Event space inquiry",
                "email_body": "I would like to reserve a room for a meeting.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email_category"] == "event_request"
        assert data["email_auto_send"] is False

    @patch("app.main.compiled_graph")
    def test_email_triage_auto_send_for_allowlisted(self, mock_graph):
        mock_graph.invoke.return_value = {
            "email_priority": "medium",
            "email_category": "question",
            "email_draft_reply": "Hello! Here is the info...",
            "email_auto_send": True,
            "decision": "approve",
            "errors": [],
        }

        response = client.post(
            "/api/v1/email/triage",
            headers=WEBHOOK_HEADERS,
            json={
                "email_from": "stefano.casafrancalaos@austincc.edu",
                "email_subject": "Quick question",
                "email_body": "What are your hours?",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email_auto_send"] is True


class TestCalendarEndpoints:
    @patch("app.main.compiled_graph")
    def test_calendar_check(self, mock_graph):
        mock_graph.invoke.return_value = {
            "calendar_is_available": True,
            "calendar_events": [],
            "decision": "approve",
            "errors": [],
        }

        response = client.post(
            "/api/v1/calendar/check",
            headers=WEBHOOK_HEADERS,
            json={
                "date": "2026-04-15",
                "start_time": "09:00",
                "end_time": "12:00",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_available"] is True

    @patch("app.main.compiled_graph")
    def test_calendar_hold(self, mock_graph):
        mock_graph.invoke.return_value = {
            "hold_event_id": "google-event-123",
            "decision": "approve",
            "draft_response": "Calendar hold created: HOLD - Test Org - 2026-04-15",
            "errors": [],
        }

        response = client.post(
            "/api/v1/calendar/hold",
            headers=AUTH_HEADERS,
            json={
                "org_name": "Test Org",
                "date": "2026-04-15",
                "start_time": "09:00",
                "end_time": "12:00",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["hold_event_id"] == "google-event-123"


class TestPetTrackerEndpoints:
    @patch("app.main.compiled_graph")
    def test_pet_query(self, mock_graph):
        mock_graph.invoke.return_value = {
            "pet_result": {"headers": ["Name", "Status"], "rows": [["Event A", "Active"]]},
            "decision": "approve",
            "errors": [],
        }

        response = client.post(
            "/api/v1/pet/query",
            headers=AUTH_HEADERS,
            json={"query": "Event A"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["rows"][0][0] == "Event A"

    @patch("app.main.compiled_graph")
    def test_pet_update_staging(self, mock_graph):
        mock_graph.invoke.return_value = {
            "pet_result": {"staged_id": "abc12345", "status": "staged"},
            "requires_approval": True,
            "decision": "needs_review",
            "errors": [],
        }

        response = client.post(
            "/api/v1/pet/update",
            headers=AUTH_HEADERS,
            json={"row_data": {"Name": "Event A", "Status": "Complete"}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["staged_id"] == "abc12345"
        assert data["requires_approval"] is True


class TestLeadEndpoints:
    @patch("app.main.compiled_graph")
    def test_assign_lead(self, mock_graph):
        mock_graph.invoke.return_value = {
            "lead_staff_name": "John Smith",
            "lead_staff_email": "john@austincc.edu",
            "lead_reservation_id": "form-test123",
            "reminders_due": [
                {"reminder_type": "30_day", "remind_date": "2026-03-16"},
                {"reminder_type": "14_day", "remind_date": "2026-04-01"},
            ],
            "decision": "approve",
            "draft_response": "Event lead assigned",
            "errors": [],
        }

        response = client.post(
            "/api/v1/leads/assign",
            headers=AUTH_HEADERS,
            json={
                "staff_name": "John Smith",
                "staff_email": "john@austincc.edu",
                "reservation_id": "form-test123",
                "event_date": "2026-04-15",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["staff_name"] == "John Smith"
        assert data["reminders_scheduled"] == 2


class TestReminderEndpoints:
    @patch("app.main.compiled_graph")
    def test_check_reminders(self, mock_graph):
        mock_graph.invoke.return_value = {
            "decision": "approve",
            "draft_response": "No reminders due at this time.",
            "errors": [],
        }

        response = client.post(
            "/api/v1/reminders/check",
            headers=WEBHOOK_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "approve"
