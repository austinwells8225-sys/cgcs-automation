"""Tests for Smartsheet intake email parser."""

from datetime import date

from app.services.smartsheet_parser import is_smartsheet_intake, parse_smartsheet_intake


# ============================================================
# Real email fixtures
# ============================================================

INTERNAL_SUBJECT = (
    "Notice of Event Space Request - Center for Government and Civic Service - RGC"
    " | Braver Angels Summer Workshop: Depolarizing from Within"
    " | 06/25/26 | 5:00 PM-9:00 PM"
)

INTERNAL_BODY = (
    "Greetings Center for Government and Civic Service Team, "
    "An Event Request has included the Rio Grande space for Center for Government and Civic Service. "
    "These are the event details: "
    "REQUESTOR "
    "- Event Requestor Name - Regina Schneider "
    "- Department: - Service-Learning Program, Center for Government and Civic Service, "
    "classes from Psychology Department, Philosophy Department, Communications and Literary "
    "- Request Type - Internal Request "
    "- Event Requestor Type - An Employee of ACC "
    "- Event Requestor Email - rschneid@austincc.edu "
    "- Event Requestor Contact Number - +1 (512) 223-7004 "
    "EVENT "
    "- Event Code - 1335 "
    "- Event Status - Pending "
    "- Campus Manager "
    "- Event Name - Braver Angels Summer Workshop: Depolarizing from Within "
    "- Event Type - Other "
    "- Event Date: 06/25/26 (1 Day) "
    "- Event Campus - Rio Grande Campus "
    "- Event Location Space - (RGC) Center for Government and Civic Service (CGCS) (RGC3.3340) - Capacity 350 (3479 SF) "
    "- Event Setup Time - 1 Hour "
    "- Event Start Time - 5:00 PM "
    "- Event End Time - 9:00 PM "
    "- Event Breakdown Time - 1 Hour "
    "- Event Expected Attendance - 90 "
    "- Event Site Walk Through Requested - No "
    "- Parking Needs: No Parking Needs Reported "
    "- Alcohol Requested - No "
    "- Event Purpose - Professional Development "
    "**NO OCRM / MARKETING INFORMATION** "
    "#INVALID OPERATION "
    "CGCS Dashboard Link: https://app.smartsheet.com/b/publish?EQBCT=1ba152f673c4429db66c148ace2e6e92 "
    "Thank you, Events Team"
)

EXTERNAL_SUBJECT = (
    "Notice of Event Space Request - Center for Government and Civic Service - RGC"
    " | ACT BootCamp for Trauma"
    " | 09/11/26 | 8:30 AM-5:30 PM"
)

EXTERNAL_BODY = (
    "Greetings Center for Government and Civic Service Team, "
    "An Event Request has included the Rio Grande space for Center for Government and Civic Service. "
    "These are the event details: "
    "REQUESTOR "
    "- Event Requestor Name - Courtney Kendler-Gelety "
    "- Organization: - Institute for Better Health "
    "- Request Type - External Request "
    "- Event Requestor Type - A Member of the Community, a Vendor, or an Event Coordinator for another organization. "
    "- Event Requestor Email - courtney@ibh.com "
    "- Event Requestor Contact Number - +1 (248) 978-7787 "
    "EVENT "
    "- Event Code - 1238 "
    "- Event Status - Pending "
    "- Campus Manager "
    "- Event Name - ACT BootCamp for Trauma "
    "- Event Type - General Meeting Lecture "
    "- Event Date: MULTI-DAY EVENT - 09/11/26 thru 09/13/26 (3 Days) "
    "- Event Campus - Rio Grande Campus "
    "- Event Location Space - (RGC) Center for Government and Civic Service (CGCS) (RGC3.3340) - Capacity 350 (3479 SF) "
    "- Event Setup Time - 1 Hour "
    "- Event Start Time - 8:30 AM "
    "- Event End Time - 5:30 PM "
    "- Event Breakdown Time - 30 Minutes "
    "- Event Expected Attendance - 150-200 "
    "- Event Site Walk Through Requested - No "
    "- Parking Needs: No Parking Needs Reported "
    "- Alcohol Requested - No "
    "- Event Purpose - This is a continuing education conference for mental health professionals. "
    "OCRM / MARKETING INFORMATION - Open to the General Public "
    "EVENT RESOURCES "
    "***AUDIO / VIDEO REQUESTED*** "
    "Complete A/V Setup By: 7:30 AM "
    "AV Check Needed "
    "Audio Support (Amplification or \"PA\" system) "
    "Projection of Digital Assets "
    "***FURNITURE REQUESTED*** "
    "Complete Furniture Setup By: 7:30 AM "
    "1 - Stage "
    "18 - Round Tables "
    "1 - Podiums "
    "150 - Chairs "
    "***REQUESTED LINENS*** "
    "1 - Stage Linen "
    "54 - Black - Round Table Linens "
    "***CATERING SERVICES*** "
    "- ACC Catering Requested - No "
    "Catering Order Submitted "
    "CGCS Dashboard Link: https://app.smartsheet.com/b/publish?EQBCT=1ba152f673c4429db66c148ace2e6e92 "
    "Thank you, Events Team"
)


