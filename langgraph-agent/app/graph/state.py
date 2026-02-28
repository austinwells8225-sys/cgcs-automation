from typing import Optional, TypedDict


class ReservationState(TypedDict, total=False):
    # --- Input from N8N ---
    request_id: str
    requester_name: str
    requester_email: str
    requester_organization: Optional[str]
    event_name: str
    event_description: Optional[str]
    requested_date: str  # ISO format YYYY-MM-DD
    requested_start_time: str  # HH:MM
    requested_end_time: str  # HH:MM
    room_requested: Optional[str]
    estimated_attendees: Optional[int]
    setup_requirements_raw: Optional[str]
    calendar_available: bool

    # --- Agent-computed fields ---
    is_eligible: Optional[bool]
    eligibility_reason: Optional[str]
    pricing_tier: Optional[str]
    estimated_cost: Optional[float]
    room_assignment: Optional[str]
    setup_config: Optional[dict]
    draft_response: Optional[str]
    decision: Optional[str]  # 'approve', 'reject', 'needs_review'
    errors: list[str]
