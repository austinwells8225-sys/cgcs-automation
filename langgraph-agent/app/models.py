from datetime import date, time
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


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
