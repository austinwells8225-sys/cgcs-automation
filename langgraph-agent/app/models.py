from datetime import date, time
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class EvaluateRequest(BaseModel):
    request_id: str
    requester_name: str
    requester_email: EmailStr
    requester_organization: Optional[str] = None
    event_name: str
    event_description: Optional[str] = None
    requested_date: date
    requested_start_time: time
    requested_end_time: time
    room_requested: Optional[str] = None
    estimated_attendees: Optional[int] = None
    setup_requirements_raw: Optional[str] = None
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
    action: str  # 'approve' or 'reject'
    admin_notes: Optional[str] = None
    edited_response: Optional[str] = None


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
