"""Intake request classifier and response drafter.

Classifies parsed Smartsheet intake requests as easy/mid/hard based on
deterministic rules, then drafts appropriate response and coordination emails.
"""

from __future__ import annotations

from datetime import date

from app.cgcs_constants import (
    COST_CENTER,
    DEADLINES,
    MINIMUM_LEAD_TIME_BD,
    MOVING_TEAM,
    MOVING_TEAM_CC,
    POLICE_CONTACT,
    CGCS_SYSTEM_EMAIL,
    calculate_business_days_before,
)
from app.services.date_utils import is_weekend_or_evening
from app.services.intake_processor import (
    _format_event_date,
    _format_room_display,
    _furniture_summary,
)


# ============================================================
# Classification
# ============================================================

def _parse_attendance_max(attendance: str | None) -> int:
    """Extract the maximum attendance number from a string like '150-200' or '90'."""
    if not attendance:
        return 0
    import re
    nums = re.findall(r"\d+", attendance)
    if nums:
        return max(int(n) for n in nums)
    return 0


def classify_request(parsed: dict) -> dict:
    """Classify an intake request as easy, mid, or hard.

    Returns:
        {
            "difficulty": "easy" | "mid" | "hard",
            "confidence": float 0.0-1.0,
            "reasoning": str,
            "auto_send": bool,
            "requires_police": bool,
            "requires_furniture_email": bool,
            "flags": list[str],
        }
    """
    flags: list[str] = []
    reasons: list[str] = []

    is_external = parsed.get("is_external", False)
    is_internal = not is_external
    is_multi_day = parsed.get("is_multi_day", False)
    av_requested = parsed.get("av_requested", False)
    furniture_requested = parsed.get("furniture_requested", False)
    catering_requested = parsed.get("catering_requested", False)
    alcohol_requested = parsed.get("alcohol_requested", False)
    attendance_max = _parse_attendance_max(parsed.get("expected_attendance"))

    # Determine weekend/evening
    event_date = parsed.get("event_start_date")
    end_time = parsed.get("end_time") or ""
    weekend_or_evening = False
    if event_date and end_time:
        weekend_or_evening = is_weekend_or_evening(event_date, end_time)

    requires_police = weekend_or_evening
    requires_furniture = furniture_requested

    # --- HARD triggers ---
    hard = False

    if alcohol_requested:
        hard = True
        flags.append("Alcohol requested — requires special coordination")
        reasons.append("alcohol requested")

    if weekend_or_evening:
        hard = True
        flags.append("Weekend/evening event — police coordination required")
        reasons.append("weekend/evening event requires police")

    if attendance_max >= 200:
        hard = True
        flags.append(f"Large event ({attendance_max} attendees) — extra coordination")
        reasons.append(f"large event ({attendance_max} attendees)")

    if catering_requested:
        hard = True
        flags.append("ACC Catering requested — catering coordination needed")
        reasons.append("ACC catering requested")

    if hard:
        return {
            "difficulty": "hard",
            "confidence": 0.9,
            "reasoning": "Hard: " + ", ".join(reasons),
            "auto_send": False,
            "requires_police": requires_police,
            "requires_furniture_email": requires_furniture,
            "flags": flags,
        }

    # --- MID triggers ---
    mid = False

    if is_external:
        mid = True
        reasons.append("external request")

    if furniture_requested:
        mid = True
        flags.append("Furniture coordination needed")
        reasons.append("furniture requested")

    if av_requested:
        mid = True
        flags.append("AV coordination needed — TDX request required")
        reasons.append("AV requested")

    if is_multi_day:
        mid = True
        flags.append("Multi-day event — extra scheduling complexity")
        reasons.append("multi-day event")

    if mid:
        return {
            "difficulty": "mid",
            "confidence": 0.8,
            "reasoning": "Mid: " + ", ".join(reasons),
            "auto_send": False,
            "requires_police": requires_police,
            "requires_furniture_email": requires_furniture,
            "flags": flags,
        }

    # --- EASY ---
    if is_internal:
        reasons.append("internal ACC request, standard room, no special needs")
    else:
        reasons.append("simple request with no special coordination")

    return {
        "difficulty": "easy",
        "confidence": 0.85,
        "reasoning": "Easy: " + ", ".join(reasons),
        "auto_send": True,
        "requires_police": False,
        "requires_furniture_email": False,
        "flags": [],
    }


# ============================================================
# Response Drafting
# ============================================================