# ============================================================
# is_smartsheet_intake
# ============================================================

class TestIsSmartsheetIntake:
    def test_valid_intake(self):
        assert is_smartsheet_intake(INTERNAL_SUBJECT, "automations@app.smartsheet.com") is True

    def test_valid_intake_external(self):
        assert is_smartsheet_intake(EXTERNAL_SUBJECT, "automations@app.smartsheet.com") is True

    def test_wrong_subject(self):
        assert is_smartsheet_intake("Re: Meeting Tomorrow", "automations@app.smartsheet.com") is False

    def test_wrong_sender(self):
        assert is_smartsheet_intake(INTERNAL_SUBJECT, "user@gmail.com") is False

    def test_both_wrong(self):
        assert is_smartsheet_intake("Hello", "user@gmail.com") is False

    def test_case_insensitive_sender(self):
        assert is_smartsheet_intake(INTERNAL_SUBJECT, "Automations@App.SMARTSHEET.com") is True

    def test_empty_strings(self):
        assert is_smartsheet_intake("", "") is False

    def test_partial_subject_match(self):
        # Must start with the prefix, not just contain it
        assert is_smartsheet_intake("Re: Notice of Event Space Request", "automations@app.smartsheet.com") is False


# ============================================================
# Internal request (Regina Schneider)
# ============================================================

