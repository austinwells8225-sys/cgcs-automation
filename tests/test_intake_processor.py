"""Tests for intake processor: acknowledgment emails, P.E.T. row building,
and calendar HOLD creation from parsed Smartsheet data."""

from datetime import date

from app.cgcs_constants import (
    COST_CENTER,
    PET_COLUMNS,
    build_intake_acknowledgment_email,
)
from app.services.intake_processor import (
    build_calendar_hold,
    build_pet_row,
    classify_event_type,
    _additional_needs_summary,
    _format_event_date,
    _format_room_display,
    _furniture_summary,
    _has_stage,
    _parse_duration_to_hours,
    _adjust_time,
)


# ============================================================
# Shared test fixtures
# ============================================================

INTERNAL_PARSED = {
    "requestor_name": "Regina Schneider",
    "department": "Service-Learning Program, Center for Government and Civic Service",
    "organization": None,
    "request_type": "Internal Request",
    "requestor_type": "An Employee of ACC",
    "requestor_email": "rschneid@austincc.edu",
    "requestor_phone": "+1 (512) 223-7004",
    "event_code": "1335",
    "event_status": "Pending",
    "event_name": "Braver Angels Summer Workshop: Depolarizing from Within",
    "event_type": "Other",
    "event_start_date": date(2026, 6, 25),
    "event_end_date": date(2026, 6, 25),
    "event_num_days": 1,
    "event_campus": "Rio Grande Campus",
    "event_location": "(RGC) Center for Government and Civic Service (CGCS) (RGC3.3340) - Capacity 350",
    "event_room": "RGC3.3340",
    "setup_time": "1 Hour",
    "start_time": "5:00 PM",
    "end_time": "9:00 PM",
    "breakdown_time": "1 Hour",
    "expected_attendance": "90",
    "walkthrough_requested": False,
    "alcohol_requested": False,
    "av_requested": False,
    "av_details": [],
    "furniture_requested": False,
    "furniture_items": [],
    "linens_requested": [],
    "catering_requested": None,
    "is_external": False,
    "is_multi_day": False,
}

EXTERNAL_PARSED = {
    "requestor_name": "Courtney Kendler-Gelety",
    "department": None,
    "organization": "Institute for Better Health",
    "request_type": "External Request",
    "requestor_type": "A Member of the Community, a Vendor, or an Event Coordinator for another organization.",
    "requestor_email": "courtney@ibh.com",
    "requestor_phone": "+1 (248) 978-7787",
    "event_code": "1238",
    "event_status": "Pending",
    "event_name": "ACT BootCamp for Trauma",
    "event_type": "General Meeting Lecture",
    "event_start_date": date(2026, 9, 11),
    "event_end_date": date(2026, 9, 13),
    "event_num_days": 3,
    "event_campus": "Rio Grande Campus",
    "event_location": "(RGC) Center for Government and Civic Service (CGCS) (RGC3.3340) - Capacity 350",
    "event_room": "RGC3.3340",
    "setup_time": "1 Hour",
    "start_time": "8:30 AM",
    "end_time": "5:30 PM",
    "breakdown_time": "30 Minutes",
    "expected_attendance": "150-200",
    "walkthrough_requested": False,
    "alcohol_requested": False,
    "av_requested": True,
    "av_setup_by": "7:30 AM",
    "av_details": ["AV Check Needed", "Audio Support", "Projection of Digital Assets"],
    "furniture_requested": True,
    "furniture_items": [
        {"qty": 1, "item": "Stage"},
        {"qty": 18, "item": "Round Tables"},
        {"qty": 1, "item": "Podiums"},
        {"qty": 150, "item": "Chairs"},
    ],
    "linens_requested": [
        {"qty": 1, "item": "Stage Linen"},
        {"qty": 54, "item": "Black - Round Table Linens"},
    ],
    "catering_requested": False,
    "is_external": True,
    "is_multi_day": True,
}


# ============================================================
# A. Acknowledgment Email
# ============================================================

