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
    rejection_reason: Optional[str] = Field(None, max_length=2000)


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
# Acknowledgment Email
# ============================================================

class AcknowledgeRequest(BaseModel):
    requester_name: str = Field(max_length=255)
    requester_email: EmailStr


class AcknowledgeResponse(BaseModel):
    to: str
    subject: str
    body: str
    auto_send: bool = True


# ============================================================
# Generic task response
# ============================================================

class GenericTaskResponse(BaseModel):
    request_id: str
    decision: str = "needs_review"
    draft_response: Optional[str] = None
    errors: list[str] = []


# ============================================================
# Revenue & Reporting
# ============================================================

class CompleteReservationRequest(BaseModel):
    actual_revenue: Optional[Decimal] = Field(None, ge=0)
    actual_attendance: Optional[int] = Field(None, ge=0)
    event_department: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=2000)


class CompleteReservationResponse(BaseModel):
    request_id: str
    status: str
    actual_revenue: Optional[float] = None
    actual_attendance: Optional[int] = None
    event_department: Optional[str] = None
    completed_at: Optional[str] = None


class RevenueReportResponse(BaseModel):
    period: str
    start: str
    end: str
    total_events: int = 0
    total_revenue: float = 0.0
    avg_revenue: float = 0.0
    total_attendance: int = 0
    avg_attendance: float = 0.0
    breakdown_by_type: list[dict] = []


class ConversionFunnelResponse(BaseModel):
    period: str
    start: str
    end: str
    total_submitted: int = 0
    pending: int = 0
    approved: int = 0
    completed: int = 0
    rejected: int = 0
    cancelled: int = 0
    approval_rate: float = 0.0
    completion_rate: float = 0.0


class TopOrganizationEntry(BaseModel):
    organization: str
    total_bookings: int = 0
    completed_bookings: int = 0
    total_revenue: float = 0.0
    total_attendance: int = 0


class TopOrganizationsResponse(BaseModel):
    period: str
    start: str
    end: str
    limit: int
    organizations: list[TopOrganizationEntry] = []


# ============================================================
# Event Compliance Checklist
# ============================================================

class ChecklistItemResponse(BaseModel):
    id: Optional[str] = None
    item_key: str
    item_label: str
    required: bool = True
    status: str = "pending"
    deadline_date: Optional[str] = None
    days_until_deadline: Optional[int] = None
    is_overdue: bool = False
    completed_at: Optional[str] = None
    completed_by: Optional[str] = None
    notes: Optional[str] = None


class ChecklistResponse(BaseModel):
    request_id: str
    items: list[ChecklistItemResponse] = []
    total: int = 0
    completed: int = 0
    pending: int = 0
    overdue: int = 0


class ChecklistItemUpdateRequest(BaseModel):
    status: str = Field(pattern=r"^(pending|in_review|completed|waived)$")
    notes: Optional[str] = Field(None, max_length=2000)


class BulkChecklistUpdateItem(BaseModel):
    item_key: str = Field(max_length=50)
    status: str = Field(pattern=r"^(pending|in_review|completed|waived)$")
    notes: Optional[str] = Field(None, max_length=2000)


class BulkChecklistUpdateRequest(BaseModel):
    items: list[BulkChecklistUpdateItem] = Field(min_length=1)


class BulkChecklistUpdateResponse(BaseModel):
    request_id: str
    updated_count: int = 0


class OverdueItemSummary(BaseModel):
    item_key: str
    item_label: str
    overdue_count: int = 0
    avg_days_overdue: float = 0.0


class ComplianceReportResponse(BaseModel):
    period: str
    start: str
    end: str
    total_items: int = 0
    completed_items: int = 0
    on_time_rate: float = 0.0
    events_all_complete: int = 0
    most_overdue_items: list[OverdueItemSummary] = []


# ============================================================
# Email Rejection / Self-Improving Drafts
# ============================================================

class EmailRejectAndReworkRequest(BaseModel):
    rejection_reason: str = Field(max_length=2000)
    email_from: Optional[str] = Field(None, max_length=255)
    email_subject: Optional[str] = Field(None, max_length=1000)
    original_draft: Optional[str] = Field(None, max_length=50000)
    category: Optional[str] = Field(None, max_length=50)


