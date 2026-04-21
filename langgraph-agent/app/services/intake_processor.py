"""Intake processor — builds P.E.T. spreadsheet rows and calendar HOLD events
from parsed Smartsheet intake data.

All functions are pure (no I/O): they take a parsed intake dict and return
structured data ready to be written to Sheets/Calendar.
"""

from __future__ import annotations

import re
from datetime import date

from app.cgcs_constants import COST_CENTER


# ============================================================
# Event classification
# ============================================================

def classify_event_type(parsed: dict) -> str:
    """Determine CGCS/AMI/STEWARDSHIP classification from request data.

    - Internal Request → "CGCS" (S-EVENT)
    - External Request with community/vendor requestor → "AMI" (A-EVENT)
    - Otherwise → "CGCS"
    """
    request_type = (parsed.get("request_type") or "").lower()
    requestor_type = (parsed.get("requestor_type") or "").lower()

    if "external" in request_type:
        if "community" in requestor_type or "vendor" in requestor_type:
            return "AMI"
    return "CGCS"


# ============================================================
# Furniture / AV / needs summaries
# ============================================================

def _furniture_summary(parsed: dict) -> str:
    """Build a summary string from furniture_items list."""
    items = parsed.get("furniture_items") or []
    if not items:
        return ""
    return ", ".join(f"{i['qty']} {i['item']}" for i in items)


def _has_stage(parsed: dict) -> str:
    """Return 'Yes' or 'No' based on whether furniture includes a Stage."""
    items = parsed.get("furniture_items") or []
    for item in items:
        if "stage" in item.get("item", "").lower():
            return "Yes"
    return "No"


def _additional_needs_summary(parsed: dict) -> str:
    """Combine AV, catering, linens, and other needs into a summary."""
    parts = []

    if parsed.get("av_requested"):
        av_items = parsed.get("av_details") or []
        if av_items:
            parts.append("AV: " + ", ".join(av_items))
        else:
            parts.append("AV requested")

    linens = parsed.get("linens_requested") or []
    if linens:
        linen_str = ", ".join(f"{l['qty']} {l['item']}" for l in linens)
        parts.append("Linens: " + linen_str)

    if parsed.get("catering_requested"):
        parts.append("ACC Catering requested")

    if parsed.get("alcohol_requested"):
        parts.append("Alcohol requested")

    return "; ".join(parts) if parts else ""


def _format_event_date(d: date | None) -> str:
    """Format a date as 'Month Day' (e.g. 'June 25')."""
    if not d:
        return ""
    return d.strftime("%B %-d")


def _format_room_display(event_room: str | None) -> str:
    """Format room code for display with full name + code.

    'RGC3.3340' -> 'CGCS Main Hall (RGC3.3340)'
    'RGC3.3328' -> 'CGCS Classroom (RGC3.3328)'
    Unknown code -> returned as-is.
    Empty/None   -> empty string.
    """
    if not event_room:
        return ""
    room = event_room.strip()
    # Match like "RGC3.3340" and capture the number after the dot
    m = re.search(r"\.(\d+)", room)
    if m:
        room_num = m.group(1)
        if room_num == "3340":
            return f"CGCS Main Hall ({room})"
        if room_num == "3328":
            return f"CGCS Classroom ({room})"
        return room  # unknown room number, preserve full code
    return room


# ============================================================
# P.E.T. Row Builder
# ============================================================

def build_pet_row(parsed: dict) -> list[str]:
    """Build a 20-column P.E.T. spreadsheet row from parsed Smartsheet intake.

    Columns match PET_COLUMNS order in cgcs_constants.py:
    1.  Event Name
    2.  Status
    3.  Entered into Calendar
    4.  CGCS/AMI/STEWARDSHIP
    5.  Date of event
    6.  Time of event
    7.  CGCS Lead
    8.  Contact Information/Event Lead
    9.  Attendance
    10. Money Expected
    11. Ad Astra Number #
    12. TDX Request #
    13. Floor Layout
    14. Stage?
    15. Breakdown Time Needed
    16. Additional Needs
    17. Walkthrough Date
    18. Invoice Generated
    19. Rooms
    20. CGCS Labor
    """
    event_name = parsed.get("event_name") or ""
    start_date = parsed.get("event_start_date")
    start_time = parsed.get("start_time") or ""
    end_time = parsed.get("end_time") or ""

    # Contact info
    contact_parts = []
    if parsed.get("requestor_name"):
        contact_parts.append(parsed["requestor_name"])
    if parsed.get("requestor_email"):
        contact_parts.append(parsed["requestor_email"])
    if parsed.get("requestor_phone"):
        contact_parts.append(parsed["requestor_phone"])
    contact_info = ", ".join(contact_parts)

    # Time range
    time_range = ""
    if start_time and end_time:
        time_range = f"{start_time} - {end_time}"

    # TDX request — only if AV is requested
    tdx = "TBD" if parsed.get("av_requested") else ""

    return [
        event_name,                              # 1. Event Name
        "Pending",                               # 2. Status
        "Yes",                                   # 3. Entered into Calendar
        classify_event_type(parsed),             # 4. CGCS/AMI/STEWARDSHIP
        _format_event_date(start_date),          # 5. Date of event
        time_range,                              # 6. Time of event
        "TBD",                                   # 7. CGCS Lead
        contact_info,                            # 8. Contact Information/Event Lead
        parsed.get("expected_attendance") or "",  # 9. Attendance
        "",                                      # 10. Money Expected
        "Pending",                               # 11. Ad Astra Number #
        tdx,                                     # 12. TDX Request #
        _furniture_summary(parsed),              # 13. Floor Layout
        _has_stage(parsed),                      # 14. Stage?
        parsed.get("breakdown_time") or "",      # 15. Breakdown Time Needed
        _additional_needs_summary(parsed),       # 16. Additional Needs
        "",                                      # 17. Walkthrough Date
        "No",                                    # 18. Invoice Generated
        _format_room_display(parsed.get("event_room")),  # 19. Rooms
        "",                                      # 20. CGCS Labor
    ]


