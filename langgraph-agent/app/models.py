from datetime import date, time
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ============================================================
# Event Intake (existing)
# ============================================================

class EvaluateRequest(BaseModel):
    request_id: str = Field(max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    requester_name: str = Field(max_length=255)
    requester_email: EmailStr
    requester_organization: Optional[str] = Field(None, max_length=255)
    event_name: str = Field(max_length=500)
    event_description: Optional[str] = Field(None, max_length=5000)
    requested_date: date
    requested_start_time: time
    requested_end_time: time
    room_requested: Optional[str] = Field(None, max_length=50)
    estimated_attendees: Optional[int] = Field(None, ge=1, le=500)
    setup_requirements_raw: Optional[str] = Field(None, max_length=5000)
    calendar_available: bool


class EvaluateResponse(BaseModel):
    request_id: str
    decision: str  # 'approve', 'reject', 'needs_review'
    is_eligible: Optional[bool] = None
    eligibility_reason: Optional[str] = None
    pricing_tier: Optional[str] = None
    estimated_cost: Optional[float] = None
    room_assignment: Optional[str] = None
    setup_config: Optional[dict] = None
    draft_response: Optional[str] = None
    errors: list[str] = []


class ApproveRequest(BaseModel):
    action: str = Field(pattern=r"^(approve|reject)$")
    admin_notes: Optional[str] = Field(None, max_length=2000)
    edited_response: Optional[str] = Field(None, max_length=10000)


class ReservationDetail(BaseModel):
    id: UUID
    request_id: str
    requester_name: str
    requester_email: str
    requester_organization: Optional[str]
    event_name: str
    event_description: Optional[str]
    requested_date: date
    requested_start_time: time
    requested_end_time: time
    room_requested: Optional[str]
    estimated_attendees: Optional[int]
    setup_requirements: Optional[dict]
    pricing_tier: Optional[str]
    estimated_cost: Optional[Decimal]
    is_eligible: Optional[bool]
    eligibility_reason: Optional[str]
    calendar_available: Optional[bool]
    ai_decision: Optional[str]
    ai_draft_response: Optional[str]
    status: str
    admin_notes: Optional[str]

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
    environment: str


# ============================================================
# Email Triage
# ============================================================

class EmailTriageRequest(BaseModel):
    request_id: Optional[str] = Field(None, max_length=64)
    email_id: Optional[str] = Field(None, max_length=255)
    email_from: str = Field(max_length=255)
    email_subject: Optional[str] = Field(None, max_length=1000)
    email_body: str = Field(max_length=50000)


class EmailTriageResponse(BaseModel):
    request_id: str
    email_priority: Optional[str] = None
    email_category: Optional[str] = None
    email_draft_reply: Optional[str] = None
    email_auto_send: bool = False
    decision: str = "needs_review"
    errors: list[str] = []


class EmailApproveRequest(BaseModel):
    action: str = Field(pattern=r"^(approve|reject)$")
    edited_reply: Optional[str] = Field(None, max_length=50000)


# ============================================================
# Calendar
# ============================================================

class CalendarCheckRequest(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")


class CalendarCheckResponse(BaseModel):
    request_id: str
    is_available: Optional[bool] = None
    events: list[dict] = []
    errors: list[str] = []


class CalendarHoldRequest(BaseModel):
    org_name: str = Field(max_length=255)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")


class CalendarHoldResponse(BaseModel):
    request_id: str
    hold_event_id: Optional[str] = None
    decision: str = "needs_review"
    draft_response: Optional[str] = None
    errors: list[str] = []


# ============================================================
# P.E.T. Tracker
# ============================================================

class PetQueryRequest(BaseModel):
    query: str = Field(default="", max_length=500)


class PetQueryResponse(BaseModel):
    request_id: str
    result: Optional[dict] = None
    errors: list[str] = []


class PetUpdateRequest(BaseModel):
    row_data: dict


class PetUpdateResponse(BaseModel):
    request_id: str
    staged_id: Optional[str] = None
    requires_approval: bool = True
    errors: list[str] = []


# ============================================================
# Event Leads
# ============================================================

class EventLeadRequest(BaseModel):
    staff_name: str = Field(max_length=255)
    staff_email: EmailStr
    reservation_id: str = Field(max_length=64)
    event_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class EventLeadResponse(BaseModel):
    request_id: str
    staff_name: Optional[str] = None
    staff_email: Optional[str] = None
    reservation_id: Optional[str] = None
    reminders_scheduled: int = 0
    decision: str = "needs_review"
    draft_response: Optional[str] = None
    errors: list[str] = []


# ============================================================
# Generic task response
# ============================================================

class GenericTaskResponse(BaseModel):
    request_id: str
    decision: str = "needs_review"
    draft_response: Optional[str] = None
    errors: list[str] = []
