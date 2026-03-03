"""Tests for event compliance checklist system."""

from datetime import date
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.cgcs_constants import (
    build_checklist_for_event,
    calculate_business_days_before,
)
from app.config import settings
from app.graph.nodes.daily_digest import build_daily_digest
from app.main import app

client = TestClient(app)

AUTH_HEADERS = {"Authorization": f"Bearer {settings.langgraph_api_key}"} if settings.langgraph_api_key else {}


# ============================================================
# Unit tests: business day calculation
# ============================================================

class TestCalculateBusinessDays:
    def test_basic_subtraction(self):
        # Wednesday 2026-04-15 minus 5 business days = Thursday 2026-04-08
        result = calculate_business_days_before(date(2026, 4, 15), 5)
        assert result == date(2026, 4, 8)

    def test_skips_weekends(self):
        # Monday 2026-04-13 minus 1 business day = Friday 2026-04-10
        result = calculate_business_days_before(date(2026, 4, 13), 1)
        assert result == date(2026, 4, 10)

    def test_zero_days(self):
        result = calculate_business_days_before(date(2026, 4, 15), 0)
        assert result == date(2026, 4, 15)

    def test_result_is_weekday(self):
        # Any result should be a weekday (Mon-Fri)
        for bd in range(1, 30):
            result = calculate_business_days_before(date(2026, 6, 15), bd)
            assert result.weekday() < 5, f"{bd} business days before gave weekend: {result}"

    def test_ten_business_days(self):
        # Wednesday 2026-04-15 minus 10 BD = Wednesday 2026-04-01
        result = calculate_business_days_before(date(2026, 4, 15), 10)
        assert result == date(2026, 4, 1)


# ============================================================
# Unit tests: checklist generation with conditions
# ============================================================

class TestBuildChecklistForEvent:
    def _base_reservation(self, **overrides):
        base = {
            "event_name": "S-EVENT-Staff Meeting",
            "requested_date": date(2026, 4, 15),
            "requested_end_time": "16:00",
            "pricing_tier": "government_agency",
        }
        base.update(overrides)
        return base

    def test_always_included_items(self):
        res = self._base_reservation()
        items = build_checklist_for_event(res)
        keys = [i["item_key"] for i in items]
        assert "user_agreement" in keys
        assert "furniture_layout" in keys
        assert "catering_plan" in keys
        assert "run_of_show" in keys
        assert "walkthrough" in keys
        assert "tdx_av_request" in keys
        assert "parking_confirmed" in keys

    def test_a_event_only_included_for_a_event(self):
        res = self._base_reservation(event_name="A-EVENT-Gala")
        items = build_checklist_for_event(res)
        keys = [i["item_key"] for i in items]
        assert "payment_received" in keys

    def test_a_event_only_excluded_for_s_event(self):
        res = self._base_reservation(event_name="S-EVENT-Meeting")
        items = build_checklist_for_event(res)
        keys = [i["item_key"] for i in items]
        assert "payment_received" not in keys

    def test_weekend_condition(self):
        # Saturday 2026-04-18
        res = self._base_reservation(requested_date=date(2026, 4, 18))
        items = build_checklist_for_event(res)
        keys = [i["item_key"] for i in items]
        assert "police_security" in keys

    def test_evening_condition(self):
        res = self._base_reservation(requested_end_time="19:00")
        items = build_checklist_for_event(res)
        keys = [i["item_key"] for i in items]
        assert "police_security" in keys

    def test_police_excluded_for_weekday_daytime(self):
        # Wednesday, ends at 16:00
        res = self._base_reservation(
            requested_date=date(2026, 4, 15),
            requested_end_time="16:00",
        )
        items = build_checklist_for_event(res)
        keys = [i["item_key"] for i in items]
        assert "police_security" not in keys

    def test_external_only_included(self):
        res = self._base_reservation(pricing_tier="external")
        items = build_checklist_for_event(res)
        keys = [i["item_key"] for i in items]
        assert "insurance_docs" in keys

    def test_external_only_excluded_for_internal(self):
        res = self._base_reservation(pricing_tier="acc_internal")
        items = build_checklist_for_event(res)
        keys = [i["item_key"] for i in items]
        assert "insurance_docs" not in keys

    def test_deadline_dates_calculated(self):
        res = self._base_reservation(requested_date=date(2026, 4, 15))
        items = build_checklist_for_event(res)
        for item in items:
            assert "deadline_date" in item
            assert isinstance(item["deadline_date"], date)

    def test_user_agreement_deadline_is_event_date(self):
        # deadline_bd=0 means deadline is the event date itself
        res = self._base_reservation(requested_date=date(2026, 4, 15))
        items = build_checklist_for_event(res)
        ua = next(i for i in items if i["item_key"] == "user_agreement")
        assert ua["deadline_date"] == date(2026, 4, 15)

    def test_string_date_parsing(self):
        res = self._base_reservation(requested_date="2026-04-15")
        items = build_checklist_for_event(res)
        assert len(items) > 0

    def test_missing_date_returns_empty(self):
        res = self._base_reservation(requested_date=None)
        items = build_checklist_for_event(res)
        assert items == []