# ============================================================
# Calendar HOLD Builder
# ============================================================

def _parse_duration_to_hours(duration_str: str | None) -> float:
    """Parse setup/breakdown time string to hours.

    Examples: '1 Hour' → 1.0, '30 Minutes' → 0.5, '2 Hours' → 2.0
    """
    if not duration_str:
        return 0.0
    d = duration_str.lower()
    hours = re.search(r"(\d+)\s*hour", d)
    minutes = re.search(r"(\d+)\s*min", d)
    total = 0.0
    if hours:
        total += float(hours.group(1))
    if minutes:
        total += float(minutes.group(1)) / 60.0
    return total


def _adjust_time(time_str: str, offset_hours: float, direction: str = "subtract") -> str:
    """Adjust a time string by offset_hours. Returns HH:MM format.

    time_str can be '5:00 PM', '17:00', '8:30 AM', etc.
    direction: 'subtract' to go earlier, 'add' to go later.
    """
    from app.services.date_utils import _normalize_time
    normalized = _normalize_time(time_str)
    if not normalized:
        return time_str

    h, m = int(normalized[:2]), int(normalized[3:])
    total_minutes = h * 60 + m
    offset_minutes = int(offset_hours * 60)

    if direction == "subtract":
        total_minutes -= offset_minutes
    else:
        total_minutes += offset_minutes

    total_minutes = max(0, min(total_minutes, 23 * 60 + 59))
    new_h = total_minutes // 60
    new_m = total_minutes % 60
    return f"{new_h:02d}:{new_m:02d}"


def build_calendar_hold(parsed: dict) -> dict:
    """Build a Google Calendar HOLD event dict from parsed Smartsheet intake.

    Returns:
        {
            "title": str,
            "start_date": str (ISO),
            "end_date": str (ISO),
            "start_time": str (HH:MM, adjusted for setup),
            "end_time": str (HH:MM, adjusted for breakdown),
            "location": str,
            "description": str,
        }
    """
    event_name = parsed.get("event_name") or "Unnamed Event"
    title = f"HOLD - {event_name}"

    start_date = parsed.get("event_start_date")
    end_date = parsed.get("event_end_date") or start_date

    start_date_str = start_date.isoformat() if start_date else ""
    end_date_str = end_date.isoformat() if end_date else start_date_str

    # Adjust times for setup and breakdown
    raw_start = parsed.get("start_time") or "09:00"
    raw_end = parsed.get("end_time") or "17:00"
    setup_hours = _parse_duration_to_hours(parsed.get("setup_time"))
    breakdown_hours = _parse_duration_to_hours(parsed.get("breakdown_time"))

    adjusted_start = _adjust_time(raw_start, setup_hours, "subtract")
    adjusted_end = _adjust_time(raw_end, breakdown_hours, "add")

    location = parsed.get("event_location") or ""
    dept_or_org = parsed.get("department") or parsed.get("organization") or "TBD"
    is_external = parsed.get("is_external", False)
    event_code = parsed.get("event_code") or ""

    # Build the CGCS calendar description
    description_lines = [
        f"Event Name: {event_name}",
        "Status: Pending",
        f"Department: {dept_or_org}",
        f"Date of Event: {_format_event_date(start_date)}",
        f"Time of Event: {raw_start} - {raw_end}",
        "CGCS Lead: TBD",
        f"Contact Name / Event Lead: {parsed.get('requestor_name') or 'TBD'}",
        f"Organization / Department: {dept_or_org}",
        f"Email: {parsed.get('requestor_email') or 'TBD'}",
        f"Phone: {parsed.get('requestor_phone') or 'TBD'}",
        f"Attendance Estimate: {parsed.get('expected_attendance') or 'TBD'}",
        f"Restricted: {'External' if is_external else 'Internal'}",
        "Ad Astra #: Pending",
        "TDX Request #: TBD",
        f"Room(s) Reserved: {_format_room_display(parsed.get('event_room'))}",
        f"Floor Layout: {_furniture_summary(parsed) or 'TBD'}",
        f"Stage Needed: {_has_stage(parsed)}",
        f"Breakdown Time Needed: {parsed.get('breakdown_time') or 'TBD'}",
        f"Additional Needs: {_additional_needs_summary(parsed) or 'N/A'}",
        "Walkthrough Date: TBD",
        f"Money Expected: {'TBD' if is_external else 'N/A'}",
        "Invoice Generated: No",
        "Deposit Paid: No",
        "Payment Method: TBD",
        f"Cost Center: {COST_CENTER}",
        "Spend Category: 5001",
        "Tax Exempt: TBD",
        f"Notes: Auto-generated from Smartsheet intake {event_code}",
    ]
    description = "\n".join(description_lines)

    return {
        "title": title,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "start_time": adjusted_start,
        "end_time": adjusted_end,
        "location": location,
        "description": description,
    }
