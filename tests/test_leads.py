"""Unit tests for event lead and reminder nodes."""

from app.cgcs_constants import REMINDER_INTERVALS, STAFF_ROSTER
from app.graph.nodes.event_lead import (
    assign_event_lead,
    schedule_reminders,
)
from app.graph.nodes.reminders import find_due_reminders, send_reminders

# Use a real staff member from the roster for tests
_TEST_STAFF = STAFF_ROSTER[0]
_TEST_STAFF_NAME = _TEST_STAFF["name"]
_TEST_STAFF_EMAIL = _TEST_STAFF["email"]


class TestAssignEventLead:
    def test_valid_assignment(self):
        state = {
            "lead_staff_name": _TEST_STAFF_NAME,
            "lead_staff_email": _TEST_STAFF_EMAIL,
            "lead_reservation_id": "form-test123",
            "errors": [],
        }
        result = assign_event_lead(state)
        assert result["decision"] == "approve"
        assert result["lead_staff_name"] == _TEST_STAFF_NAME

    def test_missing_staff_name(self):
        state = {
            "lead_staff_email": _TEST_STAFF_EMAIL,
            "lead_reservation_id": "form-test123",
            "errors": [],
        }
        result = assign_event_lead(state)
        assert any("lead_staff_name" in e for e in result.get("errors", []))

    def test_missing_all_fields(self):
        state = {"errors": []}
        result = assign_event_lead(state)
        assert len(result.get("errors", [])) >= 3

    def test_sanitizes_staff_name(self):
        state = {
            "lead_staff_name": _TEST_STAFF_NAME[:3] + "\x00" + _TEST_STAFF_NAME[3:],
            "lead_staff_email": _TEST_STAFF_EMAIL,
            "lead_reservation_id": "form-test123",
            "errors": [],
        }
        result = assign_event_lead(state)
        assert "\x00" not in result.get("lead_staff_name", "")
        assert result["decision"] == "approve"

    def test_rejects_non_roster_staff(self):
        state = {
            "lead_staff_name": "Unknown Person",
            "lead_staff_email": "nobody@example.com",
            "lead_reservation_id": "form-test123",
            "errors": [],
        }
        result = assign_event_lead(state)
        assert result["decision"] == "needs_review"
        assert any("not in the CGCS staff roster" in e for e in result.get("errors", []))

    def test_monthly_cap_enforcement(self):
        state = {
            "lead_staff_name": _TEST_STAFF_NAME,
            "lead_staff_email": _TEST_STAFF_EMAIL,
            "lead_reservation_id": "form-test123",
            "lead_current_month_count": 3,
            "errors": [],
        }
        result = assign_event_lead(state)
        assert result["decision"] == "needs_review"
        assert any("monthly lead cap" in e for e in result.get("errors", []))


class TestScheduleReminders:
    def test_schedules_reminders_for_future_event(self):
        state = {
            "lead_event_date": "2027-06-15",
            "lead_staff_email": _TEST_STAFF_EMAIL,
            "lead_reservation_id": "form-test123",
            "errors": [],
        }
        result = schedule_reminders(state)
        # Should schedule all 4 reminders for a far-future event
        assert len(result.get("reminders_due", [])) == 4

    def test_no_reminders_for_missing_date(self):
        state = {
            "lead_staff_email": _TEST_STAFF_EMAIL,
            "errors": [],
        }
        result = schedule_reminders(state)
        assert result.get("decision") == "needs_review"

    def test_invalid_date_format(self):
        state = {
            "lead_event_date": "not-a-date",
            "lead_staff_email": _TEST_STAFF_EMAIL,
            "errors": [],
        }
        result = schedule_reminders(state)
        assert result.get("decision") == "needs_review"

    def test_reminder_intervals_correct(self):
        assert len(REMINDER_INTERVALS) == 4
        labels = [i["label"] for i in REMINDER_INTERVALS]
        assert "30_day" in labels
        assert "14_day" in labels
        assert "7_day" in labels
        assert "48_hour" in labels


class TestFindDueReminders:
    def test_no_reminders_due(self):
        state = {"reminders_due": [], "errors": []}
        result = find_due_reminders(state)
        assert result["reminders_due"] == []
        assert result["decision"] == "approve"

    def test_filters_pending_reminders(self):
        state = {
            "reminders_due": [
                {"remind_date": "2020-01-01", "status": "pending"},
                {"remind_date": "2020-01-01", "status": "sent"},
                {"remind_date": "2099-01-01", "status": "pending"},
            ],
            "errors": [],
        }
        result = find_due_reminders(state)
        # Only the first one is due (past date + pending)
        assert len(result["reminders_due"]) == 1


class TestSendReminders:
    def test_no_reminders_to_send(self):
        state = {"reminders_due": [], "errors": []}
        result = send_reminders(state)
        assert result["reminders_sent"] == []

    def test_sends_due_reminders(self):
        state = {
            "reminders_due": [
                {
                    "reminder_type": "30_day",
                    "reservation_id": "form-test123",
                    "staff_email": _TEST_STAFF_EMAIL,
                    "status": "pending",
                }
            ],
            "errors": [],
        }
        result = send_reminders(state)
        assert len(result["reminders_sent"]) == 1
        assert result["reminders_sent"][0]["status"] == "sent"