class TestIntakeAcknowledgmentEmail:
    def test_basic_email(self):
        result = build_intake_acknowledgment_email(
            "Regina Schneider",
            "Braver Angels Workshop",
            "June 25, 2026",
        )
        assert "CGCS Event Request Received" in result["subject"]
        assert "Braver Angels Workshop" in result["subject"]
        assert "Hi Regina," in result["body"]
        assert "Braver Angels Workshop" in result["body"]
        assert "June 25, 2026" in result["body"]

    def test_body_contains_key_info(self):
        result = build_intake_acknowledgment_email(
            "Courtney Kendler-Gelety",
            "ACT BootCamp",
            "September 11, 2026",
        )
        assert "2\u20134 business days" in result["body"]
        assert "14 business days" in result["body"]
        assert "cgcs-acc.org" in result["body"]
        assert "email thread" in result["body"]

    def test_signoff(self):
        result = build_intake_acknowledgment_email("Test Person", "Test Event", "Jan 1")
        assert "Warm regards," in result["body"]
        assert "CGCS Team" in result["body"]
        assert "Center for Government & Civic Service" in result["body"]
        assert "Rio Grande Campus" in result["body"]

    def test_empty_name_fallback(self):
        result = build_intake_acknowledgment_email("", "Some Event", "Jan 1")
        assert "Hi there," in result["body"]

    def test_empty_event_name_fallback(self):
        result = build_intake_acknowledgment_email("Jane", "", "Jan 1")
        assert "your event" in result["subject"]
        assert "your event" in result["body"]

    def test_empty_date_fallback(self):
        result = build_intake_acknowledgment_email("Jane", "Test", "")
        assert "the requested date" in result["body"]

    def test_multipart_name_uses_first(self):
        result = build_intake_acknowledgment_email(
            "Maria Elena Garcia", "Test", "Jan 1"
        )
        assert "Hi Maria," in result["body"]

    def test_subject_format(self):
        result = build_intake_acknowledgment_email("Jane", "Big Event", "Jan 1")
        assert result["subject"] == "CGCS Event Request Received \u2014 Big Event"


# ============================================================
# B. P.E.T. Row Builder
# ============================================================

class TestClassifyEventType:
    def test_internal_is_cgcs(self):
        assert classify_event_type({"request_type": "Internal Request"}) == "CGCS"

    def test_external_community_is_ami(self):
        assert classify_event_type({
            "request_type": "External Request",
            "requestor_type": "A Member of the Community",
        }) == "AMI"

    def test_external_vendor_is_ami(self):
        assert classify_event_type({
            "request_type": "External Request",
            "requestor_type": "a Vendor or Event Coordinator",
        }) == "AMI"

    def test_external_other_is_cgcs(self):
        assert classify_event_type({
            "request_type": "External Request",
            "requestor_type": "A Government Official",
        }) == "CGCS"

    def test_missing_fields_is_cgcs(self):
        assert classify_event_type({}) == "CGCS"


class TestHelpers:
    def test_furniture_summary(self):
        result = _furniture_summary(EXTERNAL_PARSED)
        assert "18 Round Tables" in result
        assert "150 Chairs" in result
        assert "1 Stage" in result

    def test_furniture_summary_empty(self):
        assert _furniture_summary(INTERNAL_PARSED) == ""

    def test_has_stage_yes(self):
        assert _has_stage(EXTERNAL_PARSED) == "Yes"

    def test_has_stage_no(self):
        assert _has_stage(INTERNAL_PARSED) == "No"

    def test_additional_needs_with_av_and_linens(self):
        result = _additional_needs_summary(EXTERNAL_PARSED)
        assert "AV:" in result
        assert "Linens:" in result

    def test_additional_needs_empty(self):
        assert _additional_needs_summary(INTERNAL_PARSED) == ""

    def test_format_event_date(self):
        assert _format_event_date(date(2026, 6, 25)) == "June 25"
        assert _format_event_date(date(2026, 9, 11)) == "September 11"

    def test_format_event_date_none(self):
        assert _format_event_date(None) == ""

    def test_format_room_display_3340(self):
        assert _format_room_display("RGC3.3340") == "3340 (Big Room)"

    def test_format_room_display_other(self):
        assert _format_room_display("RGC3.2100") == "2100"

    def test_format_room_display_none(self):
        assert _format_room_display(None) == ""

    def test_parse_duration_1_hour(self):
        assert _parse_duration_to_hours("1 Hour") == 1.0

    def test_parse_duration_30_minutes(self):
        assert _parse_duration_to_hours("30 Minutes") == 0.5

    def test_parse_duration_2_hours(self):
        assert _parse_duration_to_hours("2 Hours") == 2.0

    def test_parse_duration_none(self):
        assert _parse_duration_to_hours(None) == 0.0

    def test_parse_duration_empty(self):
        assert _parse_duration_to_hours("") == 0.0

    def test_adjust_time_subtract(self):
        assert _adjust_time("5:00 PM", 1.0, "subtract") == "16:00"

    def test_adjust_time_add(self):
        assert _adjust_time("9:00 PM", 0.5, "add") == "21:30"

    def test_adjust_time_24h(self):
        assert _adjust_time("17:00", 1.0, "subtract") == "16:00"

    def test_adjust_time_no_offset(self):
        assert _adjust_time("09:00", 0.0, "subtract") == "09:00"


