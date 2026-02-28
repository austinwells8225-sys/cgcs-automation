"""Unit tests for event lead and reminder nodes."""

from app.graph.nodes.event_lead import (
    REMINDER_INTERVALS,
    assign_event_lead,
    schedule_reminders,
)
from app.graph.nodes.reminders import find_due_reminders, send_reminders


class TestAssignEventLead:
    def test_valid_assignment(self):
        state = {
            "lead_staff_name": "John Smith",
            "lead_staff_email": "john@austincc.edu",
            "lead_reservation_id": "form-test123",
            "errors": [],
        }
        result = assign_event_lead(state)
        assert result["decision"] == "approve"
        assert result["lead_staff_name"] == "John Smith"

    def test_missing_staff_name(self):
        state = {
            "lead_staff_email": "john@austincc.edu",
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
            "lead_staff_name": "John\x00Smith",
            "lead_staff_email": "john@austincc.edu",
            "lead_reservation_id": "form-test123",
            "errors": [],
        }
        result = assign_event_lead(state)
        assert result["lead_staff_name"] == "JohnSmith"


class TestScheduleReminders:
    def test_schedules_reminders_for_future_event(self):
        state = {
            "lead_event_date": "2027-06-15",
            "lead_staff_email": "john@austincc.edu",
            "lead_reservation_id": "form-test123",
            "errors": [],
        }
        result = schedule_reminders(state)
        # Should schedule all 4 reminders for a far-future event
        assert len(result.get("reminders_due", [])) == 4

    def test_no_reminders_for_missing_date(self):
        state = {
            "lead_staff_email": "john@austincc.edu",
            "errors": [],
        }
        result = schedule_reminders(state)
        assert result.get("decision") == "needs_review"

    def test_invalid_date_format(self):
        state = {
            "lead_event_date": "not-a-date",
            "lead_staff_email": "john@austincc.edu",
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
                    "staff_email": "john@austincc.edu",
                    "status": "pending",
                }
            ],
            "errors": [],
        }
        result = send_reminders(state)
        assert len(result["reminders_sent"]) == 1
        assert result["reminders_sent"][0]["status"] == "sent"