def draft_intake_response(parsed: dict, classification: dict) -> dict:
    """Draft the response email for an intake request.

    For easy requests: full auto-reply with deadlines.
    For mid/hard: draft for Austin's approval queue.

    Returns:
        {
            "to": str,
            "subject": str,
            "body": str,
            "auto_send": bool,
            "classification": dict,
        }
    """
    event_name = parsed.get("event_name") or "your event"
    requestor_name = parsed.get("requestor_name") or ""
    requestor_email = parsed.get("requestor_email") or ""
    first_name = requestor_name.split()[0] if requestor_name else "there"
    event_date = parsed.get("event_start_date")
    event_date_str = _format_event_date(event_date)
    room = _format_room_display(parsed.get("event_room"))

    subject = f"CGCS Event Request \u2014 {event_name}"

    if classification.get("difficulty") == "easy":
        body = _draft_easy_response(
            first_name=first_name,
            event_name=event_name,
            event_date=event_date,
            event_date_str=event_date_str,
            start_time=parsed.get("start_time") or "",
            end_time=parsed.get("end_time") or "",
            room=room,
        )
    else:
        body = _draft_review_response(
            first_name=first_name,
            event_name=event_name,
            event_date_str=event_date_str,
            start_time=parsed.get("start_time") or "",
            end_time=parsed.get("end_time") or "",
            room=room,
            classification=classification,
        )

    return {
        "to": requestor_email,
        "subject": subject,
        "body": body,
        "auto_send": classification.get("auto_send", False),
        "classification": classification,
    }


def _draft_easy_response(
    first_name: str,
    event_name: str,
    event_date: date | None,
    event_date_str: str,
    start_time: str,
    end_time: str,
    room: str,
) -> str:
    """Draft the auto-reply for easy requests."""
    # Calculate deadlines
    deadline_lines = []
    if event_date:
        walkthrough_dl = calculate_business_days_before(event_date, DEADLINES["walkthrough"])
        catering_dl = calculate_business_days_before(event_date, DEADLINES["catering_acc"])
        furniture_dl = calculate_business_days_before(event_date, DEADLINES["run_of_show_furniture"])
        tdx_dl = calculate_business_days_before(event_date, DEADLINES["tdx_av"])

        deadline_lines = [
            f"- Catering plan: {_format_event_date(catering_dl)} (25 business days before)",
            f"- Furniture layout / run of show: {_format_event_date(furniture_dl)} (20 business days before)",
            f"- AV / TDX request: {_format_event_date(tdx_dl)} (15 business days before)",
            f"- Walkthrough: {_format_event_date(walkthrough_dl)} (12 business days before)",
        ]

    deadlines_text = "\n".join(deadline_lines) if deadline_lines else "- Deadlines will be provided once your date is confirmed."

    room_line = f" in {room}" if room else ""
    return (
        f"Hi {first_name},\n"
        f"\n"
        f"Thank you for your event space request for {event_name} on "
        f"{event_date_str} from {start_time} \u2013 {end_time}{room_line}.\n"
        f"\n"
        f"We've placed a temporary hold on the room while we confirm it is "
        f"available. Once confirmed, you will receive the attached User Agreement "
        f"to review and sign.\n"
        f"\n"
        f"Key deadlines for your event:\n"
        f"{deadlines_text}\n"
        f"\n"
        f"Please note:\n"
        f"- All future correspondence regarding this event will be through this "
        f"email thread.\n"
        f"- Parking information will be provided once your reservation is "
        f"confirmed.\n"
        f"\n"
        f"If you have any questions, please reply to this email.\n"
        f"\n"
        f"Warm regards,\n"
        f"CGCS Team\n"
        f"Center for Government & Civic Service\n"
        f"Austin Community College \u2014 Rio Grande Campus\n"
        f"admin@cgcs-acc.org | www.cgcsacc.org"
    )


def _draft_review_response(
    first_name: str,
    event_name: str,
    event_date_str: str,
    start_time: str,
    end_time: str,
    room: str,
    classification: dict,
) -> str:
    """Draft the response for mid/hard requests (goes to approval queue)."""
    flags = classification.get("flags") or []
    difficulty = classification.get("difficulty", "mid")

    coordination_lines = ""
    if flags:
        coordination_lines = (
            "\nBecause of the specifics of your request, our team is "
            "coordinating a few additional details before confirming:\n"
            + "\n".join(f"- {f}" for f in flags)
            + "\n"
        )

    room_line = f" in {room}" if room else ""
    return (
        f"Hi {first_name},\n"
        f"\n"
        f"Thank you for your event space request for {event_name} on "
        f"{event_date_str} from {start_time} \u2013 {end_time}{room_line}.\n"
        f"\n"
        f"We have received your request and our team is reviewing the details. "
        f"You will hear back from us within 2\u20134 business days with next "
        f"steps.\n"
        f"{coordination_lines}"
        f"\n"
        f"Please note:\n"
        f"- All future correspondence regarding this event will be through this "
        f"email thread.\n"
        f"- Once your reservation is confirmed, you will receive the attached "
        f"User Agreement along with parking information.\n"
        f"\n"
        f"If you have any questions in the meantime, please reply to this email.\n"
        f"\n"
        f"Warm regards,\n"
        f"CGCS Team\n"
        f"Center for Government & Civic Service\n"
        f"Austin Community College \u2014 Rio Grande Campus\n"
        f"admin@cgcs-acc.org | www.cgcsacc.org"
    )


