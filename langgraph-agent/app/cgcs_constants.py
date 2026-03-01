"""CGCS operational constants — single source of truth for all operational data.

Import and use these constants everywhere instead of hardcoded values.
"""

from __future__ import annotations

import re

# ============================================================
# Staff & Admin
# ============================================================

STAFF_ROSTER: list[dict[str, str]] = [
    {"name": "Brenden Fogg", "email": "brenden.fogg@g.austincc.edu"},
    {"name": "Bryan Port", "email": "bryan.port@austincc.edu"},
    {"name": "Catherine Thomason", "email": "catherine.thomason@austincc.edu"},
    {"name": "Eimanie Thomas", "email": "eimanie.thomas@g.austincc.edu"},
    {"name": "Marisela Perez Maita", "email": "marisela.perezmaita@austincc.edu"},
    {"name": "Stefano Casafranca Laos", "email": "stefano.casafrancalaos@austincc.edu"},
    {"name": "Tzur Shalit", "email": "tzur.shalit@g.austincc.edu"},
    {"name": "Vanessa Trujano", "email": "vanessa.trujano@g.austincc.edu"},
]

MAX_LEADS_PER_STAFF_PER_MONTH = 3

ADMIN_EMAIL = "austin.wells@austincc.edu"
ADMIN_TITLE = "Strategic Planner for Community Relations & Environmental Affairs"

CGCS_ZOHO_EMAIL = "admin@cgcsacc.org"
ZOHO_USER_ID = "879105889"

CGCS_WEBSITE = "https://www.cgcsacc.org"

# ============================================================
# Auto-send & VIP
# ============================================================

AUTO_SEND_ALLOWLIST: set[str] = {
    "stefano.casafrancalaos@austincc.edu",
    "marisela.perez@austincc.edu",
}

VIP_SENDERS: dict[str, str] = {
    "michelle.raymond@austincc.edu": "ACC Strategic Planning",
}

VIP_KEYWORDS: list[str] = [
    "Office of the Chancellor",
]

ADASTRA_SENDER_EMAILS: set[str] = {
    "notifications@aais.com",
    "noreply@aais.com",
}

ADASTRA_SUBJECT_PATTERN = re.compile(r"Event Reservation #\d{8}-\d{5}")

# ============================================================
# Hours of Operation
# ============================================================

HOURS: dict[str, dict[str, str]] = {
    "mon_thu": {"open": "07:00", "close": "22:00", "events_start": "08:00", "events_end": "21:00"},
    "fri": {"open": "07:00", "close": "17:00", "events_start": "08:00", "events_end": "16:30"},
    "weekend": {"note": "Conditional: requires police ($65/hr) + police agreement + CGCS support staff"},
}

# ============================================================
# Deadlines (business days)
# ============================================================

DEADLINES: dict[str, int] = {
    "cgcs_response": 3,
    "tdx_av": 15,
    "walkthrough": 12,
    "catering_acc": 25,
    "run_of_show_furniture": 20,
}

# ============================================================
# Reminders
# ============================================================

REMINDER_INTERVALS: list[dict[str, int | str]] = [
    {"label": "30_day", "days": 30},
    {"label": "14_day", "days": 14},
    {"label": "7_day", "days": 7},
    {"label": "48_hour", "days": 2},
]

# ============================================================
# AMI Facility Pricing
# ============================================================

AMI_FACILITY_PRICING: dict[str, float] = {
    "morning": 500.0,
    "afternoon": 500.0,
    "evening": 500.0,
    "full_day": 1000.0,
    "extended": 1250.0,
    "fri_eve_weekend": 750.0,
    "weekend_hourly": 200.0,  # per hour
}

AMI_ADDONS: dict[str, dict] = {
    "av": {"rate": 60.0, "unit": "per_hour", "webcast_surcharge": 100.0},
    "acc_technician": {"rate": 160.0, "unit": "flat"},
    "furniture": {"rate": 250.0, "unit": "flat"},
    "round_tables": {"rate": 15.0, "unit": "each", "note": "Includes fresh black linens and ACC moving team"},
    "stage_setup": {"rate": 150.0, "unit": "flat"},
    "stage_teardown": {"rate": 100.0, "unit": "flat"},
    "admin_support": {"rate": 250.0, "unit": "up_to", "note": "Up to $250"},
    "signage": {"rate": 100.0, "unit": "flat"},
    "catering_coord": {"rate": 100.0, "unit": "surcharge"},
    "police": {"rate": 65.0, "unit": "per_hour", "minimum_hours": 4},
}

DEPOSIT_RATE = 0.05  # A-EVENT only
COST_CENTER = "CC05070"

# ============================================================
# Event Type Prefixes
# ============================================================

