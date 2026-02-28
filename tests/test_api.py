"""Integration tests for FastAPI endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


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
            json={"request_id": "test"},
        )
        assert response.status_code == 422


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
            json={"action": "approve"},
        )

        assert response.status_code == 400
        assert "already" in response.json()["detail"].lower()


class TestReservationLookup:
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_get_reservation(self, mock_get):
        mock_get.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "pending_review",
            "requester_name": "Jane Doe",
        }

        response = client.get("/api/v1/reservation/form-test123")
        assert response.status_code == 200
        assert response.json()["request_id"] == "form-test123"

    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_get_nonexistent_reservation(self, mock_get):
        mock_get.return_value = None

        response = client.get("/api/v1/reservation/nonexistent")
        assert response.status_code == 404
