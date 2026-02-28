"""Unit tests for calendar and calendar hold nodes."""

from app.graph.nodes.calendar import check_calendar_availability
from app.graph.nodes.calendar_hold import create_calendar_hold, validate_hold_request


class TestCalendarAvailability:
    def test_missing_fields_returns_error(self):
        state = {"errors": []}
        result = check_calendar_availability(state)
        assert result["decision"] == "needs_review"
        assert any("Missing calendar query fields" in e for e in result.get("errors", []))

    def test_partial_fields_returns_error(self):
        state = {
            "calendar_query_date": "2026-04-15",
            "errors": [],
        }
        result = check_calendar_availability(state)
        assert result["decision"] == "needs_review"


class TestValidateHoldRequest:
    def test_valid_hold_request(self):
        state = {
            "hold_org_name": "Test Org",
            "hold_date": "2026-04-15",
            "hold_start_time": "09:00",
            "hold_end_time": "12:00",
            "errors": [],
        }
        result = validate_hold_request(state)
        assert result["errors"] == []

    def test_missing_org_name(self):
        state = {
            "hold_date": "2026-04-15",
            "hold_start_time": "09:00",
            "hold_end_time": "12:00",
            "errors": [],
        }
        result = validate_hold_request(state)
        assert any("hold_org_name" in e for e in result["errors"])

    def test_missing_all_fields(self):
        state = {"errors": []}
        result = validate_hold_request(state)
        assert len(result["errors"]) >= 4

    def test_invalid_date_format(self):
        state = {
            "hold_org_name": "Test",
            "hold_date": "bad-date",
            "hold_start_time": "09:00",
            "hold_end_time": "12:00",
            "errors": [],
        }
        result = validate_hold_request(state)
        assert any("date format" in e.lower() for e in result["errors"])

    def test_invalid_time_format(self):
        state = {
            "hold_org_name": "Test",
            "hold_date": "2026-04-15",
            "hold_start_time": "9am",
            "hold_end_time": "12:00",
            "errors": [],
        }
        result = validate_hold_request(state)
        assert any("time format" in e.lower() for e in result["errors"])

    def test_start_after_end(self):
        state = {
            "hold_org_name": "Test",
            "hold_date": "2026-04-15",
            "hold_start_time": "14:00",
            "hold_end_time": "10:00",
            "errors": [],
        }
        result = validate_hold_request(state)
        assert any("start time" in e.lower() for e in result["errors"])

    def test_sanitizes_org_name(self):
        state = {
            "hold_org_name": "Test\x00Org\x07",
            "hold_date": "2026-04-15",
            "hold_start_time": "09:00",
            "hold_end_time": "12:00",
            "errors": [],
        }
        result = validate_hold_request(state)
        assert result["hold_org_name"] == "TestOrg"


class TestCreateCalendarHold:
    def test_skips_if_errors(self):
        state = {"errors": ["validation error"]}
        result = create_calendar_hold(state)
        assert result["decision"] == "needs_review"
