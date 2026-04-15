"""Smartsheet intake email parser — extracts structured event data from
'Notice of Event Space Request' notification emails sent by Smartsheet automations.

These emails arrive from automations@app.smartsheet.com with a predictable
field layout: '- Field Name - Value' pairs, plus optional resource sections.
"""

from __future__ import annotations

import re
from datetime import datetime, date


# ============================================================
# Detection
# ============================================================

SMARTSHEET_SUBJECT_PREFIX = "Notice of Event Space Request"


def is_smartsheet_intake(subject: str, sender: str) -> bool:
    """Return True if this email is a Smartsheet intake notification."""
    return (
        subject.strip().startswith(SMARTSHEET_SUBJECT_PREFIX)
        and "smartsheet.com" in sender.lower()
    )


# ============================================================
# Known field markers — used to find boundaries between fields
# ============================================================

# These are the known field labels that appear as "- Label -" or "- Label:"
# in the email body. Order doesn't matter — they're used to build a
# terminator regex so we know where one field's value ends.
_KNOWN_FIELDS = [
    "Event Requestor Name",
    "Department:",
    "Organization:",
    "Request Type",
    "Event Requestor Type",
    "Event Requestor Email",
    "Event Requestor Contact Number",
    "Event Code",
    "Event Status",
    "Campus Manager",
    "Event Name",
    "Event Type",
    "Event Date:",
    "Event Campus",
    "Event Location Space",
    "Event Setup Time",
    "Event Start Time",
    "Event End Time",
    "Event Breakdown Time",
    "Event Expected Attendance",
    "Event Site Walk Through Requested",
    "Parking Needs:",
    "Alcohol Requested",
    "Event Purpose",
    "ACC Catering Requested",
]

# Build a regex alternation of all known field markers, escaped.
# This is used as a lookahead to terminate value capture.
_FIELD_BOUNDARY = "|".join(re.escape(f) for f in _KNOWN_FIELDS)

# Terminators: next known field, section headers, or end-of-content markers
_TERMINATORS = (
    r"(?="
    r"\s*-\s*(?:" + _FIELD_BOUNDARY + r")"  # next known field
    r"|\s*REQUESTOR\b"
    r"|\s+EVENT\s+-\s*Event\b"
    r"|\s*OCRM\b"
    r"|\s*\*{3}"           # *** section markers
    r"|\s*#INVALID"
    r"|\s*\*\*NO\s+OCRM"  # **NO OCRM
    r"|\s*CGCS\s+Dashboard"
    r"|\s*Thank\s+you"
    r"|$"
    r")"
)


# ============================================================
# Field extraction helpers
# ============================================================

