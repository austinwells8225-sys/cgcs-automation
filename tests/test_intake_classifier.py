"""Tests for intake classification, response drafting, furniture and police emails."""

from datetime import date

from app.services.intake_classifier import (
    classify_request,
    draft_furniture_email,
    draft_intake_response,
    draft_police_email,
    _parse_attendance_max,
)
from app.cgcs_constants import MOVING_TEAM, MOVING_TEAM_CC, POLICE_CONTACT, CGCS_SYSTEM_EMAIL
from app.graph.nodes.smartsheet_intake import classify_intake_request, draft_intake_emails


# ============================================================
# Shared fixtures
# ============================================================

def _easy_internal():
    """Simple internal ACC request — weekday, no AV, no furniture."""
    return {
        "requestor_name": "Regina Schneider",
        "requestor_email": "rschneid@austincc.edu",
        "requestor_phone": "+1 (512) 223-7004",
        "request_type": "Internal Request",
        "requestor_type": "An Employee of ACC",
        "event_code": "1335",
        "event_name": "Braver Angels Workshop",
        "event_type": "Other",
        "event_start_date": date(2026, 6, 25),  # Thursday
        "event_end_date": date(2026, 6, 25),
        "event_num_days": 1,
        "event_room": "RGC3.3340",
        "event_location": "(RGC) CGCS (RGC3.3340)",
        "start_time": "5:00 PM",
        "end_time": "9:00 PM",
        "setup_time": "1 Hour",
        "breakdown_time": "1 Hour",
        "expected_attendance": "90",
        "walkthrough_requested": False,
        "alcohol_requested": False,
        "av_requested": False,
        "av_details": [],
        "furniture_requested": False,
        "furniture_items": [],
        "linens_requested": [],
        "catering_requested": False,
        "is_external": False,
        "is_multi_day": False,
    }


def _mid_external_with_av():
    """External request with AV — mid difficulty."""
    base = _easy_internal()
    base.update({
        "request_type": "External Request",
        "requestor_type": "A Member of the Community",
        "requestor_name": "Courtney Kendler",
        "requestor_email": "courtney@ibh.com",
        "is_external": True,
        "av_requested": True,
        "av_details": ["Projection", "Audio"],
        "end_time": "4:00 PM",  # weekday afternoon — keeps this mid, not hard
    })
    return base


def _mid_furniture():
    """Internal request with furniture — mid difficulty."""
    base = _easy_internal()
    base.update({
        "furniture_requested": True,
        "furniture_items": [
            {"qty": 18, "item": "Round Tables"},
            {"qty": 150, "item": "Chairs"},
        ],
        "furniture_setup_by": "7:30 AM",
        "linens_requested": [
            {"qty": 54, "item": "Black - Round Table Linens"},
        ],
    })
    return base


def _mid_multi_day():
    """Multi-day event — mid difficulty."""
    base = _easy_internal()
    base.update({
        "event_end_date": date(2026, 6, 27),
        "event_num_days": 3,
        "is_multi_day": True,
    })
    return base


def _hard_alcohol():
    """Event with alcohol — hard."""
    base = _easy_internal()
    base["alcohol_requested"] = True
    return base


def _hard_weekend():
    """Saturday event — hard (police needed)."""
    base = _easy_internal()
    base.update({
        "event_start_date": date(2026, 6, 27),  # Saturday
        "end_time": "3:00 PM",
    })
    return base


def _hard_evening():
    """Weekday evening event ending after 5 PM — hard (police)."""
    base = _easy_internal()
    # end_time "9:00 PM" is already > 5 PM, but let's use the base as-is
    # Actually the base end_time is "9:00 PM" on a Thursday — that IS evening
    # Let me use a time that's clearly evening on a weekday
    base.update({
        "event_start_date": date(2026, 6, 24),  # Wednesday
        "end_time": "9:00 PM",
    })
    return base


def _hard_large():
    """Large event with 250 attendees — hard."""
    base = _easy_internal()
    base["expected_attendance"] = "250"
    return base


def _hard_catering():
    """Event with ACC catering — hard."""
    base = _easy_internal()
    base["catering_requested"] = True
    return base