# ============================================================
# Furniture Draft Email
# ============================================================

def draft_furniture_email(parsed: dict) -> dict | None:
    """Draft a furniture coordination email if furniture is requested.

    Returns None if no furniture requested. Otherwise:
        {"to": str, "cc": str, "subject": str, "body": str}
    """
    if not parsed.get("furniture_requested"):
        return None

    event_name = parsed.get("event_name") or "Unnamed Event"
    event_date = _format_event_date(parsed.get("event_start_date"))
    start_time = parsed.get("start_time") or ""
    end_time = parsed.get("end_time") or ""
    furniture_setup_by = parsed.get("furniture_setup_by") or "TBD"
    room = _format_room_display(parsed.get("event_room"))
    attendance = parsed.get("expected_attendance") or "TBD"

    furniture_items = parsed.get("furniture_items") or []
    furniture_lines = "\n".join(
        f"- {item['qty']} {item['item']}" for item in furniture_items
    ) if furniture_items else "- None specified"

    linens = parsed.get("linens_requested") or []
    linen_lines = "\n".join(
        f"- {item['qty']} {item['item']}" for item in linens
    ) if linens else "- None"

    to = ", ".join(MOVING_TEAM)
    cc = MOVING_TEAM_CC
    subject = f"Furniture Request \u2014 {event_name} on {event_date}"

    body = (
        f"Hi Tyler and Scott,\n"
        f"\n"
        f"We have a new event space request that requires furniture coordination:\n"
        f"\n"
        f"Event: {event_name}\n"
        f"Date: {event_date}\n"
        f"Time: {start_time} - {end_time} (Setup by: {furniture_setup_by})\n"
        f"Room: {room}\n"
        f"Expected Attendance: {attendance}\n"
        f"\n"
        f"Furniture requested:\n"
        f"{furniture_lines}\n"
        f"\n"
        f"Linens requested:\n"
        f"{linen_lines}\n"
        f"\n"
        f"Please confirm availability and timing for setup.\n"
        f"\n"
        f"Thank you,\n"
        f"CGCS Team"
    )

    return {"to": to, "cc": cc, "subject": subject, "body": body}


# ============================================================
# Police Draft Email
# ============================================================

def draft_police_email(parsed: dict) -> dict | None:
    """Draft a police coordination email if weekend/evening event.

    Returns None if police not required. Otherwise:
        {"to": str, "cc": str, "subject": str, "body": str}
    """
    event_date = parsed.get("event_start_date")
    end_time = parsed.get("end_time") or ""

    if not event_date or not is_weekend_or_evening(event_date, end_time):
        return None

    event_name = parsed.get("event_name") or "Unnamed Event"
    event_date_str = _format_event_date(event_date)
    start_time = parsed.get("start_time") or ""
    room = _format_room_display(parsed.get("event_room"))
    attendance = parsed.get("expected_attendance") or "TBD"
    event_type = parsed.get("event_type") or "TBD"

    # Determine weekend vs evening
    if event_date.weekday() >= 5:
        time_label = "weekend"
    else:
        time_label = "evening"

    to = POLICE_CONTACT
    cc = CGCS_SYSTEM_EMAIL
    subject = f"Police Coverage Request \u2014 {event_name} on {event_date_str}"

    body = (
        f"Hi Officer Ortiz,\n"
        f"\n"
        f"We have an upcoming event that requires police coverage:\n"
        f"\n"
        f"Event: {event_name}\n"
        f"Date: {event_date_str}\n"
        f"Time: {start_time} - {end_time}\n"
        f"Room: {room}\n"
        f"Expected Attendance: {attendance}\n"
        f"Event Type: {event_type}\n"
        f"\n"
        f"This is a {time_label} event. "
        f"Please confirm availability for police coverage.\n"
        f"\n"
        f"Thank you,\n"
        f"CGCS Team"
    )

    return {"to": to, "cc": cc, "subject": subject, "body": body}