# ============================================================
# Endpoint tests
# ============================================================

class TestGetChecklist:
    @patch("app.main.get_checklist", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_get_checklist(self, mock_get_res, mock_get_cl):
        mock_get_res.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
        }
        mock_get_cl.return_value = [
            {
                "id": "item-uuid-1",
                "item_key": "user_agreement",
                "item_label": "User Agreement Signed",
                "required": True,
                "status": "completed",
                "deadline_date": date(2026, 4, 15),
                "completed_at": "2026-04-10T10:00:00+00:00",
                "completed_by": "admin",
                "notes": None,
            },
            {
                "id": "item-uuid-2",
                "item_key": "catering_plan",
                "item_label": "Catering Plan Submitted",
                "required": True,
                "status": "pending",
                "deadline_date": date(2025, 1, 15),
                "completed_at": None,
                "completed_by": None,
                "notes": None,
            },
        ]

        response = client.get(
            "/api/v1/checklist/form-test123",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["completed"] == 1
        assert data["pending"] == 1
        # catering_plan should be overdue (deadline in the past)
        catering = next(i for i in data["items"] if i["item_key"] == "catering_plan")
        assert catering["is_overdue"] is True

    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_get_checklist_not_found(self, mock_get_res):
        mock_get_res.return_value = None
        response = client.get(
            "/api/v1/checklist/nonexistent",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 404


class TestUpdateChecklistItem:
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    @patch("app.main.update_checklist_item", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_complete_item(self, mock_get_res, mock_update, mock_audit):
        mock_get_res.return_value = {"id": "test-uuid", "request_id": "form-test123"}
        mock_update.return_value = {
            "item_key": "user_agreement",
            "status": "completed",
            "completed_at": "2026-04-10T10:00:00+00:00",
        }

        response = client.post(
            "/api/v1/checklist/form-test123/user_agreement",
            headers=AUTH_HEADERS,
            json={"status": "completed", "notes": "Received via email Feb 20"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        mock_audit.assert_called_once()

    @patch("app.main.update_checklist_item", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_update_item_not_found(self, mock_get_res, mock_update):
        mock_get_res.return_value = {"id": "test-uuid", "request_id": "form-test123"}
        mock_update.return_value = None

        response = client.post(
            "/api/v1/checklist/form-test123/nonexistent_item",
            headers=AUTH_HEADERS,
            json={"status": "completed"},
        )

        assert response.status_code == 404

    def test_invalid_status(self):
        response = client.post(
            "/api/v1/checklist/form-test123/user_agreement",
            headers=AUTH_HEADERS,
            json={"status": "invalid_status"},
        )
        assert response.status_code == 422


class TestBulkUpdateChecklist:
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    @patch("app.main.bulk_update_checklist_items", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_bulk_update(self, mock_get_res, mock_bulk, mock_audit):
        mock_get_res.return_value = {"id": "test-uuid", "request_id": "form-test123"}
        mock_bulk.return_value = 2

        response = client.post(
            "/api/v1/checklist/form-test123/bulk-update",
            headers=AUTH_HEADERS,
            json={
                "items": [
                    {"item_key": "furniture_layout", "status": "completed"},
                    {"item_key": "catering_plan", "status": "in_review"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 2

    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_bulk_update_not_found(self, mock_get_res):
        mock_get_res.return_value = None
        response = client.post(
            "/api/v1/checklist/nonexistent/bulk-update",
            headers=AUTH_HEADERS,
            json={"items": [{"item_key": "user_agreement", "status": "completed"}]},
        )
        assert response.status_code == 404


class TestComplianceReport:
    @patch("app.main.get_compliance_report", new_callable=AsyncMock)
    def test_compliance_report(self, mock_report):
        mock_report.return_value = {
            "period": "quarter",
            "start": "2026-01-01",
            "end": "2026-04-01",
            "total_items": 50,
            "completed_items": 40,
            "on_time_rate": 85.0,
            "events_all_complete": 6,
            "most_overdue_items": [
                {
                    "item_key": "catering_plan",
                    "item_label": "Catering Plan Submitted",
                    "overdue_count": 3,
                    "avg_days_overdue": 5.2,
                },
            ],
        }

        response = client.get(
            "/api/v1/reports/compliance?period=quarter&start=2026-01-01",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["on_time_rate"] == 85.0
        assert data["events_all_complete"] == 6
        assert len(data["most_overdue_items"]) == 1


# ============================================================
# Approve endpoint generates checklist
# ============================================================

class TestApproveGeneratesChecklist:
    @patch("app.main.insert_checklist_items", new_callable=AsyncMock)
    @patch("app.main.build_checklist_for_event")
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    @patch("app.main.approve_reservation", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_approve_creates_checklist(self, mock_get, mock_approve, mock_audit, mock_build, mock_insert):
        mock_get.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "pending_review",
        }
        mock_approve.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "approved",
            "ai_draft_response": "Approved",
            "requester_email": "jane@txgov.gov",
            "requester_name": "Jane Doe",
            "event_name": "S-EVENT-Meeting",
        }
        mock_build.return_value = [
            {"item_key": "user_agreement", "item_label": "User Agreement Signed", "required": True, "deadline_date": date(2026, 4, 15)},
            {"item_key": "catering_plan", "item_label": "Catering Plan Submitted", "required": True, "deadline_date": date(2026, 3, 10)},
        ]
        mock_insert.return_value = 2

        response = client.post(
            "/api/v1/approve/form-test123",
            headers=AUTH_HEADERS,
            json={"action": "approve"},
        )

        assert response.status_code == 200
        mock_build.assert_called_once()
        mock_insert.assert_called_once()
        # Audit should be called twice: once for approval, once for checklist generation
        assert mock_audit.call_count == 2

    @patch("app.main.insert_checklist_items", new_callable=AsyncMock)
    @patch("app.main.build_checklist_for_event")
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    @patch("app.main.approve_reservation", new_callable=AsyncMock)
    @patch("app.main.get_reservation", new_callable=AsyncMock)
    def test_checklist_failure_does_not_block_approval(self, mock_get, mock_approve, mock_audit, mock_build, mock_insert):
        mock_get.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "pending_review",
        }
        mock_approve.return_value = {
            "id": "test-uuid",
            "request_id": "form-test123",
            "status": "approved",
            "ai_draft_response": "Approved",
            "requester_email": "jane@txgov.gov",
            "requester_name": "Jane Doe",
            "event_name": "S-EVENT-Meeting",
        }
        mock_build.side_effect = RuntimeError("Checklist generation exploded")

        response = client.post(
            "/api/v1/approve/form-test123",
            headers=AUTH_HEADERS,
            json={"action": "approve"},
        )

        # Approval still succeeds despite checklist failure
        assert response.status_code == 200
        assert response.json()["status"] == "approved"


# ============================================================
# Daily digest integration
# ============================================================

class TestDailyDigestChecklist:
    def test_digest_includes_checklist_section(self):
        state = {
            "task_type": "daily_digest",
            "request_id": "digest-test",
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [
                {
                    "event_name": "A-EVENT-Gala",
                    "item_label": "Catering Plan Submitted",
                    "deadline_date": "2026-03-10",
                    "days_until_due": 3,
                },
            ],
            "errors": [],
        }

        result = build_daily_digest(state)
        body = result["draft_response"]
        assert "CHECKLIST ITEMS DUE THIS WEEK" in body
        assert "A-EVENT-Gala" in body
        assert "Catering Plan Submitted" in body

    def test_digest_empty_checklist(self):
        state = {
            "task_type": "daily_digest",
            "request_id": "digest-test",
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "errors": [],
        }

        result = build_daily_digest(state)
        body = result["draft_response"]
        assert "No checklist items due this week." in body