EVENT_PREFIXES: dict[str, str] = {
    "S-EVENT": "Service/partner/internal (no revenue)",
    "C-EVENT": "CGCS programs",
    "A-EVENT": "Paid/AMI (revenue-generating)",
}

# ============================================================
# P.E.T. Tracker Columns
# ============================================================

PET_COLUMNS: list[str] = [
    "Event Name",
    "Status",
    "Entered into Calendar",
    "CGCS/AMI/STEWARDSHIP",
    "Date of event",
    "Time of event",
    "CGCS Lead",
    "Contact Information/Event Lead",
    "Attendance",
    "Money Expected",
    "Ad Astra Number #",
    "TDX Request #",
    "Floor Layout",
    "Stage?",
    "Breakdown Time Needed",
    "Additional Needs",
    "Walkthrough Date",
    "Invoice Generated",
    "Rooms",
    "CGCS Labor",
]

# ============================================================
# Calendar Entry Template
# ============================================================

CALENDAR_ENTRY_TEMPLATE = """\
Event Name: {event_name}
Status: {status}
Department: CGCS
Date/Time: {date_time}
CGCS Lead: {cgcs_lead}
Contact Name/Event Lead: {contact_name}
Organization/Department: {organization}
Email: {email}
Phone: {phone}
Attendance Estimate: {attendance}
Restricted (Internal/External): {restricted}
Ad Astra #: {adastra_number}
TDX #: {tdx_number}
Room(s) Reserved: {rooms}
Floor Layout: {floor_layout}
Stage Needed (Yes/No): {stage_needed}
Breakdown Time: {breakdown_time}
Additional Needs: {additional_needs}
Walkthrough Date: {walkthrough_date}
Money Expected: {money_expected}
Invoice Generated (Yes/No): {invoice_generated}
Deposit Paid (Yes/No): {deposit_paid}
Payment Method: {payment_method}
Cost Center: {cost_center}
Spend Category: {spend_category}
Tax-Exempt Status: {tax_exempt}
Quote Amount: {quote_amount}
Final Invoice Amount: {final_invoice}
Notes on Billing Entity: {billing_notes}
Setup Details: {setup_details}
AV Details: {av_details}
Catering Details: {catering_details}
Police Coverage/Extended Hours (Yes/No): {police_coverage}
Marketing Needs: {marketing_needs}
CGCS Labor Notes: {cgcs_labor}
Post-Event Notes: {post_event_notes}"""


def build_calendar_description(**kwargs: str) -> str:
    """Fill the calendar entry template with provided values, defaulting to TBD/N/A."""
    defaults = {
        "event_name": "TBD",
        "status": "HOLD",
        "date_time": "TBD",
        "cgcs_lead": "TBD",
        "contact_name": "TBD",
        "organization": "TBD",
        "email": "TBD",
        "phone": "TBD",
        "attendance": "TBD",
        "restricted": "TBD",
        "adastra_number": "N/A",
        "tdx_number": "N/A",
        "rooms": "TBD",
        "floor_layout": "TBD",
        "stage_needed": "No",
        "breakdown_time": "TBD",
        "additional_needs": "N/A",
        "walkthrough_date": "TBD",
        "money_expected": "N/A",
        "invoice_generated": "No",
        "deposit_paid": "No",
        "payment_method": "N/A",
        "cost_center": COST_CENTER,
        "spend_category": "N/A",
        "tax_exempt": "TBD",
        "quote_amount": "N/A",
        "final_invoice": "N/A",
        "billing_notes": "N/A",
        "setup_details": "TBD",
        "av_details": "N/A",
        "catering_details": "N/A",
        "police_coverage": "No",
        "marketing_needs": "N/A",
        "cgcs_labor": "N/A",
        "post_event_notes": "N/A",
    }
    merged = {**defaults, **kwargs}
    return CALENDAR_ENTRY_TEMPLATE.format(**merged)


def build_calendar_title(event_type: str, event_name: str) -> str:
    """Build a calendar event title following CGCS naming convention.

    HOLD -> "HOLD - Name"
    S-EVENT -> "S-EVENT-Name"
    C-EVENT -> "C-EVENT-Name"
    A-EVENT -> "A-EVENT-Name"
    """
    if event_type == "HOLD":
        return f"HOLD - {event_name}"
    if event_type in EVENT_PREFIXES:
        return f"{event_type}-{event_name}"
    return event_name


def is_vip_sender(email: str, subject: str = "") -> bool:
    """Check if the sender is a VIP based on email or subject keywords."""
    email_lower = email.lower().strip()
    if email_lower in VIP_SENDERS:
        return True
    for keyword in VIP_KEYWORDS:
        if keyword.lower() in subject.lower():
            return True
    return False


def is_adastra_email(sender: str) -> bool:
    """Check if the email is from Ad Astra (AAIS)."""
    return sender.lower().strip() in ADASTRA_SENDER_EMAILS