def _field(body: str, name: str) -> str | None:
    """Extract a value for '- {name} - {value}' pattern.

    Uses known field names as terminators so hyphens inside values
    (names, phone numbers, attendance ranges) are preserved.
    """
    pattern = re.compile(
        r"-\s*" + re.escape(name) + r"\s*-\s*(.+?)" + _TERMINATORS,
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.search(body)
    if m:
        return m.group(1).strip()
    return None


def _field_colon(body: str, name: str) -> str | None:
    """Extract value for '- Field: - Value' or '- Field: Value' pattern.

    The Smartsheet format uses '- Department: - Value' where there's a
    separator '- ' between the colon and the actual value.
    """
    # Try "- Field: - Value" first (Smartsheet's format)
    pattern = re.compile(
        r"-?\s*" + re.escape(name) + r"\s*-\s*(.+?)" + _TERMINATORS,
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.search(body)
    if m:
        return m.group(1).strip()

    # Fallback: "Field: Value" without the separator dash
    pattern2 = re.compile(
        r"-?\s*" + re.escape(name) + r"\s+(.+?)" + _TERMINATORS,
        re.IGNORECASE | re.DOTALL,
    )
    m2 = pattern2.search(body)
    if m2:
        return m2.group(1).strip()

    return None


def _yes_no(value: str | None) -> bool | None:
    """Convert Yes/No string to boolean, None if missing."""
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("yes", "true"):
        return True
    if v in ("no", "false"):
        return False
    return None


# ============================================================
# Subject line parsing
# ============================================================

def _parse_subject(subject: str) -> dict:
    """Extract event name, date, and time range from the subject line.

    Format: 'Notice of ... - RGC | Event Name | MM/DD/YY | H:MM AM-H:MM PM'
    """
    result: dict = {
        "subject_event_name": None,
        "subject_date": None,
        "subject_time_range": None,
    }
    parts = subject.split("|")
    if len(parts) >= 2:
        result["subject_event_name"] = parts[1].strip()
    if len(parts) >= 3:
        result["subject_date"] = parts[2].strip()
    if len(parts) >= 4:
        result["subject_time_range"] = parts[3].strip()
    return result


# ============================================================
# Date parsing
# ============================================================

_DATE_FMT = "%m/%d/%y"


def _parse_event_dates(raw: str | None) -> dict:
    """Parse event date field into start/end dates and num_days.

    Single day:  '06/25/26 (1 Day)'
    Multi-day:   'MULTI-DAY EVENT - 09/11/26 thru 09/13/26 (3 Days)'
    """
    result: dict = {
        "event_date_raw": raw,
        "event_start_date": None,
        "event_end_date": None,
        "event_num_days": None,
    }
    if not raw:
        return result

    # Extract number of days
    days_match = re.search(r"\((\d+)\s*Days?\)", raw, re.IGNORECASE)
    if days_match:
        result["event_num_days"] = int(days_match.group(1))

    # Multi-day: "MM/DD/YY thru MM/DD/YY"
    multi = re.search(r"(\d{2}/\d{2}/\d{2})\s+thru\s+(\d{2}/\d{2}/\d{2})", raw)
    if multi:
        try:
            result["event_start_date"] = datetime.strptime(multi.group(1), _DATE_FMT).date()
            result["event_end_date"] = datetime.strptime(multi.group(2), _DATE_FMT).date()
        except ValueError:
            pass
        return result

    # Single day: "MM/DD/YY"
    single = re.search(r"(\d{2}/\d{2}/\d{2})", raw)
    if single:
        try:
            d = datetime.strptime(single.group(1), _DATE_FMT).date()
            result["event_start_date"] = d
            result["event_end_date"] = d
        except ValueError:
            pass

    return result


# ============================================================
# Room code extraction
# ============================================================

def _extract_room_code(location: str | None) -> str | None:
    """Extract room code like 'RGC3.3340' from location string.

    Example input: '(RGC) Center for ... (RGC3.3340) - Capacity 350 (3479 SF)'
    """
    if not location:
        return None
    m = re.search(r"\(([A-Z]{2,5}\d+\.\d+)\)", location)
    if m:
        return m.group(1)
    return None


# ============================================================
# Resource section parsers
# ============================================================

def _parse_av_section(body: str) -> dict:
    """Parse the AUDIO / VIDEO REQUESTED section."""
    result: dict = {
        "av_requested": False,
        "av_setup_by": None,
        "av_details": [],
    }
    av_match = re.search(
        r"\*{3}AUDIO\s*/\s*VIDEO\s+REQUESTED\*{3}(.*?)(?=\*{3}|CGCS Dashboard|$)",
        body, re.IGNORECASE | re.DOTALL,
    )
    if not av_match:
        return result

    result["av_requested"] = True
    section = av_match.group(1).strip()

    # Extract setup time — ends at the next capitalized phrase
    setup_m = re.search(r"Complete\s+A/V\s+Setup\s+By:\s*(\d+:\d+\s*(?:AM|PM))", section, re.IGNORECASE)
    if setup_m:
        result["av_setup_by"] = setup_m.group(1).strip()

    # AV items: everything after the setup-by line
    # Remove the setup-by portion, then extract individual items
    after_setup = re.sub(
        r"Complete\s+A/V\s+Setup\s+By:\s*\d+:\d+\s*(?:AM|PM)\s*",
        "", section, flags=re.IGNORECASE,
    ).strip()

    if after_setup:
        # Try newline-separated first
        lines = [l.strip() for l in after_setup.split("\n") if l.strip()]
        if len(lines) > 1:
            result["av_details"] = lines
        else:
            # Flat text: split on boundaries between AV item phrases
            # Items typically start with a capital letter after a space
            items = re.split(r'\s{2,}', after_setup)
            if len(items) == 1:
                # Single blob — split on known AV keywords
                items = re.findall(
                    r'(?:AV Check Needed|Audio Support[^A-Z]*|Projection of Digital Assets|[A-Z][a-z].*?)(?=\s+(?:AV|Audio|Projection|$))',
                    after_setup,
                )
                if not items:
                    items = [after_setup]
            result["av_details"] = [i.strip() for i in items if i.strip()]

    return result


def _parse_furniture_section(body: str) -> dict:
    """Parse the FURNITURE REQUESTED section."""
    result: dict = {
        "furniture_requested": False,
        "furniture_setup_by": None,
        "furniture_items": [],
        "linens_requested": [],
    }
    furn_match = re.search(
        r"\*{3}FURNITURE\s+REQUESTED\*{3}(.*?)(?=\*{3}|CGCS Dashboard|$)",
        body, re.IGNORECASE | re.DOTALL,
    )
    if not furn_match:
        return result

    result["furniture_requested"] = True
    section = furn_match.group(1)

    setup_m = re.search(r"Complete\s+Furniture\s+Setup\s+By:\s*(\d+:\d+\s*(?:AM|PM))", section, re.IGNORECASE)
    if setup_m:
        result["furniture_setup_by"] = setup_m.group(1).strip()

    # Furniture items: "18 - Round Tables", "150 - Chairs", etc.
    for m in re.finditer(r"(\d+)\s*-\s*([A-Za-z][A-Za-z ]+?)(?=\s+\d+\s*-|\s*\*{3}|\s*CGCS|$)", section):
        result["furniture_items"].append({
            "qty": int(m.group(1)),
            "item": m.group(2).strip(),
        })

    # Linens section may be within or after furniture
    linen_match = re.search(
        r"\*{3}REQUESTED\s+LINENS\*{3}(.*?)(?=\*{3}|CGCS Dashboard|$)",
        body, re.IGNORECASE | re.DOTALL,
    )
    if linen_match:
        linen_section = linen_match.group(1)
        for m in re.finditer(r"(\d+)\s*-\s*([A-Za-z][A-Za-z \-]+?)(?=\s+\d+\s*-|\s*\*{3}|\s*CGCS|$)", linen_section):
            result["linens_requested"].append({
                "qty": int(m.group(1)),
                "item": m.group(2).strip(),
            })

    return result


def _parse_catering_section(body: str) -> dict:
    """Parse catering information."""
    result: dict = {
        "catering_requested": None,
        "catering_order_submitted": None,
    }
    catering_m = re.search(r"ACC\s+Catering\s+Requested\s*-\s*(Yes|No)", body, re.IGNORECASE)
    if catering_m:
        result["catering_requested"] = catering_m.group(1).strip().lower() == "yes"

    if "Catering Order Submitted" in body:
        if re.search(r"No\s+Catering\s+Order\s+Submitted", body, re.IGNORECASE):
            result["catering_order_submitted"] = False
        elif re.search(r"Catering\s+Order\s+Submitted", body, re.IGNORECASE):
            result["catering_order_submitted"] = True

    return result


# ============================================================
# Dashboard link
# ============================================================

def _extract_dashboard_link(body: str) -> str | None:
    """Extract the Smartsheet dashboard URL."""
    m = re.search(r"(https?://app\.smartsheet\.com/\S+)", body)
    if m:
        return m.group(1)
    return None


# ============================================================
# Main parser
# ============================================================

def parse_smartsheet_intake(subject: str, body: str) -> dict:
    """Parse a Smartsheet 'Notice of Event Space Request' email.

    Returns a dict with all extracted fields. Missing fields are None.
    Never raises — returns partial results on malformed input.
    """
    result: dict = {}

    # Subject line fields
    result.update(_parse_subject(subject))

    # Requestor fields
    result["requestor_name"] = _field(body, "Event Requestor Name")
    result["department"] = _field_colon(body, "Department:")
    result["organization"] = _field_colon(body, "Organization:")
    result["request_type"] = _field(body, "Request Type")
    result["requestor_type"] = _field(body, "Event Requestor Type")
    result["requestor_email"] = _field(body, "Event Requestor Email")
    result["requestor_phone"] = _field(body, "Event Requestor Contact Number")

    # Event fields
    result["event_code"] = _field(body, "Event Code")
    result["event_status"] = _field(body, "Event Status")
    result["event_name"] = _field(body, "Event Name")
    result["event_type"] = _field(body, "Event Type")

    # Event date — uses "Event Date:" with colon
    event_date_raw = _field_colon(body, "Event Date:")
    date_info = _parse_event_dates(event_date_raw)
    result.update(date_info)

    result["event_campus"] = _field(body, "Event Campus")

    location = _field(body, "Event Location Space")
    result["event_location"] = location
    result["event_room"] = _extract_room_code(location)

    result["setup_time"] = _field(body, "Event Setup Time")
    result["start_time"] = _field(body, "Event Start Time")
    result["end_time"] = _field(body, "Event End Time")
    result["breakdown_time"] = _field(body, "Event Breakdown Time")
    result["expected_attendance"] = _field(body, "Event Expected Attendance")
    result["walkthrough_requested"] = _yes_no(_field(body, "Event Site Walk Through Requested"))
    result["parking_needs"] = _field_colon(body, "Parking Needs:")
    result["alcohol_requested"] = _yes_no(_field(body, "Alcohol Requested"))

    # Event purpose — between "Event Purpose" and the next major section
    purpose_m = re.search(
        r"-\s*Event\s+Purpose\s*-\s*(.*?)(?=\s*(?:\*{3}|OCRM|#INVALID|\*\*NO\s+OCRM|CGCS\s+Dashboard|Thank\s+you|$))",
        body, re.IGNORECASE | re.DOTALL,
    )
    result["event_purpose"] = purpose_m.group(1).strip() if purpose_m else None

    # Resource sections
    av = _parse_av_section(body)
    result.update(av)

    furniture = _parse_furniture_section(body)
    result.update(furniture)

    catering = _parse_catering_section(body)
    result.update(catering)

    # Dashboard link
    result["smartsheet_dashboard_link"] = _extract_dashboard_link(body)

    # Derived booleans
    result["is_external"] = result.get("request_type") == "External Request"
    result["is_multi_day"] = (result.get("event_num_days") or 0) > 1

    return result
