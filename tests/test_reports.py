"""Tests for revenue tracking and reporting endpoints."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)

AUTH_HEADERS = {"Authorization": f"Bearer {settings.langgraph_api_key}"} if settings.langgraph_api_key else {}


class TestCompleteReservation:
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    @patch("app.main.complete_reservation", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_complete_approved_reservation(self, mock_get, mock_complete, mock_audit):
        mock_get.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "approved",
        }
        mock_complete.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "completed",
            "actual_revenue": 5500.00,
            "actual_attendance": 120,
            "event_department": "CGCS",
            "completed_at": "2026-03-15T10:00:00+00:00",
        }

        response = client.post(
            "/api/v1/reservation/form-test123/complete",
            headers=AUTH_HEADERS,
            json={
                "actual_revenue": 5500.00,
                "actual_attendance": 120,
                "notes": "Great event",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["actual_revenue"] == 5500.00
        assert data["actual_attendance"] == 120
        mock_audit.assert_called_once()

    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_complete_nonexistent_reservation(self, mock_get):
        mock_get.return_value = None

        response = client.post(
            "/api/v1/reservation/nonexistent/complete",
            headers=AUTH_HEADERS,
            json={"actual_revenue": 100.00},
        )

        assert response.status_code == 404

    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_complete_pending_reservation_fails(self, mock_get):
        mock_get.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "pending_review",
        }

        response = client.post(
            "/api/v1/reservation/form-test123/complete",
            headers=AUTH_HEADERS,
            json={"actual_revenue": 100.00},
        )

        assert response.status_code == 400
        assert "approved" in response.json()["detail"].lower()

    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_complete_rejected_reservation_fails(self, mock_get):
        mock_get.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "rejected",
        }

        response = client.post(
            "/api/v1/reservation/form-test123/complete",
            headers=AUTH_HEADERS,
            json={"actual_revenue": 100.00},
        )

        assert response.status_code == 400

    def test_complete_rejects_without_api_key(self):
        if not settings.langgraph_api_key:
            return
        response = client.post(
            "/api/v1/reservation/form-test123/complete",
            json={"actual_revenue": 100.00},
        )
        assert response.status_code == 401


class TestRevenueReport:
    @patch("app.main.get_revenue_report", new_callable=AsyncMock)
    def test_revenue_report_monthly(self, mock_report):
        mock_report.return_value = {
            "period": "month",
            "start": "2026-03-01",
            "end": "2026-04-01",
            "total_events": 5,
            "total_revenue": 2500.00,
            "avg_revenue": 500.00,
            "total_attendance": 200,
            "avg_attendance": 40.0,
            "breakdown_by_type": [
                {"event_type": "A-EVENT", "event_count": 3, "revenue": 2500.00, "attendance": 150},
                {"event_type": "S-EVENT", "event_count": 2, "revenue": 0.0, "attendance": 50},
            ],
        }

        response = client.get(
            "/api/v1/reports/revenue?period=month&start=2026-03-01",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_events"] == 5
        assert data["total_revenue"] == 2500.00
        assert len(data["breakdown_by_type"]) == 2

    def test_revenue_report_invalid_date(self):
        response = client.get(
            "/api/v1/reports/revenue?period=month&start=bad-date",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400

    def test_revenue_report_invalid_period(self):
        response = client.get(
            "/api/v1/reports/revenue?period=decade&start=2026-03-01",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400


class TestConversionFunnel:
    @patch("app.main.get_conversion_funnel", new_callable=AsyncMock)
    def test_conversion_funnel_quarterly(self, mock_funnel):
        mock_funnel.return_value = {
            "period": "quarter",
            "start": "2026-01-01",
            "end": "2026-04-01",
            "total_submitted": 20,
            "pending": 2,
            "approved": 12,
            "completed": 8,
            "rejected": 4,
            "cancelled": 2,
            "approval_rate": 60.0,
            "completion_rate": 40.0,
        }

        response = client.get(
            "/api/v1/reports/conversion-funnel?period=quarter&start=2026-01-01",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_submitted"] == 20
        assert data["approval_rate"] == 60.0
        assert data["completion_rate"] == 40.0


class TestExportReport:
    @patch("app.main.get_reservations_for_export", new_callable=AsyncMock)
    def test_csv_export(self, mock_export):
        mock_export.return_value = [
            {
                "request_id": "form-1",
                "requester_name": "Jane Doe",
                "requester_email": "jane@txgov.gov",
                "requester_organization": "Texas DOE",
                "event_name": "A-EVENT-Meeting",
                "requested_date": "2026-03-15",
                "status": "completed",
                "actual_revenue": 500.00,
                "actual_attendance": 45,
            },
        ]

        response = client.get(
            "/api/v1/reports/export?format=csv&period=month&start=2026-03-01",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "form-1" in response.text
        assert "Jane Doe" in response.text

    @patch("app.main.get_reservations_for_export", new_callable=AsyncMock)
    def test_csv_export_empty(self, mock_export):
        mock_export.return_value = []

        response = client.get(
            "/api/v1/reports/export?format=csv&period=month&start=2026-03-01",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        assert "No data" in response.text

    def test_export_unsupported_format(self):
        response = client.get(
            "/api/v1/reports/export?format=pdf&period=month&start=2026-03-01",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400


class TestTopOrganizations:
    @patch("app.main.get_top_organizations", new_callable=AsyncMock)
    def test_top_organizations(self, mock_top):
        mock_top.return_value = [
            {
                "organization": "Texas DOE",
                "total_bookings": 5,
                "completed_bookings": 4,
                "total_revenue": 2000.00,
                "total_attendance": 180,
            },
            {
                "organization": "Austin ISD",
                "total_bookings": 3,
                "completed_bookings": 2,
                "total_revenue": 800.00,
                "total_attendance": 90,
            },
        ]

        response = client.get(
            "/api/v1/reports/top-organizations?period=quarter&start=2026-01-01&limit=10",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["organizations"]) == 2
        assert data["organizations"][0]["organization"] == "Texas DOE"
        assert data["limit"] == 10

    def test_top_organizations_invalid_limit(self):
        response = client.get(
            "/api/v1/reports/top-organizations?period=quarter&start=2026-01-01&limit=0",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 400