# ============================================================
# Classification
# ============================================================

class TestClassifyRequest:
    def test_easy_internal(self):
        # Internal, weekday, 5PM end is technically evening but
        # the fixture uses Thu with 9PM end — that's evening → hard.
        # Use a clean weekday-afternoon fixture:
        parsed = _easy_internal()
        parsed["end_time"] = "4:00 PM"  # before 5 PM
        result = classify_request(parsed)
        assert result["difficulty"] == "easy"
        assert result["auto_send"] is True
        assert result["confidence"] >= 0.7
        assert result["requires_police"] is False
        assert result["requires_furniture_email"] is False
        assert result["flags"] == []

    def test_mid_external(self):
        result = classify_request(_mid_external_with_av())
        assert result["difficulty"] == "mid"
        assert result["auto_send"] is False
        assert "external" in result["reasoning"].lower()

    def test_mid_furniture(self):
        parsed = _mid_furniture()
        parsed["end_time"] = "4:00 PM"
        result = classify_request(parsed)
        assert result["difficulty"] == "mid"
        assert result["requires_furniture_email"] is True
        assert any("furniture" in f.lower() for f in result["flags"])

    def test_mid_av(self):
        parsed = _easy_internal()
        parsed["end_time"] = "4:00 PM"
        parsed["av_requested"] = True
        result = classify_request(parsed)
        assert result["difficulty"] == "mid"
        assert any("av" in f.lower() for f in result["flags"])

    def test_mid_multi_day(self):
        parsed = _mid_multi_day()
        parsed["end_time"] = "4:00 PM"
        result = classify_request(parsed)
        assert result["difficulty"] == "mid"
        assert any("multi-day" in f.lower() for f in result["flags"])

    def test_hard_alcohol(self):
        parsed = _hard_alcohol()
        parsed["end_time"] = "4:00 PM"
        result = classify_request(parsed)
        assert result["difficulty"] == "hard"
        assert any("alcohol" in f.lower() for f in result["flags"])

    def test_hard_weekend(self):
        result = classify_request(_hard_weekend())
        assert result["difficulty"] == "hard"
        assert result["requires_police"] is True
        assert any("police" in f.lower() for f in result["flags"])

    def test_hard_evening(self):
        result = classify_request(_hard_evening())
        assert result["difficulty"] == "hard"
        assert result["requires_police"] is True

    def test_hard_large_attendance(self):
        parsed = _hard_large()
        parsed["end_time"] = "4:00 PM"
        result = classify_request(parsed)
        assert result["difficulty"] == "hard"
        assert any("250" in f for f in result["flags"])

    def test_hard_catering(self):
        parsed = _hard_catering()
        parsed["end_time"] = "4:00 PM"
        result = classify_request(parsed)
        assert result["difficulty"] == "hard"
        assert any("catering" in f.lower() for f in result["flags"])

    def test_hard_overrides_mid(self):
        """External + alcohol should be hard, not mid."""
        parsed = _mid_external_with_av()
        parsed["alcohol_requested"] = True
        parsed["end_time"] = "4:00 PM"
        result = classify_request(parsed)
        assert result["difficulty"] == "hard"

    def test_multiple_hard_flags(self):
        """Weekend + alcohol + catering = hard with multiple flags."""
        parsed = _hard_weekend()
        parsed["alcohol_requested"] = True
        parsed["catering_requested"] = True
        result = classify_request(parsed)
        assert result["difficulty"] == "hard"
        assert len(result["flags"]) >= 3

    def test_empty_parsed(self):
        result = classify_request({})
        assert result["difficulty"] == "easy"
        assert result["auto_send"] is True

    def test_confidence_always_valid(self):
        for fixture in [_easy_internal, _mid_external_with_av, _hard_alcohol, _hard_weekend]:
            parsed = fixture()
            if parsed.get("end_time") == "9:00 PM":
                pass  # evening → hard
            result = classify_request(parsed)
            assert 0.0 <= result["confidence"] <= 1.0