class TestBuildPetRow:
    def test_internal_row_length(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert len(row) == len(PET_COLUMNS)
        assert len(row) == 20

    def test_internal_event_name(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[0] == "Braver Angels Summer Workshop: Depolarizing from Within"

    def test_status_always_pending(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[1] == "Pending"

    def test_entered_into_calendar(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[2] == "Yes"

    def test_internal_classification(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[3] == "CGCS"

    def test_external_classification(self):
        row = build_pet_row(EXTERNAL_PARSED)
        assert row[3] == "AMI"

    def test_date_formatted(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[4] == "June 25"

    def test_time_range(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[5] == "5:00 PM - 9:00 PM"

    def test_cgcs_lead_tbd(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[6] == "TBD"

    def test_contact_info(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert "Regina Schneider" in row[7]
        assert "rschneid@austincc.edu" in row[7]
        assert "+1 (512) 223-7004" in row[7]

    def test_attendance(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[8] == "90"

    def test_attendance_range(self):
        row = build_pet_row(EXTERNAL_PARSED)
        assert row[8] == "150-200"

    def test_money_expected_empty(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[9] == ""

    def test_adastra_pending(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[10] == "Pending"

    def test_tdx_empty_no_av(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[11] == ""

    def test_tdx_tbd_with_av(self):
        row = build_pet_row(EXTERNAL_PARSED)
        assert row[11] == "TBD"

    def test_floor_layout_empty(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[12] == ""

    def test_floor_layout_with_furniture(self):
        row = build_pet_row(EXTERNAL_PARSED)
        assert "18 Round Tables" in row[12]
        assert "150 Chairs" in row[12]

    def test_stage_no(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[13] == "No"

    def test_stage_yes(self):
        row = build_pet_row(EXTERNAL_PARSED)
        assert row[13] == "Yes"

    def test_breakdown_time(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[14] == "1 Hour"

    def test_additional_needs_empty(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[15] == ""

    def test_additional_needs_with_av(self):
        row = build_pet_row(EXTERNAL_PARSED)
        assert "AV:" in row[15]

    def test_walkthrough_date_empty(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[16] == ""

    def test_invoice_generated_no(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[17] == "No"

    def test_rooms(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[18] == "3340 (Big Room)"

    def test_cgcs_labor_empty(self):
        row = build_pet_row(INTERNAL_PARSED)
        assert row[19] == ""


class TestBuildPetRowMinimal:
    """Test with missing fields — should never crash."""

    def test_empty_parsed(self):
        row = build_pet_row({})
        assert len(row) == 20
        assert row[0] == ""
        assert row[1] == "Pending"
        assert row[3] == "CGCS"

    def test_partial_data(self):
        row = build_pet_row({
            "event_name": "Minimal",
            "event_start_date": date(2027, 1, 15),
        })
        assert len(row) == 20
        assert row[0] == "Minimal"
        assert row[4] == "January 15"


# ============================================================
# C. Calendar HOLD Builder
# ============================================================

class TestBuildCalendarHold:
    def test_internal_hold(self):
        hold = build_calendar_hold(INTERNAL_PARSED)
        assert hold["title"] == "HOLD - Braver Angels Summer Workshop: Depolarizing from Within"
        assert hold["start_date"] == "2026-06-25"
        assert hold["end_date"] == "2026-06-25"

    def test_start_time_adjusted_for_setup(self):
        hold = build_calendar_hold(INTERNAL_PARSED)
        # 5:00 PM (17:00) minus 1 hour setup = 16:00
        assert hold["start_time"] == "16:00"

    def test_end_time_adjusted_for_breakdown(self):
        hold = build_calendar_hold(INTERNAL_PARSED)
        # 9:00 PM (21:00) plus 1 hour breakdown = 22:00
        assert hold["end_time"] == "22:00"

    def test_external_hold_dates(self):
        hold = build_calendar_hold(EXTERNAL_PARSED)
        assert hold["start_date"] == "2026-09-11"
        assert hold["end_date"] == "2026-09-13"

    def test_external_setup_adjustment(self):
        hold = build_calendar_hold(EXTERNAL_PARSED)
        # 8:30 AM minus 1 hour = 7:30
        assert hold["start_time"] == "07:30"

    def test_external_breakdown_adjustment(self):
        hold = build_calendar_hold(EXTERNAL_PARSED)
        # 5:30 PM (17:30) plus 30 min = 18:00
        assert hold["end_time"] == "18:00"

    def test_location_set(self):
        hold = build_calendar_hold(INTERNAL_PARSED)
        assert "CGCS" in hold["location"]

    def test_description_has_all_fields(self):
        hold = build_calendar_hold(INTERNAL_PARSED)
        desc = hold["description"]
        assert "Event Name: Braver Angels" in desc
        assert "Status: Pending" in desc
        assert "CGCS Lead: TBD" in desc
        assert "Contact Name / Event Lead: Regina Schneider" in desc
        assert "Email: rschneid@austincc.edu" in desc
        assert "Phone: +1 (512) 223-7004" in desc
        assert "Attendance Estimate: 90" in desc
        assert "Restricted: Internal" in desc
        assert "Ad Astra #: Pending" in desc
        assert "TDX Request #: TBD" in desc
        assert "Room(s) Reserved: 3340 (Big Room)" in desc
        assert "Stage Needed: No" in desc
        assert "Breakdown Time Needed: 1 Hour" in desc
        assert "Walkthrough Date: TBD" in desc
        assert "Invoice Generated: No" in desc
        assert "Deposit Paid: No" in desc
        assert f"Cost Center: {COST_CENTER}" in desc
        assert "Spend Category: 5001" in desc
        assert "Tax Exempt: TBD" in desc
        assert "Auto-generated from Smartsheet intake 1335" in desc

    def test_internal_money_expected_na(self):
        hold = build_calendar_hold(INTERNAL_PARSED)
        assert "Money Expected: N/A" in hold["description"]

    def test_external_money_expected_tbd(self):
        hold = build_calendar_hold(EXTERNAL_PARSED)
        assert "Money Expected: TBD" in hold["description"]

    def test_external_description_fields(self):
        hold = build_calendar_hold(EXTERNAL_PARSED)
        desc = hold["description"]
        assert "Restricted: External" in desc
        assert "Organization / Department: Institute for Better Health" in desc
        assert "Courtney Kendler-Gelety" in desc
        assert "AV:" in desc or "Additional Needs:" in desc

    def test_external_furniture_in_description(self):
        hold = build_calendar_hold(EXTERNAL_PARSED)
        desc = hold["description"]
        assert "18 Round Tables" in desc
        assert "Stage Needed: Yes" in desc

    def test_minimal_hold(self):
        hold = build_calendar_hold({
            "event_name": "Minimal",
            "event_start_date": date(2027, 1, 15),
            "start_time": "9:00 AM",
            "end_time": "12:00 PM",
        })
        assert hold["title"] == "HOLD - Minimal"
        assert hold["start_date"] == "2027-01-15"
        assert hold["start_time"] == "09:00"  # no setup offset
        assert hold["end_time"] == "12:00"    # no breakdown offset

    def test_empty_parsed_doesnt_crash(self):
        hold = build_calendar_hold({})
        assert hold["title"] == "HOLD - Unnamed Event"
        assert isinstance(hold["description"], str)

    def test_description_dept_for_internal(self):
        hold = build_calendar_hold(INTERNAL_PARSED)
        assert "Service-Learning Program" in hold["description"]

    def test_description_org_for_external(self):
        hold = build_calendar_hold(EXTERNAL_PARSED)
        assert "Institute for Better Health" in hold["description"]