class RevisionOption(BaseModel):
    label: str
    draft: str


class EmailRejectAndReworkResponse(BaseModel):
    email_id: str
    pattern_id: int
    revisions: list[RevisionOption] = []


class SelectRevisionRequest(BaseModel):
    revision_index: Optional[int] = Field(None, ge=0, le=2)
    final_draft: Optional[str] = Field(None, max_length=50000)


class SelectRevisionResponse(BaseModel):
    pattern_id: int
    status: str
    final_draft: str


class RejectionInsightsResponse(BaseModel):
    total_rejections: int = 0
    improvement_rate: float = 0.0
    top_reasons: list[dict] = []
    category_breakdown: list[dict] = []


# ============================================================
# Dynamic Quote Versioning
# ============================================================

class QuoteLineItem(BaseModel):
    service: str
    description: str
    quantity: float = 1
    unit_price: float = 0.0
    total: float = 0.0


class QuoteVersionResponse(BaseModel):
    id: Optional[str] = None
    reservation_id: Optional[str] = None
    version: int = 1
    line_items: list[QuoteLineItem] = []
    subtotal: float = 0.0
    deposit_amount: float = 0.0
    total: float = 0.0
    changes_from_previous: Optional[dict] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None


class QuoteHistoryResponse(BaseModel):
    reservation_id: str
    versions: list[QuoteVersionResponse] = []
    current_version: int = 0


class QuoteGenerateResponse(BaseModel):
    reservation_id: str
    quote: QuoteVersionResponse
    email_snippet: str = ""


class AddServiceItem(BaseModel):
    service: str = Field(max_length=50)
    hours: Optional[int] = Field(None, ge=1, le=24)
    count: Optional[int] = Field(None, ge=1, le=100)


class QuoteUpdateRequest(BaseModel):
    add_services: list[AddServiceItem] = []
    remove_services: list[str] = []
    notes: Optional[str] = Field(None, max_length=2000)


class QuoteUpdateResponse(BaseModel):
    reservation_id: str
    quote: QuoteVersionResponse
    email_snippet: str = ""
    changes: Optional[dict] = None


# ============================================================
# Process Insights & Reporting
# ============================================================

class EmailMetrics(BaseModel):
    total_drafts: int = 0
    rejection_rate: float = 0.0
    avg_revisions_per_email: float = 0.0
    top_rejection_reasons: list[dict] = []
    improvement_trend: dict = {}


class QuoteMetrics(BaseModel):
    total_quotes: int = 0
    avg_revisions_per_quote: float = 0.0
    most_added_service: Optional[str] = None
    avg_quote_increase_pct: float = 0.0


class TurnaroundMetrics(BaseModel):
    avg_intake_to_response_hours: float = 0.0
    avg_intake_to_approval_days: float = 0.0
    avg_intake_to_event_days: float = 0.0


class ComplianceMetrics(BaseModel):
    on_time_rate: float = 0.0
    most_overdue_items: list[dict] = []
    avg_overdue_days_per_item: list[dict] = []
    items_never_completed: int = 0


class ProcessInsightsResponse(BaseModel):
    period: str = "quarter"
    start: str = ""
    end: str = ""
    email: EmailMetrics = EmailMetrics()
    quotes: QuoteMetrics = QuoteMetrics()
    turnaround: TurnaroundMetrics = TurnaroundMetrics()
    compliance: ComplianceMetrics = ComplianceMetrics()
    conversion: dict = {}
    revenue: dict = {}
    top_organizations: list[dict] = []
    recommendations: list[str] = []


class QuarterlyReportRequest(BaseModel):
    quarter_start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    send_email: bool = False


class QuarterlyReportResponse(BaseModel):
    report: ProcessInsightsResponse
    generated_at: str = ""
    email_sent: bool = False


class MonthlyQuickStats(BaseModel):
    events_this_month: int = 0
    revenue_this_month: float = 0.0
    pending_approvals: int = 0
    on_time_checklist_rate: float = 0.0