class TestParseAttendanceMax:
    def test_single_number(self):
        assert _parse_attendance_max("90") == 90

    def test_range(self):
        assert _parse_attendance_max("150-200") == 200

    def test_empty(self):
        assert _parse_attendance_max("") == 0

    def test_none(self):
        assert _parse_attendance_max(None) == 0

    def test_text(self):
        assert _parse_attendance_max("about 50") == 50


# ============================================================
# Response Drafting
# ============================================================

class TestDraftIntakeResponse:
    def test_easy_auto_send(self):
        parsed = _easy_internal()
        parsed["end_time"] = "4:00 PM"
        classification = classify_request(parsed)
        result = draft_intake_response(parsed, classification)
        assert result["auto_send"] is True
        assert result["to"] == "rschneid@austincc.edu"
        assert "Braver Angels" in result["subject"]

    def test_easy_body_has_deadlines(self):
        parsed = _easy_internal()
        parsed["end_time"] = "4:00 PM"
        classification = classify_request(parsed)
        result = draft_intake_response(parsed, classification)
        body = result["body"]
        assert "Hi Regina," in body
        assert "available" in body.lower()
        assert "hold" in body.lower()
        assert "Catering plan" in body or "catering" in body.lower()
        assert "Walkthrough" in body or "walkthrough" in body.lower()
        assert "User Agreement" in body
        assert "CGCS Team" in body

    def test_easy_body_has_parking(self):
        parsed = _easy_internal()
        parsed["end_time"] = "4:00 PM"
        classification = classify_request(parsed)
        result = draft_intake_response(parsed, classification)
        assert "parking" in result["body"].lower()

    def test_mid_not_auto_send(self):
        parsed = _mid_external_with_av()
        classification = classify_request(parsed)
        result = draft_intake_response(parsed, classification)
        assert result["auto_send"] is False

    def test_mid_body_is_review_draft(self):
        parsed = _mid_external_with_av()
        classification = classify_request(parsed)
        result = draft_intake_response(parsed, classification)
        body = result["body"]
        assert "Hi Courtney," in body
        assert "reviewing" in body.lower() or "review" in body.lower()
        assert "2\u20134 business days" in body
        assert "CGCS Team" in body

    def test_hard_not_auto_send(self):
        parsed = _hard_alcohol()
        parsed["end_time"] = "4:00 PM"
        classification = classify_request(parsed)
        result = draft_intake_response(parsed, classification)
        assert result["auto_send"] is False

    def test_empty_name_fallback(self):
        parsed = _easy_internal()
        parsed["end_time"] = "4:00 PM"
        parsed["requestor_name"] = ""
        classification = classify_request(parsed)
        result = draft_intake_response(parsed, classification)
        assert "Hi there," in result["body"]


# ============================================================
# Furniture Email
# ============================================================

class TestDraftFurnitureEmail:
    def test_returns_none_when_no_furniture(self):
        assert draft_furniture_email(_easy_internal()) is None

    def test_drafts_email_with_furniture(self):
        result = draft_furniture_email(_mid_furniture())
        assert result is not None
        assert MOVING_TEAM[0] in result["to"]
        assert MOVING_TEAM[1] in result["to"]
        assert result["cc"] == MOVING_TEAM_CC

    def test_subject_has_event_name(self):
        result = draft_furniture_email(_mid_furniture())
        assert "Braver Angels" in result["subject"]
        assert "Furniture Request" in result["subject"]

    def test_body_has_furniture_items(self):
        result = draft_furniture_email(_mid_furniture())
        body = result["body"]
        assert "18 Round Tables" in body
        assert "150 Chairs" in body

    def test_body_has_linens(self):
        result = draft_furniture_email(_mid_furniture())
        body = result["body"]
        assert "54 Black - Round Table Linens" in body

    def test_body_has_event_details(self):
        result = draft_furniture_email(_mid_furniture())
        body = result["body"]
        assert "Hi Tyler and Scott," in body
        assert "5:00 PM - 9:00 PM" in body
        assert "Setup by:" in body
        assert "CGCS Team" in body

    def test_body_has_attendance(self):
        result = draft_furniture_email(_mid_furniture())
        assert "90" in result["body"]


