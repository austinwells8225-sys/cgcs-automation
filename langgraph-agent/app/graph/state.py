from typing import Optional, TypedDict


class AgentState(TypedDict, total=False):
    # --- Common fields ---
    task_type: str  # event_intake | email_triage | calendar_check | calendar_hold | pet_tracker | event_lead | reminder_check | daily_digest
    request_id: str
    errors: list[str]
    decision: Optional[str]  # 'approve', 'reject', 'needs_review'
    draft_response: Optional[str]
    requires_approval: Optional[bool]
    approved: Optional[bool]

    # --- Event intake fields (existing) ---
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
    is_eligible: Optional[bool]
    eligibility_reason: Optional[str]
    pricing_tier: Optional[str]
    estimated_cost: Optional[float]
    room_assignment: Optional[str]
    setup_config: Optional[dict]

    # --- Email triage fields ---
    email_id: Optional[str]
    email_from: Optional[str]
    email_subject: Optional[str]
    email_body: Optional[str]
    email_priority: Optional[str]  # 'high', 'medium', 'low'
    email_category: Optional[str]  # 'event_request', 'question', 'complaint', 'follow_up', 'spam', 'other'
    email_draft_reply: Optional[str]
    email_auto_send: Optional[bool]
    email_rejection_lessons: Optional[str]

    # --- Calendar check fields ---
    calendar_query_date: Optional[str]
    calendar_query_start: Optional[str]
    calendar_query_end: Optional[str]
    calendar_is_available: Optional[bool]
    calendar_events: Optional[list[dict]]

    # --- Calendar hold fields ---
    hold_org_name: Optional[str]
    hold_date: Optional[str]
    hold_start_time: Optional[str]
    hold_end_time: Optional[str]
    hold_event_id: Optional[str]
    hold_event_type: Optional[str]  # HOLD, S-EVENT, C-EVENT, A-EVENT

    # --- P.E.T. tracker fields ---
    pet_operation: Optional[str]  # 'read' or 'update'
    pet_row_data: Optional[dict]
    pet_query: Optional[str]
    pet_result: Optional[dict]

    # --- Event lead fields ---
    lead_staff_name: Optional[str]
    lead_staff_email: Optional[str]
    lead_reservation_id: Optional[str]
    lead_event_date: Optional[str]
    lead_current_month_count: Optional[int]  # current month lead count for cap enforcement

    # --- Reminder fields ---
    reminders_due: Optional[list[dict]]
    reminders_sent: Optional[list[dict]]

    # --- Daily digest fields ---
    digest_pending_approvals: Optional[list[dict]]
    digest_new_intakes: Optional[list[dict]]
    digest_upcoming_events: Optional[list[dict]]
    digest_pending_agreements: Optional[list[dict]]
    digest_overdue_deadlines: Optional[list[dict]]
    digest_checklist_items_due: Optional[list[dict]]
    digest_monthly_stats: Optional[dict]

    # --- Event type ---
    event_type: Optional[str]  # S-EVENT, C-EVENT, A-EVENT

    # --- Quote fields ---
    quote_email_snippet: Optional[str]


# Backward compatibility alias
ReservationState = AgentState