class TestInternalRequest:
    def setup_method(self):
        self.result = parse_smartsheet_intake(INTERNAL_SUBJECT, INTERNAL_BODY)

    # Subject parsing
    def test_subject_event_name(self):
        assert self.result["subject_event_name"] == "Braver Angels Summer Workshop: Depolarizing from Within"

    def test_subject_date(self):
        assert self.result["subject_date"] == "06/25/26"

    def test_subject_time_range(self):
        assert self.result["subject_time_range"] == "5:00 PM-9:00 PM"

    # Requestor fields
    def test_requestor_name(self):
        assert self.result["requestor_name"] == "Regina Schneider"

    def test_department(self):
        dept = self.result["department"]
        assert dept is not None
        assert "Service-Learning Program" in dept

    def test_organization_none_for_internal(self):
        assert self.result["organization"] is None

    def test_request_type(self):
        assert self.result["request_type"] == "Internal Request"

    def test_requestor_type(self):
        assert self.result["requestor_type"] == "An Employee of ACC"

    def test_requestor_email(self):
        assert self.result["requestor_email"] == "rschneid@austincc.edu"

    def test_requestor_phone(self):
        assert self.result["requestor_phone"] == "+1 (512) 223-7004"

    # Event fields
    def test_event_code(self):
        assert self.result["event_code"] == "1335"

    def test_event_status(self):
        assert self.result["event_status"] == "Pending"

    def test_event_name(self):
        assert self.result["event_name"] == "Braver Angels Summer Workshop: Depolarizing from Within"

    def test_event_type(self):
        assert self.result["event_type"] == "Other"

    def test_event_start_date(self):
        assert self.result["event_start_date"] == date(2026, 6, 25)

    def test_event_end_date_same_as_start(self):
        assert self.result["event_end_date"] == date(2026, 6, 25)

    def test_event_num_days(self):
        assert self.result["event_num_days"] == 1

    def test_event_campus(self):
        assert self.result["event_campus"] == "Rio Grande Campus"

    def test_event_location(self):
        assert self.result["event_location"] is not None
        assert "CGCS" in self.result["event_location"]

    def test_event_room(self):
        assert self.result["event_room"] == "RGC3.3340"

    def test_setup_time(self):
        assert self.result["setup_time"] == "1 Hour"

    def test_start_time(self):
        assert self.result["start_time"] == "5:00 PM"

    def test_end_time(self):
        assert self.result["end_time"] == "9:00 PM"

    def test_breakdown_time(self):
        assert self.result["breakdown_time"] == "1 Hour"

    def test_expected_attendance(self):
        assert self.result["expected_attendance"] == "90"

    def test_walkthrough_requested(self):
        assert self.result["walkthrough_requested"] is False

    def test_parking_needs(self):
        assert self.result["parking_needs"] is not None
        assert "No Parking" in self.result["parking_needs"]

    def test_alcohol_requested(self):
        assert self.result["alcohol_requested"] is False

    def test_event_purpose(self):
        assert self.result["event_purpose"] == "Professional Development"

    # No resource sections
    def test_av_not_requested(self):
        assert self.result["av_requested"] is False

    def test_furniture_not_requested(self):
        assert self.result["furniture_requested"] is False

    def test_catering_not_present(self):
        assert self.result["catering_requested"] is None

    # Derived
    def test_is_external(self):
        assert self.result["is_external"] is False

    def test_is_multi_day(self):
        assert self.result["is_multi_day"] is False

    # Dashboard
    def test_dashboard_link(self):
        assert self.result["smartsheet_dashboard_link"] == (
            "https://app.smartsheet.com/b/publish?EQBCT=1ba152f673c4429db66c148ace2e6e92"
        )


# ============================================================
# External request (Courtney Kendler-Gelety)
# ============================================================