# ============================================================
# Police Email
# ============================================================

class TestDraftPoliceEmail:
    def test_returns_none_for_weekday_afternoon(self):
        parsed = _easy_internal()
        parsed["end_time"] = "4:00 PM"
        assert draft_police_email(parsed) is None

    def test_drafts_for_weekend(self):
        result = draft_police_email(_hard_weekend())
        assert result is not None
        assert result["to"] == POLICE_CONTACT
        assert result["cc"] == CGCS_SYSTEM_EMAIL

    def test_drafts_for_evening(self):
        result = draft_police_email(_hard_evening())
        assert result is not None
        assert result["to"] == POLICE_CONTACT

    def test_subject_has_event_name(self):
        result = draft_police_email(_hard_weekend())
        assert "Braver Angels" in result["subject"]
        assert "Police Coverage" in result["subject"]

    def test_body_has_event_details(self):
        result = draft_police_email(_hard_weekend())
        body = result["body"]
        assert "Hi Officer Ortiz," in body
        assert "police coverage" in body.lower()
        assert "CGCS Team" in body

    def test_weekend_label(self):
        result = draft_police_email(_hard_weekend())
        assert "weekend" in result["body"].lower()

    def test_evening_label(self):
        result = draft_police_email(_hard_evening())
        assert "evening" in result["body"].lower()

    def test_returns_none_without_date(self):
        parsed = _easy_internal()
        parsed["event_start_date"] = None
        assert draft_police_email(parsed) is None

    def test_body_has_attendance(self):
        result = draft_police_email(_hard_weekend())
        assert "90" in result["body"]

    def test_body_has_event_type(self):
        result = draft_police_email(_hard_weekend())
        assert "Other" in result["body"]


# ============================================================
# Graph Nodes
# ============================================================

class TestClassifyIntakeRequestNode:
    def test_classifies_from_state(self):
        parsed = _easy_internal()
        parsed["end_time"] = "4:00 PM"
        state = {"smartsheet_parsed": parsed, "errors": []}
        result = classify_intake_request(state)
        assert result["intake_difficulty"] == "easy"
        assert result["intake_classification"]["auto_send"] is True

    def test_missing_parsed_returns_error(self):
        state = {"errors": []}
        result = classify_intake_request(state)
        assert result["decision"] == "needs_review"
        assert any("No parsed" in e for e in result["errors"])


class TestDraftIntakeEmailsNode:
    def test_easy_produces_auto_send(self):
        parsed = _easy_internal()
        parsed["end_time"] = "4:00 PM"
        classification = classify_request(parsed)
        state = {
            "smartsheet_parsed": parsed,
            "intake_classification": classification,
            "errors": [],
        }
        result = draft_intake_emails(state)
        assert result["decision"] == "approve"
        assert result["email_auto_send"] is True
        assert len(result["intake_draft_emails"]) == 1

    def test_hard_with_furniture_and_police(self):
        parsed = _hard_weekend()
        parsed["furniture_requested"] = True
        parsed["furniture_items"] = [{"qty": 10, "item": "Chairs"}]
        classification = classify_request(parsed)
        state = {
            "smartsheet_parsed": parsed,
            "intake_classification": classification,
            "errors": [],
        }
        result = draft_intake_emails(state)
        assert result["decision"] == "needs_review"
        assert result["email_auto_send"] is False
        # main response + furniture + police = 3
        assert len(result["intake_draft_emails"]) == 3

    def test_mid_with_furniture_only(self):
        parsed = _mid_furniture()
        parsed["end_time"] = "4:00 PM"
        classification = classify_request(parsed)
        state = {
            "smartsheet_parsed": parsed,
            "intake_classification": classification,
            "errors": [],
        }
        result = draft_intake_emails(state)
        assert result["decision"] == "needs_review"
        # main response + furniture = 2
        assert len(result["intake_draft_emails"]) == 2

    def test_missing_parsed_returns_error(self):
        state = {"intake_classification": {}, "errors": []}
        result = draft_intake_emails(state)
        assert result["decision"] == "needs_review"
