"""Tests for dynamic quote versioning system."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.quote_builder import (
    build_initial_quote,
    format_quote_for_email,
    update_quote,
)

client = TestClient(app)

AUTH_HEADERS = {"Authorization": f"Bearer {settings.langgraph_api_key}"} if settings.langgraph_api_key else {}


# ============================================================
# Unit tests: build_initial_quote
# ============================================================

class TestBuildInitialQuote:
    def test_external_tier_3hr(self):
        reservation = {
            "pricing_tier": "external",
            "requested_start_time": "09:00",
            "requested_end_time": "12:00",
            "event_type": "",
        }
        quote = build_initial_quote(reservation)
        assert quote["version"] == 1
        assert len(quote["line_items"]) >= 1
        facility = quote["line_items"][0]
        assert facility["service"] == "facility"
        # external = $100/hr, 3hr min → $300
        assert facility["total"] == 300.0
        assert quote["subtotal"] == 300.0
        assert quote["deposit_amount"] == 0.0

    def test_government_zero_cost(self):
        reservation = {
            "pricing_tier": "government_agency",
            "requested_start_time": "09:00",
            "requested_end_time": "12:00",
            "event_type": "",
        }
        quote = build_initial_quote(reservation)
        facility = quote["line_items"][0]
        assert facility["total"] == 0.0
        assert "no charge" in facility["description"]

    def test_acc_internal_zero_cost(self):
        reservation = {
            "pricing_tier": "acc_internal",
            "requested_start_time": "10:00",
            "requested_end_time": "14:00",
            "event_type": "",
        }
        quote = build_initial_quote(reservation)
        assert quote["subtotal"] == 0.0

    def test_a_event_facility_pricing_with_deposit(self):
        reservation = {
            "pricing_tier": "external",
            "requested_start_time": "08:00",
            "requested_end_time": "17:00",
            "event_type": "A-EVENT",
        }
        quote = build_initial_quote(reservation)
        facility = quote["line_items"][0]
        # 9 hours > 8 → Extended = $1250
        assert facility["total"] == 1250.0
        assert "Extended" in facility["description"]
        assert quote["deposit_amount"] == round(1250.0 * 0.05, 2)

    def test_a_event_full_day(self):
        reservation = {
            "pricing_tier": "external",
            "requested_start_time": "09:00",
            "requested_end_time": "15:00",
            "event_type": "A-EVENT",
        }
        quote = build_initial_quote(reservation)
        facility = quote["line_items"][0]
        # 6 hours > 4 → Full Day = $1000
        assert facility["total"] == 1000.0

    def test_a_event_half_day(self):
        reservation = {
            "pricing_tier": "external",
            "requested_start_time": "09:00",
            "requested_end_time": "12:00",
            "event_type": "A-EVENT",
        }
        quote = build_initial_quote(reservation)
        facility = quote["line_items"][0]
        # 3 hours ≤ 4 → Half Day Block = $500
        assert facility["total"] == 500.0

    def test_addon_detection_from_setup_config(self):
        reservation = {
            "pricing_tier": "external",
            "requested_start_time": "09:00",
            "requested_end_time": "12:00",
            "event_type": "",
            "setup_config": {"projector": True, "catering": True},
        }
        quote = build_initial_quote(reservation)
        services = [item["service"] for item in quote["line_items"]]
        assert "av_equipment" in services
        assert "catering_coordination" in services

    def test_nonprofit_tier(self):
        reservation = {
            "pricing_tier": "nonprofit",
            "requested_start_time": "10:00",
            "requested_end_time": "11:00",
            "event_type": "",
        }
        quote = build_initial_quote(reservation)
        facility = quote["line_items"][0]
        # $25/hr, min 2hr → $50
        assert facility["total"] == 50.0

    def test_empty_fields_produce_valid_quote(self):
        reservation = {}
        quote = build_initial_quote(reservation)
        assert quote["version"] == 1
        assert len(quote["line_items"]) >= 1
        assert quote["changes_from_previous"] is None

    def test_setup_config_as_json_string(self):
        reservation = {
            "pricing_tier": "external",
            "requested_start_time": "09:00",
            "requested_end_time": "12:00",
            "event_type": "",
            "setup_config": '{"projector": true}',
        }
        quote = build_initial_quote(reservation)
        services = [item["service"] for item in quote["line_items"]]
        assert "av_equipment" in services


# ============================================================
# Unit tests: update_quote
# ============================================================

class TestUpdateQuote:
    def _base_quote(self):
        return {
            "version": 1,
            "line_items": [
                {
                    "service": "facility",
                    "description": "Event Hall — Full Day",
                    "quantity": 1,
                    "unit_price": 1000.0,
                    "total": 1000.0,
                }
            ],
            "subtotal": 1000.0,
            "deposit_amount": 50.0,  # A-EVENT
            "total": 1000.0,
        }

    def test_add_single_service(self):
        quote = self._base_quote()
        new = update_quote(quote, add_services=[{"service": "av_technician"}])
        assert new["version"] == 2
        assert new["subtotal"] == 1160.0  # 1000 + 160
        assert new["changes_from_previous"]["added"][0]["service"] == "av_technician"
        assert new["changes_from_previous"]["difference"] == 160.0

    def test_remove_service(self):
        quote = self._base_quote()
        quote["line_items"].append({
            "service": "av_technician",
            "description": "ACC Technician",
            "quantity": 1,
            "unit_price": 160.0,
            "total": 160.0,
        })
        quote["subtotal"] = 1160.0
        quote["total"] = 1160.0

        new = update_quote(quote, remove_services=["av_technician"])
        assert new["subtotal"] == 1000.0
        assert len(new["changes_from_previous"]["removed"]) == 1
        assert new["changes_from_previous"]["difference"] == -160.0

    def test_add_multiple_services(self):
        quote = self._base_quote()
        new = update_quote(
            quote,
            add_services=[
                {"service": "av_equipment", "hours": 6},
                {"service": "av_webcast"},
                {"service": "av_technician"},
            ],
        )
        assert new["version"] == 2
        # 1000 + (60*6) + 100 + 160 = 1620
        assert new["subtotal"] == 1620.0
        assert len(new["changes_from_previous"]["added"]) == 3

    def test_police_minimum_hours(self):
        quote = self._base_quote()
        # Request 2 hours of police → should enforce 4hr minimum
        new = update_quote(quote, add_services=[{"service": "police", "hours": 2}])
        police_item = next(i for i in new["line_items"] if i["service"] == "police")
        assert police_item["quantity"] == 4  # minimum enforced
        assert police_item["total"] == 260.0  # 65 * 4

    def test_round_tables_with_count(self):
        quote = self._base_quote()
        new = update_quote(quote, add_services=[{"service": "round_tables", "count": 10}])
        tables_item = next(i for i in new["line_items"] if i["service"] == "round_tables")
        assert tables_item["quantity"] == 10
        assert tables_item["total"] == 150.0  # 15 * 10

    def test_deposit_preserved_for_a_event(self):
        quote = self._base_quote()  # has deposit > 0
        new = update_quote(quote, add_services=[{"service": "signage"}])
        assert new["deposit_amount"] == round(new["subtotal"] * 0.05, 2)

    def test_no_deposit_for_non_a_event(self):
        quote = self._base_quote()
        quote["deposit_amount"] = 0  # not A-EVENT
        new = update_quote(quote, add_services=[{"service": "signage"}])
        assert new["deposit_amount"] == 0


# ============================================================
# Unit tests: format_quote_for_email
# ============================================================

class TestFormatQuoteForEmail:
    def test_version_1_no_changes(self):
        quote = {
            "version": 1,
            "line_items": [
                {"service": "facility", "description": "Event Hall — Full Day", "quantity": 1, "unit_price": 1000.0, "total": 1000.0},
            ],
            "subtotal": 1000.0,
            "deposit_amount": 50.0,
            "total": 1000.0,
            "changes_from_previous": None,
        }
        text = format_quote_for_email(quote)
        assert "Version 1" in text
        assert "Event Hall" in text
        assert "1,000.00" in text
        assert "Deposit (5%)" in text
        assert "Changes from previous" not in text

    def test_version_2_with_changes(self):
        quote = {
            "version": 2,
            "line_items": [
                {"service": "facility", "description": "Event Hall — Full Day", "quantity": 1, "unit_price": 1000.0, "total": 1000.0},
                {"service": "av_technician", "description": "ACC Technician", "quantity": 1, "unit_price": 160.0, "total": 160.0},
            ],
            "subtotal": 1160.0,
            "deposit_amount": 0,
            "total": 1160.0,
            "changes_from_previous": {
                "added": [{"service": "av_technician", "description": "ACC Technician", "total": 160.0}],
                "removed": [],
                "previous_total": 1000.0,
                "new_total": 1160.0,
                "difference": 160.0,
            },
        }
        text = format_quote_for_email(quote)
        assert "Version 2" in text
        assert "NEW" in text
        assert "Changes from previous" in text
        assert "Added ACC Technician" in text
        assert "+$160.00" in text

    def test_no_deposit_line(self):
        quote = {
            "version": 1,
            "line_items": [
                {"service": "facility", "description": "Facility — government_agency (no charge)", "quantity": 1, "unit_price": 0.0, "total": 0.0},
            ],
            "subtotal": 0.0,
            "deposit_amount": 0,
            "total": 0.0,
            "changes_from_previous": None,
        }
        text = format_quote_for_email(quote)
        assert "Deposit" not in text


# ============================================================
# Endpoint tests
# ============================================================

MOCK_RESERVATION = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "request_id": "form-test123",
    "pricing_tier": "external",
    "requested_start_time": "09:00",
    "requested_end_time": "12:00",
    "event_type": "",
    "setup_config": None,
    "status": "pending_review",
}


class TestQuoteEndpoints:
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    @patch("app.main.create_quote_version", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_generate_quote(self, mock_get, mock_create, mock_audit):
        mock_get.return_value = MOCK_RESERVATION
        mock_create.return_value = "quote-uuid-1"

        response = client.post(
            "/api/v1/quote/generate/form-test123",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reservation_id"] == "form-test123"
        assert data["quote"]["version"] == 1
        assert len(data["quote"]["line_items"]) >= 1
        assert data["email_snippet"] != ""
        mock_create.assert_called_once()

    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_generate_quote_not_found(self, mock_get):
        mock_get.return_value = None

        response = client.post(
            "/api/v1/quote/generate/nonexistent",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 404

    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    @patch("app.main.create_quote_version", new_callable=AsyncMock)
    @patch("app.main.get_latest_quote", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_update_quote(self, mock_get, mock_latest, mock_create, mock_audit):
        mock_get.return_value = MOCK_RESERVATION
        mock_latest.return_value = {
            "id": "quote-uuid-1",
            "reservation_id": MOCK_RESERVATION["id"],
            "version": 1,
            "line_items": [
                {"service": "facility", "description": "Facility — external ($100/hr × 3.0 hrs)", "quantity": 3, "unit_price": 100.0, "total": 300.0},
            ],
            "subtotal": 300.0,
            "deposit_amount": 0,
            "total": 300.0,
        }
        mock_create.return_value = "quote-uuid-2"

        response = client.post(
            "/api/v1/quote/update/form-test123",
            headers=AUTH_HEADERS,
            json={
                "add_services": [
                    {"service": "av_technician"},
                    {"service": "av_equipment", "hours": 3},
                ],
                "remove_services": [],
                "notes": "Client needs AV for presentation",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["quote"]["version"] == 2
        assert data["changes"]["difference"] > 0
        assert data["email_snippet"] != ""

    @patch("app.main.get_latest_quote", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_update_quote_no_existing(self, mock_get, mock_latest):
        mock_get.return_value = MOCK_RESERVATION
        mock_latest.return_value = None

        response = client.post(
            "/api/v1/quote/update/form-test123",
            headers=AUTH_HEADERS,
            json={"add_services": [{"service": "signage"}]},
        )
        assert response.status_code == 404
        assert "Generate one first" in response.json()["detail"]

    @patch("app.main.get_quote_history", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_quote_history(self, mock_get, mock_history):
        mock_get.return_value = MOCK_RESERVATION
        mock_history.return_value = [
            {
                "id": "q1",
                "reservation_id": MOCK_RESERVATION["id"],
                "version": 1,
                "line_items": [{"service": "facility", "description": "Facility", "quantity": 1, "unit_price": 300, "total": 300}],
                "subtotal": 300,
                "deposit_amount": 0,
                "total": 300,
                "changes_from_previous": None,
                "notes": None,
                "created_by": "system",
                "created_at": "2026-03-01T00:00:00",
            },
            {
                "id": "q2",
                "reservation_id": MOCK_RESERVATION["id"],
                "version": 2,
                "line_items": [
                    {"service": "facility", "description": "Facility", "quantity": 1, "unit_price": 300, "total": 300},
                    {"service": "signage", "description": "Signage", "quantity": 1, "unit_price": 100, "total": 100},
                ],
                "subtotal": 400,
                "deposit_amount": 0,
                "total": 400,
                "changes_from_previous": {"added": [{"service": "signage", "description": "Signage", "total": 100}], "removed": [], "previous_total": 300, "new_total": 400, "difference": 100},
                "notes": None,
                "created_by": "admin",
                "created_at": "2026-03-02T00:00:00",
            },
        ]

        response = client.get(
            "/api/v1/quote/history/form-test123",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["current_version"] == 2
        assert len(data["versions"]) == 2

    @patch("app.main.get_latest_quote", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_quote_latest(self, mock_get, mock_latest):
        mock_get.return_value = MOCK_RESERVATION
        mock_latest.return_value = {
            "id": "q1",
            "reservation_id": MOCK_RESERVATION["id"],
            "version": 1,
            "line_items": [{"service": "facility", "description": "Facility", "quantity": 1, "unit_price": 300, "total": 300}],
            "subtotal": 300,
            "deposit_amount": 0,
            "total": 300,
            "changes_from_previous": None,
            "notes": None,
            "created_by": "system",
            "created_at": "2026-03-01T00:00:00",
        }

        response = client.get(
            "/api/v1/quote/latest/form-test123",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == 1
        assert data["total"] == 300

    @patch("app.main.get_latest_quote", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_quote_latest_not_found(self, mock_get, mock_latest):
        mock_get.return_value = MOCK_RESERVATION
        mock_latest.return_value = None

        response = client.get(
            "/api/v1/quote/latest/form-test123",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 404


class TestAutoQuoteOnEvaluate:
    @patch("app.main.create_quote_version", new_callable=AsyncMock)
    @patch("app.main.compiled_graph")
    @patch("app.main.create_reservation", new_callable=AsyncMock)
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    def test_evaluate_auto_generates_quote_on_approve(
        self, mock_audit, mock_create, mock_graph, mock_quote
    ):
        mock_graph.invoke.return_value = {
            "decision": "approve",
            "is_eligible": True,
            "eligibility_reason": "Government agency",
            "pricing_tier": "government_agency",
            "estimated_cost": 0.0,
            "room_assignment": "large_conference",
            "setup_config": {"chairs": 40},
            "draft_response": "Approved...",
            "errors": [],
        }
        mock_create.return_value = "test-uuid"
        mock_quote.return_value = "quote-uuid"

        response = client.post(
            "/api/v1/evaluate",
            headers={"X-Webhook-Secret": settings.webhook_secret} if settings.webhook_secret else {},
            json={
                "request_id": "form-quotegen",
                "requester_name": "Jane Doe",
                "requester_email": "jane@txgov.gov",
                "requester_organization": "Texas DOE",
                "event_name": "Staff Meeting",
                "requested_date": "2026-04-15",
                "requested_start_time": "09:00",
                "requested_end_time": "12:00",
                "calendar_available": True,
            },
        )

        assert response.status_code == 200
        mock_quote.assert_called_once()

    @patch("app.main.create_quote_version", new_callable=AsyncMock)
    @patch("app.main.compiled_graph")
    @patch("app.main.create_reservation", new_callable=AsyncMock)
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    def test_evaluate_no_quote_on_reject(
        self, mock_audit, mock_create, mock_graph, mock_quote
    ):
        mock_graph.invoke.return_value = {
            "decision": "reject",
            "is_eligible": False,
            "pricing_tier": None,
            "errors": [],
        }
        mock_create.return_value = "test-uuid"

        response = client.post(
            "/api/v1/evaluate",
            headers={"X-Webhook-Secret": settings.webhook_secret} if settings.webhook_secret else {},
            json={
                "request_id": "form-noquote",
                "requester_name": "Test",
                "requester_email": "test@test.com",
                "event_name": "Test",
                "requested_date": "2026-04-15",
                "requested_start_time": "09:00",
                "requested_end_time": "12:00",
                "calendar_available": True,
            },
        )

        assert response.status_code == 200
        mock_quote.assert_not_called()

    @patch("app.main.create_quote_version", new_callable=AsyncMock)
    @patch("app.main.compiled_graph")
    @patch("app.main.create_reservation", new_callable=AsyncMock)
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    def test_quote_failure_does_not_block_evaluate(
        self, mock_audit, mock_create, mock_graph, mock_quote
    ):
        mock_graph.invoke.return_value = {
            "decision": "approve",
            "pricing_tier": "external",
            "estimated_cost": 300.0,
            "errors": [],
        }
        mock_create.return_value = "test-uuid"
        mock_quote.side_effect = RuntimeError("DB down")

        response = client.post(
            "/api/v1/evaluate",
            headers={"X-Webhook-Secret": settings.webhook_secret} if settings.webhook_secret else {},
            json={
                "request_id": "form-quotefail",
                "requester_name": "Test",
                "requester_email": "test@test.com",
                "event_name": "Test",
                "requested_date": "2026-04-15",
                "requested_start_time": "09:00",
                "requested_end_time": "12:00",
                "calendar_available": True,
            },
        )

        # Evaluate should still succeed even if quote generation fails
        assert response.status_code == 200
        assert response.json()["decision"] == "approve"