class TestExternalRequest:
    def setup_method(self):
        self.result = parse_smartsheet_intake(EXTERNAL_SUBJECT, EXTERNAL_BODY)

    # Requestor fields
    def test_requestor_name(self):
        assert self.result["requestor_name"] == "Courtney Kendler-Gelety"

    def test_department_none_for_external(self):
        assert self.result["department"] is None

    def test_organization(self):
        assert self.result["organization"] == "Institute for Better Health"

    def test_request_type(self):
        assert self.result["request_type"] == "External Request"

    def test_requestor_type(self):
        assert "Community" in self.result["requestor_type"]

    def test_requestor_email(self):
        assert self.result["requestor_email"] == "courtney@ibh.com"

    def test_requestor_phone(self):
        assert self.result["requestor_phone"] == "+1 (248) 978-7787"

    # Multi-day dates
    def test_event_start_date(self):
        assert self.result["event_start_date"] == date(2026, 9, 11)

    def test_event_end_date(self):
        assert self.result["event_end_date"] == date(2026, 9, 13)

    def test_event_num_days(self):
        assert self.result["event_num_days"] == 3

    def test_is_multi_day(self):
        assert self.result["is_multi_day"] is True

    # Event fields
    def test_event_code(self):
        assert self.result["event_code"] == "1238"

    def test_event_name(self):
        assert self.result["event_name"] == "ACT BootCamp for Trauma"

    def test_event_type(self):
        assert self.result["event_type"] == "General Meeting Lecture"

    def test_breakdown_time(self):
        assert self.result["breakdown_time"] == "30 Minutes"

    # Attendance range
    def test_expected_attendance_range(self):
        assert self.result["expected_attendance"] == "150-200"

    # Event purpose
    def test_event_purpose(self):
        assert "continuing education" in self.result["event_purpose"]

    # AV section
    def test_av_requested(self):
        assert self.result["av_requested"] is True

    def test_av_setup_by(self):
        assert self.result["av_setup_by"] == "7:30 AM"

    def test_av_details_not_empty(self):
        assert len(self.result["av_details"]) > 0

    def test_av_details_contain_items(self):
        details_text = " ".join(self.result["av_details"])
        assert "AV Check" in details_text or "Audio" in details_text or "Projection" in details_text

    # Furniture section
    def test_furniture_requested(self):
        assert self.result["furniture_requested"] is True

    def test_furniture_setup_by(self):
        assert self.result["furniture_setup_by"] == "7:30 AM"

    def test_furniture_items(self):
        items = self.result["furniture_items"]
        assert len(items) >= 3
        item_names = {i["item"] for i in items}
        assert "Round Tables" in item_names
        assert "Chairs" in item_names

    def test_furniture_round_tables_qty(self):
        for item in self.result["furniture_items"]:
            if item["item"] == "Round Tables":
                assert item["qty"] == 18
                break
        else:
            raise AssertionError("Round Tables not found")

    def test_furniture_chairs_qty(self):
        for item in self.result["furniture_items"]:
            if item["item"] == "Chairs":
                assert item["qty"] == 150
                break
        else:
            raise AssertionError("Chairs not found")

    # Linens
    def test_linens_requested(self):
        linens = self.result["linens_requested"]
        assert len(linens) >= 1

    def test_linen_round_table(self):
        linens = self.result["linens_requested"]
        found = any("Round Table" in l["item"] for l in linens)
        assert found

    def test_linen_qty(self):
        for l in self.result["linens_requested"]:
            if "Round Table" in l["item"]:
                assert l["qty"] == 54
                break

    # Catering
    def test_catering_requested(self):
        assert self.result["catering_requested"] is False

    # Derived
    def test_is_external(self):
        assert self.result["is_external"] is True

    # Dashboard
    def test_dashboard_link(self):
        assert "smartsheet.com" in self.result["smartsheet_dashboard_link"]

    # Subject
    def test_subject_event_name(self):
        assert self.result["subject_event_name"] == "ACT BootCamp for Trauma"

    def test_subject_date(self):
        assert self.result["subject_date"] == "09/11/26"

    def test_subject_time_range(self):
        assert self.result["subject_time_range"] == "8:30 AM-5:30 PM"


# ============================================================
# Missing optional sections
# ============================================================

MINIMAL_SUBJECT = "Notice of Event Space Request - Center for Government and Civic Service - RGC | Minimal Event | 01/15/27 | 9:00 AM-12:00 PM"

MINIMAL_BODY = (
    "Greetings Center for Government and Civic Service Team, "
    "These are the event details: "
    "REQUESTOR "
    "- Event Requestor Name - Test Person "
    "- Request Type - Internal Request "
    "- Event Requestor Email - test@austincc.edu "
    "EVENT "
    "- Event Code - 9999 "
    "- Event Status - Pending "
    "- Event Name - Minimal Event "
    "- Event Date: 01/15/27 (1 Day) "
    "- Event Start Time - 9:00 AM "
    "- Event End Time - 12:00 PM "
    "CGCS Dashboard Link: https://app.smartsheet.com/b/publish?EQBCT=abc123 "
    "Thank you, Events Team"
)


