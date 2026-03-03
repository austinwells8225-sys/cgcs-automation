"""CGCS operational constants — single source of truth for all operational data.

Import and use these constants everywhere instead of hardcoded values.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

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

LABOR_RATES: dict[str, dict] = {
    "director": {
        "staff": ["Bryan Port"],
        "hourly_rate": 66.00,
        "role": "Director / Event Lead",
    },
    "intern_lead": {
        "staff": [
            "Brenden Fogg",
            "Catherine Thomason",
            "Eimanie Thomas",
            "Marisela Perez Maita",
            "Stefano Casafranca Laos",
            "Tzur Shalit",
            "Vanessa Trujano",
        ],
        "hourly_rate": 25.00,
        "role": "Intern Event Lead",
    },
    "intake_processing": {
        "staff": ["Austin Wells"],
        "hourly_rate": 25.00,
        "role": "Intake Processing",
    },
}

DEFAULT_PREP_TIME_HOURS = 1.0
DEFAULT_BREAKDOWN_HOURS = 0.5


def get_labor_rate(staff_name: str) -> float:
    """Return hourly rate for a staff member based on their role."""
    for role_data in LABOR_RATES.values():
        if staff_name in role_data["staff"]:
            return role_data["hourly_rate"]
    return 0.0


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


# ============================================================
# Step 1A — Acknowledgment Email
# ============================================================

ACKNOWLEDGMENT_EMAIL_SUBJECT = "Thank You — CGCS Event Request Received"

ACKNOWLEDGMENT_EMAIL_TEMPLATE = """\
Hi {first_name},

Thank you for submitting your event request to the Center for Government & Community Services (CGCS). We've received your inquiry and a member of our team will be in touch within 3 business days with next steps.

In the meantime, if you have any questions, feel free to reply to this email.

Best regards,
CGCS Team"""


def build_acknowledgment_email(requester_name: str) -> dict:
    """Build the automatic acknowledgment email payload.

    Extracts the first name from requester_name for personalization.
    Falls back to a generic greeting when the name is empty.
    """
    name = (requester_name or "").strip()
    first_name = name.split()[0] if name else "there"
    greeting = f"Hi {first_name}," if name else "Hi there,"
    body = ACKNOWLEDGMENT_EMAIL_TEMPLATE.replace("Hi {first_name},", greeting)
    return {"subject": ACKNOWLEDGMENT_EMAIL_SUBJECT, "body": body}


# ============================================================
# Event Compliance Checklist
# ============================================================

EVENT_CHECKLIST_TEMPLATE: list[dict] = [
    {"key": "user_agreement", "label": "User Agreement Signed", "deadline_bd": 0, "required": True, "condition": None},
    {"key": "furniture_layout", "label": "Furniture Layout Confirmed", "deadline_bd": 20, "required": True, "condition": None},
    {"key": "catering_plan", "label": "Catering Plan Submitted", "deadline_bd": 25, "required": True, "condition": None},
    {"key": "run_of_show", "label": "Run of Show Provided", "deadline_bd": 20, "required": True, "condition": None},
    {"key": "walkthrough", "label": "Walkthrough Scheduled", "deadline_bd": 12, "required": True, "condition": None},
    {"key": "tdx_av_request", "label": "TDX AV Request Submitted", "deadline_bd": 15, "required": True, "condition": None},
    {"key": "payment_received", "label": "Payment/Deposit Received", "deadline_bd": 10, "required": True, "condition": "a_event_only"},
    {"key": "police_security", "label": "Police/Security Reviewed", "deadline_bd": 10, "required": True, "condition": "weekend_or_evening"},
    {"key": "insurance_docs", "label": "Insurance Documentation", "deadline_bd": 10, "required": True, "condition": "external_only"},
    {"key": "parking_confirmed", "label": "Parking Arrangements Confirmed", "deadline_bd": 7, "required": True, "condition": None},
]


def calculate_business_days_before(event_date: date, business_days: int) -> date:
    """Subtract N business days from event_date, skipping weekends."""
    if business_days <= 0:
        return event_date
    current = event_date
    remaining = business_days
    while remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            remaining -= 1
    return current


def build_checklist_for_event(reservation: dict) -> list[dict]:
    """Generate checklist items for an approved reservation.

    Filters template items by conditions and calculates deadline dates.
    """
    event_name = reservation.get("event_name", "")
    pricing_tier = reservation.get("pricing_tier", "")

    # Parse event date
    raw_date = reservation.get("requested_date")
    if isinstance(raw_date, date):
        event_date = raw_date
    elif isinstance(raw_date, str):
        event_date = date.fromisoformat(raw_date)
    else:
        return []

    # Parse end time for evening check
    end_time_str = str(reservation.get("requested_end_time", ""))
    is_evening = end_time_str > "17:00" if end_time_str else False
    is_weekend = event_date.weekday() >= 5

    items: list[dict] = []
    for template in EVENT_CHECKLIST_TEMPLATE:
        condition = template["condition"]

        if condition == "a_event_only" and not event_name.startswith("A-EVENT"):
            continue
        if condition == "weekend_or_evening" and not (is_weekend or is_evening):
            continue
        if condition == "external_only" and pricing_tier != "external":
            continue

        deadline = calculate_business_days_before(event_date, template["deadline_bd"])
        items.append({
            "item_key": template["key"],
            "item_label": template["label"],
            "required": template["required"],
            "deadline_date": deadline,
        })

    return items