class TestMinimalRequest:
    def setup_method(self):
        self.result = parse_smartsheet_intake(MINIMAL_SUBJECT, MINIMAL_BODY)

    def test_requestor_name(self):
        assert self.result["requestor_name"] == "Test Person"

    def test_department_missing(self):
        assert self.result["department"] is None

    def test_organization_missing(self):
        assert self.result["organization"] is None

    def test_requestor_phone_missing(self):
        assert self.result["requestor_phone"] is None

    def test_setup_time_missing(self):
        assert self.result["setup_time"] is None

    def test_breakdown_time_missing(self):
        assert self.result["breakdown_time"] is None

    def test_expected_attendance_missing(self):
        assert self.result["expected_attendance"] is None

    def test_walkthrough_missing(self):
        assert self.result["walkthrough_requested"] is None

    def test_alcohol_missing(self):
        assert self.result["alcohol_requested"] is None

    def test_av_not_present(self):
        assert self.result["av_requested"] is False
        assert self.result["av_details"] == []

    def test_furniture_not_present(self):
        assert self.result["furniture_requested"] is False
        assert self.result["furniture_items"] == []

    def test_linens_not_present(self):
        assert self.result["linens_requested"] == []

    def test_catering_not_present(self):
        assert self.result["catering_requested"] is None

    def test_event_date_still_parsed(self):
        assert self.result["event_start_date"] == date(2027, 1, 15)

    def test_is_external_false(self):
        assert self.result["is_external"] is False

    def test_is_multi_day_false(self):
        assert self.result["is_multi_day"] is False


# ============================================================
# Edge cases
# ============================================================

class TestEdgeCases:
    def test_empty_body(self):
        result = parse_smartsheet_intake("Notice of Event Space Request - RGC", "")
        assert result["requestor_name"] is None
        assert result["event_code"] is None
        assert result["av_requested"] is False

    def test_empty_subject(self):
        result = parse_smartsheet_intake("", INTERNAL_BODY)
        assert result["subject_event_name"] is None
        assert result["requestor_name"] == "Regina Schneider"

    def test_completely_empty(self):
        result = parse_smartsheet_intake("", "")
        assert isinstance(result, dict)
        assert result["requestor_name"] is None

    def test_multi_day_date_parsing(self):
        body = "- Event Date: MULTI-DAY EVENT - 12/01/26 thru 12/05/26 (5 Days) "
        result = parse_smartsheet_intake("", body)
        assert result["event_start_date"] == date(2026, 12, 1)
        assert result["event_end_date"] == date(2026, 12, 5)
        assert result["event_num_days"] == 5
        assert result["is_multi_day"] is True

    def test_single_day_date_parsing(self):
        body = "- Event Date: 03/15/27 (1 Day) "
        result = parse_smartsheet_intake("", body)
        assert result["event_start_date"] == date(2027, 3, 15)
        assert result["event_end_date"] == date(2027, 3, 15)
        assert result["event_num_days"] == 1
        assert result["is_multi_day"] is False

    def test_attendance_range_preserved_as_string(self):
        body = "- Event Expected Attendance - 150-200 "
        result = parse_smartsheet_intake("", body)
        assert result["expected_attendance"] == "150-200"

    def test_attendance_single_number(self):
        body = "- Event Expected Attendance - 90 "
        result = parse_smartsheet_intake("", body)
        assert result["expected_attendance"] == "90"

    def test_room_code_extraction(self):
        body = "- Event Location Space - (RGC) Center for CGCS (RGC3.3340) - Capacity 350 "
        result = parse_smartsheet_intake("", body)
        assert result["event_room"] == "RGC3.3340"

    def test_no_room_code(self):
        body = "- Event Location Space - Some Other Building "
        result = parse_smartsheet_intake("", body)
        assert result["event_room"] is None

    def test_dashboard_link_extracted(self):
        body = "CGCS Dashboard Link: https://app.smartsheet.com/b/publish?EQBCT=xyz123 Thank you"
        result = parse_smartsheet_intake("", body)
        assert result["smartsheet_dashboard_link"] == "https://app.smartsheet.com/b/publish?EQBCT=xyz123"

    def test_catering_requested_yes(self):
        body = "- ACC Catering Requested - Yes Catering Order Submitted "
        result = parse_smartsheet_intake("", body)
        assert result["catering_requested"] is True

    def test_catering_not_submitted(self):
        body = "- ACC Catering Requested - No No Catering Order Submitted "
        result = parse_smartsheet_intake("", body)
        assert result["catering_requested"] is False
        assert result["catering_order_submitted"] is False
