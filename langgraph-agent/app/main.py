import csv
import io
import json
import logging
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Header, HTTPException, Request, Security
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader

from app.config import settings
from app.db.connection import close_pool
from app.db.queries import (
    add_audit_entry,
    add_dead_letter,
    approve_reservation,
    create_reservation,
    get_dead_letter_entries,
    get_reservation,
    reject_reservation,
    resolve_dead_letter,
)
from app.graph.builder import build_graph
from app.services.intake_processor import _format_event_date
from app.db.checklist_queries import (
    bulk_update_checklist_items,
    get_checklist,
    get_compliance_report,
    insert_checklist_items,
    update_checklist_item,
)
from app.db.quote_queries import (
    create_quote_version,
    get_latest_quote,
    get_quote_history,
)
from app.db.rejection_queries import (
    create_rejection_pattern,
    get_rejection_insights,
    get_rejection_patterns,
    select_revision,
)
from app.db.report_queries import (
    complete_reservation,
    get_conversion_funnel,
    get_reservations_for_export,
    get_revenue_report,
    get_top_organizations,
)
from app.graph.nodes.shared import _invoke_with_retry, _parse_json_response
from app.prompt_tuning import get_rejection_lessons
from app.prompts.templates import REJECTION_REWORK_SYSTEM_PROMPT
from app.services.process_insights import (
    build_quarterly_report,
    get_monthly_quick_stats,
)
from app.services.quote_builder import build_initial_quote, format_quote_for_email, update_quote
from app.db.alert_queries import (
    create_alert,
    dismiss_alert,
    get_active_alerts,
)
from app.services.smartsheet_parser import is_smartsheet_intake, parse_smartsheet_intake
from app.services.date_utils import business_days_until, is_within_minimum_lead_time
from app.services.intake_classifier import classify_request
from app.services.error_handler import classify_error, build_error_alert
from app.cgcs_constants import (
    build_acknowledgment_email,
    build_checklist_for_event,
    build_intake_acknowledgment_email,
    MINIMUM_LEAD_TIME_BD,
    CGCS_SYSTEM_EMAIL,
)
from app.models import (
    AcknowledgeRequest,
    AcknowledgeResponse,
    ApproveRequest,
    CalendarCheckRequest,
    CalendarCheckResponse,
    CalendarHoldRequest,
    CalendarHoldResponse,
    EmailApproveRequest,
    EmailTriageRequest,
    EmailTriageResponse,
    EvaluateRequest,
    EvaluateResponse,
    EventLeadRequest,
    EventLeadResponse,
    GenericTaskResponse,
    HealthResponse,
    PetQueryRequest,
    PetQueryResponse,
    PetUpdateRequest,
    PetUpdateResponse,
    CompleteReservationRequest,
    CompleteReservationResponse,
    ConversionFunnelResponse,
    RevenueReportResponse,
    TopOrganizationsResponse,
    BulkChecklistUpdateRequest,
    BulkChecklistUpdateResponse,
    ChecklistItemResponse,
    ChecklistItemUpdateRequest,
    ChecklistResponse,
    ComplianceReportResponse,
    EmailRejectAndReworkRequest,
    EmailRejectAndReworkResponse,
    RejectionInsightsResponse,
    RevisionOption,
    SelectRevisionRequest,
    SelectRevisionResponse,
    AddServiceItem,
    QuoteGenerateResponse,
    QuoteHistoryResponse,
    QuoteLineItem,
    QuoteUpdateRequest,
    QuoteUpdateResponse,
    QuoteVersionResponse,
    ProcessInsightsResponse,
    QuarterlyReportRequest,
    QuarterlyReportResponse,
    DashboardAlertResponse,
    DashboardAlertsListResponse,
    SmartsheetWebhookRequest,
    EmailReplyWebhookRequest,
    AdminResponseWebhookRequest,
    PoliceConfirmedWebhookRequest,
)

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

graph = build_graph()
compiled_graph = graph.compile()

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Verify Bearer token for authenticated internal endpoints."""
    if not settings.langgraph_api_key:
        return "anonymous"
    expected = f"Bearer {settings.langgraph_api_key}"
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return "authenticated"


async def verify_webhook_secret(x_webhook_secret: str = Header(None)) -> str:
    """Verify shared secret header for the public webhook endpoint."""
    if not settings.webhook_secret:
        return "no-secret-configured"
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    return "verified"


def _run_config(task_type: str, request_id: str) -> dict:
    """Build LangGraph invocation config with LangSmith run_name."""
    return {"run_name": f"{task_type}:{request_id}"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CGCS LangGraph Agent starting up")
    yield
    logger.info("Shutting down, closing DB pool")
    await close_pool()


app = FastAPI(
    title="CGCS Unified Agent",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None,
)


# ============================================================
# Health (unauthenticated)
# ============================================================

@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", environment=settings.environment)


# ============================================================
# Step 1A — Acknowledgment Email (webhook secret auth, no approval gate)
# ============================================================

@app.post("/api/v1/acknowledge", response_model=AcknowledgeResponse)
async def acknowledge(
    request: AcknowledgeRequest,
    _auth: str = Security(verify_webhook_secret),
):
    """Send automatic acknowledgment email — continueOnFail, never blocks pipeline."""
    try:
        email = build_acknowledgment_email(request.requester_name)
    except Exception:
        logger.exception("Acknowledgment email build failed, using fallback")
        email = build_acknowledgment_email("")

    return AcknowledgeResponse(
        to=request.requester_email,
        subject=email["subject"],
        body=email["body"],
        auto_send=True,
    )


# ============================================================
# Event Intake (webhook secret auth) — existing
# ============================================================

@app.post("/api/v1/evaluate", response_model=EvaluateResponse)
async def evaluate(
    request: EvaluateRequest,
    _auth: str = Security(verify_webhook_secret),
):
    """Evaluate an event space reservation request.

    Authenticated via X-Webhook-Secret header (shared secret with N8N).
    Processes the request through the LangGraph agent, saves as pending_review.
    NO email is sent to the requester — admin must approve first.
    """
    logger.info("Evaluating request: %s", request.request_id)

    initial_state = {
        "task_type": "event_intake",
        "request_id": request.request_id,
        "requester_name": request.requester_name,
        "requester_email": request.requester_email,
        "requester_organization": request.requester_organization,
        "event_name": request.event_name,
        "event_description": request.event_description,
        "requested_date": request.requested_date.isoformat(),
        "requested_start_time": request.requested_start_time.strftime("%H:%M"),
        "requested_end_time": request.requested_end_time.strftime("%H:%M"),
        "room_requested": request.room_requested,
        "estimated_attendees": request.estimated_attendees,
        "setup_requirements_raw": request.setup_requirements_raw,
        "calendar_available": request.calendar_available,
        "errors": [],
    }

    # Run the graph — catch all failures to send to dead letter queue
    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("event_intake", request.request_id),
        )
    except Exception as e:
        logger.exception("Graph execution failed for request %s", request.request_id)
        # Dead letter queue — never silently drop
        try:
            dlq_id = await add_dead_letter(
                request_id=request.request_id,
                payload=initial_state,
                error_message=f"{type(e).__name__}: {e}",
                error_type="graph_execution_failure",
            )
            logger.error("Request %s sent to dead letter queue (DLQ #%d)", request.request_id, dlq_id)
        except Exception:
            logger.exception("CRITICAL: Failed to write to dead letter queue")

        return EvaluateResponse(
            request_id=request.request_id,
            decision="needs_review",
            draft_response=f"Processing failed. Queued for manual review. Error: {type(e).__name__}",
            errors=[f"Graph execution failed: {e}"],
        )

    # Save to database
    try:
        reservation_data = {
            **initial_state,
            "decision": result.get("decision"),
            "is_eligible": result.get("is_eligible"),
            "eligibility_reason": result.get("eligibility_reason"),
            "pricing_tier": result.get("pricing_tier"),
            "estimated_cost": result.get("estimated_cost"),
            "room_assignment": result.get("room_assignment"),
            "setup_config": json.dumps(result.get("setup_config")) if result.get("setup_config") else None,
            "draft_response": result.get("draft_response"),
        }
        reservation_id = await create_reservation(reservation_data)
        await add_audit_entry(
            reservation_id=reservation_id,
            action="agent_evaluated",
            actor="langgraph_agent",
            details={
                "decision": result.get("decision"),
                "pricing_tier": result.get("pricing_tier"),
                "estimated_cost": result.get("estimated_cost"),
                "errors": result.get("errors", []),
            },
        )
        logger.info("Reservation %s saved with status pending_review", request.request_id)

        # Auto-generate initial quote on approve (continueOnFail)
        if result.get("decision") == "approve" and result.get("pricing_tier"):
            try:
                quote_data = build_initial_quote({**reservation_data, **result})
                await create_quote_version(reservation_id, quote_data)
                logger.info("Auto-generated quote v1 for %s", request.request_id)
            except Exception:
                logger.exception("Auto-quote generation failed for %s (continueOnFail)", request.request_id)

    except Exception as e:
        logger.exception("Failed to save reservation to database")
        # Dead letter the result so it's not lost
        try:
            await add_dead_letter(
                request_id=request.request_id,
                payload={**initial_state, "graph_result": {
                    "decision": result.get("decision"),
                    "draft_response": result.get("draft_response"),
                }},
                error_message=f"DB save failed: {e}",
                error_type="db_save_failure",
            )
        except Exception:
            logger.exception("CRITICAL: Failed to write to dead letter queue")

    return EvaluateResponse(
        request_id=request.request_id,
        decision=result.get("decision", "needs_review"),
        is_eligible=result.get("is_eligible"),
        eligibility_reason=result.get("eligibility_reason"),
        pricing_tier=result.get("pricing_tier"),
        estimated_cost=result.get("estimated_cost"),
        room_assignment=result.get("room_assignment"),
        setup_config=result.get("setup_config"),
        draft_response=result.get("draft_response"),
        errors=result.get("errors", []),
    )


# ============================================================
# Admin endpoints (API key auth) — existing
# ============================================================

@app.post("/api/v1/approve/{request_id}")
async def approve(
    request_id: str,
    body: ApproveRequest,
    _auth: str = Security(verify_api_key),
):
    """Admin approval/rejection endpoint.

    Called by N8N Workflow 2 when admin explicitly approves or rejects.
    Only after this call should N8N send the email to the requester.
    """
    reservation = await get_reservation(request_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation["status"] != "pending_review":
        raise HTTPException(
            status_code=400,
            detail=f"Reservation is already {reservation['status']}, cannot modify",
        )

    if body.action == "approve":
        updated = await approve_reservation(
            request_id=request_id,
            admin_notes=body.admin_notes,
            edited_response=body.edited_response,
        )
    elif body.action == "reject":
        updated = await reject_reservation(
            request_id=request_id,
            admin_notes=body.admin_notes,
        )
    else:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

    if not updated:
        raise HTTPException(status_code=409, detail="Failed to update reservation")

    await add_audit_entry(
        reservation_id=updated["id"],
        action=f"admin_{body.action}d",
        actor="admin",
        details={
            "admin_notes": body.admin_notes,
            "edited_response": body.edited_response is not None,
        },
    )

    logger.info("Reservation %s %sd by admin", request_id, body.action)

    # Generate compliance checklist on approval (continueOnFail)
    if body.action == "approve":
        try:
            checklist_items = build_checklist_for_event(updated)
            if checklist_items:
                await insert_checklist_items(updated["id"], checklist_items)
                await add_audit_entry(
                    reservation_id=updated["id"],
                    action="checklist_generated",
                    actor="system",
                    details={"item_count": len(checklist_items)},
                )
                logger.info("Generated %d checklist items for %s", len(checklist_items), request_id)
        except Exception:
            logger.exception("Checklist generation failed for %s (continueOnFail)", request_id)

    return {
        "request_id": request_id,
        "status": updated["status"],
        "draft_response": updated["ai_draft_response"],
        "requester_email": updated["requester_email"],
        "requester_name": updated["requester_name"],
        "event_name": updated["event_name"],
    }


@app.get("/api/v1/reservation/{request_id}")
async def get_reservation_detail(
    request_id: str,
    _auth: str = Security(verify_api_key),
):
    """Admin lookup endpoint for a reservation."""
    reservation = await get_reservation(request_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return reservation


# ============================================================
# Dead letter queue admin endpoints — existing
# ============================================================

@app.get("/api/v1/dead-letter")
async def list_dead_letters(
    status: str = "pending",
    _auth: str = Security(verify_api_key),
):
    """List dead letter queue entries for admin review."""
    entries = await get_dead_letter_entries(status)
    return {"count": len(entries), "entries": entries}


@app.post("/api/v1/dead-letter/{dlq_id}/resolve")
async def resolve_dead_letter_entry(
    dlq_id: int,
    _auth: str = Security(verify_api_key),
):
    """Mark a dead letter entry as resolved after manual review."""
    resolved = await resolve_dead_letter(dlq_id, resolved_by="admin")
    if not resolved:
        raise HTTPException(status_code=404, detail="DLQ entry not found or already resolved")
    return {"id": dlq_id, "status": "resolved"}


# ============================================================
# Email Triage endpoints — NEW
# ============================================================

@app.post("/api/v1/email/triage", response_model=EmailTriageResponse)
async def triage_email(
    request: EmailTriageRequest,
    _auth: str = Security(verify_webhook_secret),
):
    """Triage an incoming email: classify, draft reply, check auto-send."""
    request_id = request.request_id or f"email-{uuid.uuid4().hex[:12]}"
    logger.info("Triaging email: %s from %s", request_id, request.email_from)

    # Fetch rejection lessons to inject into email drafting (continueOnFail)
    lessons = ""
    try:
        lessons = await get_rejection_lessons()
    except Exception:
        logger.debug("Failed to fetch rejection lessons (continueOnFail)")

    initial_state = {
        "task_type": "email_triage",
        "request_id": request_id,
        "email_id": request.email_id,
        "email_from": request.email_from,
        "email_subject": request.email_subject,
        "email_body": request.email_body,
        "email_rejection_lessons": lessons,
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("email_triage", request_id),
        )
    except Exception as e:
        logger.exception("Email triage failed for %s", request_id)
        try:
            await add_dead_letter(
                request_id=request_id,
                payload=initial_state,
                error_message=f"{type(e).__name__}: {e}",
                error_type="email_triage_failure",
            )
        except Exception:
            logger.exception("CRITICAL: Failed to write to dead letter queue")

        return EmailTriageResponse(
            request_id=request_id,
            decision="needs_review",
            errors=[f"Email triage failed: {e}"],
        )

    return EmailTriageResponse(
        request_id=request_id,
        email_priority=result.get("email_priority"),
        email_category=result.get("email_category"),
        email_draft_reply=result.get("email_draft_reply"),
        email_auto_send=result.get("email_auto_send", False),
        decision=result.get("decision", "needs_review"),
        errors=result.get("errors", []),
    )


@app.post("/api/v1/email/approve/{email_id}")
async def approve_email(
    email_id: str,
    body: EmailApproveRequest,
    _auth: str = Security(verify_api_key),
):
    """Admin approves or rejects an email draft reply.

    When rejecting with a rejection_reason, automatically triggers the
    rework flow: generates 3 improved versions and stores the pattern.
    """
    logger.info("Email %s %sd by admin", email_id, body.action)

    if body.action == "reject" and body.rejection_reason:
        # Trigger rework flow inline
        try:
            prompt = REJECTION_REWORK_SYSTEM_PROMPT.format(
                email_from="unknown",
                email_subject="unknown",
                category="unknown",
                original_draft=body.edited_reply or "No original draft available",
                rejection_reason=body.rejection_reason,
            )
            content = _invoke_with_retry([
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Generate 3 revised versions."},
            ])
            parsed = _parse_json_response(content)
            revisions = parsed.get("revisions", [])

            pattern_id = await create_rejection_pattern(
                email_task_id=None,
                original_draft=body.edited_reply or "",
                rejection_reason=body.rejection_reason,
                revision_options=revisions,
                category=None,
            )

            return {
                "email_id": email_id,
                "action": "rejected",
                "status": "rework_generated",
                "pattern_id": pattern_id,
                "revisions": revisions,
            }
        except Exception:
            logger.exception("Rework generation failed for email %s (returning simple reject)", email_id)

    return {
        "email_id": email_id,
        "action": body.action,
        "status": "approved" if body.action == "approve" else "rejected",
    }


@app.get("/api/v1/email/pending")
async def list_pending_emails(
    _auth: str = Security(verify_api_key),
):
    """List pending email drafts awaiting admin approval."""
    # In production, queries cgcs.email_tasks WHERE status = 'pending_review'
    return {"count": 0, "entries": []}


# ============================================================
# Email Rejection / Self-Improving Drafts — NEW
# ============================================================

@app.post("/api/v1/email/reject-and-rework/{email_id}", response_model=EmailRejectAndReworkResponse)
async def reject_and_rework(
    email_id: str,
    body: EmailRejectAndReworkRequest,
    _auth: str = Security(verify_api_key),
):
    """Reject an email draft and generate 3 improved revisions."""
    logger.info("Reject-and-rework for email %s: %s", email_id, body.rejection_reason[:80])

    prompt = REJECTION_REWORK_SYSTEM_PROMPT.format(
        email_from=body.email_from or "unknown",
        email_subject=body.email_subject or "unknown",
        category=body.category or "unknown",
        original_draft=body.original_draft or "No original draft provided",
        rejection_reason=body.rejection_reason,
    )

    try:
        content = _invoke_with_retry([
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Generate 3 revised versions."},
        ])
        parsed = _parse_json_response(content)
        revisions = parsed.get("revisions", [])
    except Exception as e:
        logger.exception("Rework LLM call failed for email %s", email_id)
        raise HTTPException(status_code=502, detail=f"Revision generation failed: {e}")

    pattern_id = await create_rejection_pattern(
        email_task_id=None,
        original_draft=body.original_draft or "",
        rejection_reason=body.rejection_reason,
        revision_options=revisions,
        category=body.category,
    )

    return EmailRejectAndReworkResponse(
        email_id=email_id,
        pattern_id=pattern_id,
        revisions=[RevisionOption(**r) for r in revisions],
    )


@app.post("/api/v1/email/select-revision/{pattern_id}", response_model=SelectRevisionResponse)
async def select_revision_endpoint(
    pattern_id: int,
    body: SelectRevisionRequest,
    _auth: str = Security(verify_api_key),
):
    """Admin selects one of the 3 revisions or provides a custom final draft."""
    if body.revision_index is None and not body.final_draft:
        raise HTTPException(
            status_code=422,
            detail="Must provide either revision_index (0-2) or final_draft",
        )

    # If selecting a revision by index, retrieve the draft from stored options
    final_draft = body.final_draft
    if body.revision_index is not None and not final_draft:
        patterns = await get_rejection_patterns(limit=1)
        # Look up this specific pattern
        for p in patterns:
            if p["id"] == pattern_id:
                options = p.get("revision_options", [])
                if body.revision_index < len(options):
                    final_draft = options[body.revision_index].get("draft", "")
                break
        if not final_draft:
            # Fallback: query by pattern_id directly
            all_patterns = await get_rejection_patterns(limit=100)
            for p in all_patterns:
                if p["id"] == pattern_id:
                    options = p.get("revision_options", [])
                    if body.revision_index < len(options):
                        final_draft = options[body.revision_index].get("draft", "")
                    break

    if not final_draft:
        raise HTTPException(status_code=404, detail="Pattern or revision not found")

    updated = await select_revision(
        pattern_id=pattern_id,
        revision_index=body.revision_index,
        final_draft=final_draft,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Rejection pattern not found")

    return SelectRevisionResponse(
        pattern_id=pattern_id,
        status="revision_selected",
        final_draft=final_draft,
    )


@app.get("/api/v1/email/rejection-insights", response_model=RejectionInsightsResponse)
async def rejection_insights(
    category: str = "",
    _auth: str = Security(verify_api_key),
):
    """Aggregated rejection analytics: top reasons, improvement rate, category breakdown."""
    result = await get_rejection_insights(category=category or None)
    return RejectionInsightsResponse(**result)


# ============================================================
# Calendar endpoints — NEW
# ============================================================

@app.post("/api/v1/calendar/check", response_model=CalendarCheckResponse)
async def calendar_check(
    request: CalendarCheckRequest,
    _auth: str = Security(verify_webhook_secret),
):
    """Check calendar availability for a given time slot."""
    request_id = f"cal-{uuid.uuid4().hex[:12]}"
    logger.info("Calendar check: %s %s-%s", request.date, request.start_time, request.end_time)

    initial_state = {
        "task_type": "calendar_check",
        "request_id": request_id,
        "calendar_query_date": request.date,
        "calendar_query_start": request.start_time,
        "calendar_query_end": request.end_time,
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("calendar_check", request_id),
        )
    except Exception as e:
        logger.exception("Calendar check failed")
        return CalendarCheckResponse(
            request_id=request_id,
            is_available=None,
            events=[],
            errors=[f"Calendar check failed: {e}"],
        )

    return CalendarCheckResponse(
        request_id=request_id,
        is_available=result.get("calendar_is_available"),
        events=result.get("calendar_events", []),
        errors=result.get("errors", []),
    )


@app.post("/api/v1/calendar/hold", response_model=CalendarHoldResponse)
async def calendar_hold(
    request: CalendarHoldRequest,
    _auth: str = Security(verify_api_key),
):
    """Create a calendar hold for a time slot."""
    request_id = f"hold-{uuid.uuid4().hex[:12]}"
    logger.info("Calendar hold: %s %s %s-%s", request.org_name, request.date, request.start_time, request.end_time)

    initial_state = {
        "task_type": "calendar_hold",
        "request_id": request_id,
        "hold_org_name": request.org_name,
        "hold_date": request.date,
        "hold_start_time": request.start_time,
        "hold_end_time": request.end_time,
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("calendar_hold", request_id),
        )
    except Exception as e:
        logger.exception("Calendar hold failed")
        return CalendarHoldResponse(
            request_id=request_id,
            decision="needs_review",
            errors=[f"Calendar hold failed: {e}"],
        )

    return CalendarHoldResponse(
        request_id=request_id,
        hold_event_id=result.get("hold_event_id"),
        decision=result.get("decision", "needs_review"),
        draft_response=result.get("draft_response"),
        errors=result.get("errors", []),
    )


# ============================================================
# P.E.T. Tracker endpoints — NEW
# ============================================================

@app.post("/api/v1/pet/query", response_model=PetQueryResponse)
async def pet_query(
    request: PetQueryRequest,
    _auth: str = Security(verify_api_key),
):
    """Read data from the P.E.T. tracker spreadsheet."""
    request_id = f"pet-{uuid.uuid4().hex[:12]}"
    logger.info("P.E.T. query: %s", request.query)

    initial_state = {
        "task_type": "pet_tracker",
        "request_id": request_id,
        "pet_operation": "read",
        "pet_query": request.query,
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("pet_tracker", request_id),
        )
    except Exception as e:
        logger.exception("P.E.T. query failed")
        return PetQueryResponse(
            request_id=request_id,
            errors=[f"P.E.T. query failed: {e}"],
        )

    return PetQueryResponse(
        request_id=request_id,
        result=result.get("pet_result"),
        errors=result.get("errors", []),
    )


@app.post("/api/v1/pet/update", response_model=PetUpdateResponse)
async def pet_update(
    request: PetUpdateRequest,
    _auth: str = Security(verify_api_key),
):
    """Stage a P.E.T. tracker update for approval."""
    request_id = f"pet-{uuid.uuid4().hex[:12]}"
    logger.info("P.E.T. update staging")

    initial_state = {
        "task_type": "pet_tracker",
        "request_id": request_id,
        "pet_operation": "update",
        "pet_row_data": request.row_data,
        "pet_query": "",
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("pet_tracker", request_id),
        )
    except Exception as e:
        logger.exception("P.E.T. update staging failed")
        return PetUpdateResponse(
            request_id=request_id,
            errors=[f"P.E.T. update staging failed: {e}"],
        )

    return PetUpdateResponse(
        request_id=request_id,
        staged_id=result.get("pet_result", {}).get("staged_id") if result.get("pet_result") else None,
        requires_approval=result.get("requires_approval", True),
        errors=result.get("errors", []),
    )


@app.post("/api/v1/pet/update/{staged_id}/approve")
async def pet_approve_update(
    staged_id: str,
    _auth: str = Security(verify_api_key),
):
    """Approve a staged P.E.T. tracker update."""
    # In production, this applies the staged update via google_sheets.apply_update
    logger.info("P.E.T. update %s approved", staged_id)
    return {"staged_id": staged_id, "status": "approved"}


# ============================================================
# Event Lead endpoints — NEW
# ============================================================

@app.post("/api/v1/leads/assign", response_model=EventLeadResponse)
async def assign_lead(
    request: EventLeadRequest,
    _auth: str = Security(verify_api_key),
):
    """Assign a staff member as event lead and schedule reminders."""
    request_id = f"lead-{uuid.uuid4().hex[:12]}"
    logger.info("Assigning lead: %s for reservation %s", request.staff_name, request.reservation_id)

    initial_state = {
        "task_type": "event_lead",
        "request_id": request_id,
        "lead_staff_name": request.staff_name,
        "lead_staff_email": request.staff_email,
        "lead_reservation_id": request.reservation_id,
        "lead_event_date": request.event_date,
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("event_lead", request_id),
        )
    except Exception as e:
        logger.exception("Event lead assignment failed")
        return EventLeadResponse(
            request_id=request_id,
            decision="needs_review",
            errors=[f"Lead assignment failed: {e}"],
        )

    return EventLeadResponse(
        request_id=request_id,
        staff_name=result.get("lead_staff_name"),
        staff_email=result.get("lead_staff_email"),
        reservation_id=result.get("lead_reservation_id"),
        reminders_scheduled=len(result.get("reminders_due", [])),
        decision=result.get("decision", "needs_review"),
        draft_response=result.get("draft_response"),
        errors=result.get("errors", []),
    )


@app.get("/api/v1/leads/{reservation_id}")
async def get_lead(
    reservation_id: str,
    _auth: str = Security(verify_api_key),
):
    """Get the assigned lead for an event."""
    # In production, queries cgcs.event_leads
    return {"reservation_id": reservation_id, "lead": None}


# ============================================================
# Reminder endpoints — NEW
# ============================================================

@app.post("/api/v1/reminders/check", response_model=GenericTaskResponse)
async def check_reminders(
    _auth: str = Security(verify_webhook_secret),
):
    """Find and process due reminders (called by cron)."""
    request_id = f"remind-{uuid.uuid4().hex[:12]}"
    logger.info("Checking due reminders")

    # In production, pre-populate reminders_due from database
    initial_state = {
        "task_type": "reminder_check",
        "request_id": request_id,
        "reminders_due": [],  # populated from DB in production
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("reminder_check", request_id),
        )
    except Exception as e:
        logger.exception("Reminder check failed")
        return GenericTaskResponse(
            request_id=request_id,
            decision="needs_review",
            errors=[f"Reminder check failed: {e}"],
        )

    return GenericTaskResponse(
        request_id=request_id,
        decision=result.get("decision", "approve"),
        draft_response=result.get("draft_response"),
        errors=result.get("errors", []),
    )


# ============================================================
# Daily Digest endpoint — NEW
# ============================================================

@app.post("/api/v1/daily-digest", response_model=GenericTaskResponse)
async def daily_digest(
    _auth: str = Security(verify_webhook_secret),
):
    """Generate and send the daily digest email to admin (called by cron)."""
    request_id = f"digest-{uuid.uuid4().hex[:12]}"
    logger.info("Generating daily digest")

    # Fetch monthly quick stats (continueOnFail)
    monthly_stats = {}
    try:
        today = date.today()
        monthly_stats = await get_monthly_quick_stats(today.replace(day=1))
    except Exception:
        logger.exception("Monthly quick stats failed (continueOnFail)")

    initial_state = {
        "task_type": "daily_digest",
        "request_id": request_id,
        "digest_pending_approvals": [],  # populated from DB in production
        "digest_new_intakes": [],
        "digest_upcoming_events": [],
        "digest_pending_agreements": [],
        "digest_overdue_deadlines": [],
        "digest_checklist_items_due": [],
        "digest_monthly_stats": monthly_stats,
        "reminders_due": [],
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("daily_digest", request_id),
        )
    except Exception as e:
        logger.exception("Daily digest generation failed")
        return GenericTaskResponse(
            request_id=request_id,
            decision="needs_review",
            errors=[f"Daily digest failed: {e}"],
        )

    return GenericTaskResponse(
        request_id=request_id,
        decision=result.get("decision", "approve"),
        draft_response=result.get("draft_response"),
        errors=result.get("errors", []),
    )


# ============================================================
# Staff Roster endpoint — NEW
# ============================================================

@app.get("/api/v1/staff-roster")
async def staff_roster(
    _auth: str = Security(verify_api_key),
):
    """Return the current CGCS staff roster from cgcs_constants."""
    from app.cgcs_constants import STAFF_ROSTER, MAX_LEADS_PER_STAFF_PER_MONTH
    return {
        "staff": STAFF_ROSTER,
        "max_leads_per_month": MAX_LEADS_PER_STAFF_PER_MONTH,
    }


# ============================================================
# Revenue & Reporting endpoints (API key auth)
# ============================================================

@app.post("/api/v1/reservation/{request_id}/complete", response_model=CompleteReservationResponse)
async def complete_reservation_endpoint(
    request_id: str,
    body: CompleteReservationRequest,
    _auth: str = Security(verify_api_key),
):
    """Mark an approved reservation as completed and record actual revenue/attendance."""
    reservation = await get_reservation(request_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Reservation is '{reservation['status']}', only 'approved' reservations can be completed",
        )

    updated = await complete_reservation(
        request_id=request_id,
        actual_revenue=float(body.actual_revenue) if body.actual_revenue is not None else None,
        actual_attendance=body.actual_attendance,
        event_department=body.event_department,
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Failed to complete reservation")

    await add_audit_entry(
        reservation_id=updated["id"],
        action="reservation_completed",
        actor="admin",
        details={
            "actual_revenue": float(body.actual_revenue) if body.actual_revenue is not None else None,
            "actual_attendance": body.actual_attendance,
            "event_department": body.event_department,
            "notes": body.notes,
        },
    )

    logger.info("Reservation %s completed", request_id)

    return CompleteReservationResponse(
        request_id=request_id,
        status=updated["status"],
        actual_revenue=float(updated["actual_revenue"]) if updated.get("actual_revenue") is not None else None,
        actual_attendance=updated.get("actual_attendance"),
        event_department=updated.get("event_department"),
        completed_at=str(updated["completed_at"]) if updated.get("completed_at") else None,
    )


def _validate_report_params(period: str, start: str) -> date:
    """Validate and parse common report query parameters."""
    if period not in ("week", "month", "quarter", "year"):
        raise HTTPException(status_code=400, detail="Period must be one of: week, month, quarter, year")
    try:
        return date.fromisoformat(start) if start else date.today().replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid start date format. Use YYYY-MM-DD.")


@app.get("/api/v1/reports/revenue", response_model=RevenueReportResponse)
async def revenue_report(
    period: str = "month",
    start: str = "",
    _auth: str = Security(verify_api_key),
):
    """Revenue aggregation report for a given period."""
    start_date = _validate_report_params(period, start)
    result = await get_revenue_report(period, start_date)
    return RevenueReportResponse(**result)


@app.get("/api/v1/reports/conversion-funnel", response_model=ConversionFunnelResponse)
async def conversion_funnel(
    period: str = "month",
    start: str = "",
    _auth: str = Security(verify_api_key),
):
    """Conversion funnel showing reservation counts by stage."""
    start_date = _validate_report_params(period, start)
    result = await get_conversion_funnel(period, start_date)
    return ConversionFunnelResponse(**result)


@app.get("/api/v1/reports/export")
async def export_report(
    format: str = "csv",
    period: str = "month",
    start: str = "",
    _auth: str = Security(verify_api_key),
):
    """Export reservation data as CSV."""
    if format != "csv":
        raise HTTPException(status_code=400, detail="Only 'csv' format is currently supported")

    start_date = _validate_report_params(period, start)
    rows = await get_reservations_for_export(period, start_date)

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow({k: str(v) if v is not None else "" for k, v in row.items()})
    else:
        output.write("No data for the selected period.\n")

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=reservations_{period}_{start}.csv"},
    )


@app.get("/api/v1/reports/top-organizations", response_model=TopOrganizationsResponse)
async def top_organizations(
    period: str = "quarter",
    start: str = "",
    limit: int = 10,
    _auth: str = Security(verify_api_key),
):
    """Top organizations by number of bookings."""
    start_date = _validate_report_params(period, start)
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")

    rows = await get_top_organizations(period, start_date, limit)

    from app.db.report_queries import _compute_end_date
    end_date = _compute_end_date(start_date, period)

    return TopOrganizationsResponse(
        period=period,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        limit=limit,
        organizations=rows,
    )


# ============================================================
# Compliance Checklist endpoints (API key auth)
# ============================================================

@app.get("/api/v1/checklist/{request_id}", response_model=ChecklistResponse)
async def get_event_checklist(
    request_id: str,
    _auth: str = Security(verify_api_key),
):
    """Get all checklist items for an event, with computed deadline info."""
    reservation = await get_reservation(request_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    items = await get_checklist(reservation["id"])
    today = date.today()

    response_items = []
    overdue_count = 0
    completed_count = 0
    pending_count = 0
    for item in items:
        dl = item.get("deadline_date")
        if dl:
            days_until = (dl - today).days
            is_overdue = days_until < 0 and item["status"] in ("pending", "in_review")
        else:
            days_until = None
            is_overdue = False

        if is_overdue:
            overdue_count += 1
        if item["status"] == "completed":
            completed_count += 1
        if item["status"] in ("pending", "in_review"):
            pending_count += 1

        response_items.append(ChecklistItemResponse(
            id=str(item["id"]),
            item_key=item["item_key"],
            item_label=item["item_label"],
            required=item["required"],
            status=item["status"],
            deadline_date=dl.isoformat() if dl else None,
            days_until_deadline=days_until,
            is_overdue=is_overdue,
            completed_at=str(item["completed_at"]) if item.get("completed_at") else None,
            completed_by=item.get("completed_by"),
            notes=item.get("notes"),
        ))

    return ChecklistResponse(
        request_id=request_id,
        items=response_items,
        total=len(response_items),
        completed=completed_count,
        pending=pending_count,
        overdue=overdue_count,
    )


@app.post("/api/v1/checklist/{request_id}/bulk-update", response_model=BulkChecklistUpdateResponse)
async def bulk_update_checklist(
    request_id: str,
    body: BulkChecklistUpdateRequest,
    _auth: str = Security(verify_api_key),
):
    """Update multiple checklist items at once."""
    reservation = await get_reservation(request_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    update_items = [
        {"item_key": item.item_key, "status": item.status, "notes": item.notes}
        for item in body.items
    ]
    count = await bulk_update_checklist_items(reservation["id"], update_items)

    await add_audit_entry(
        reservation_id=reservation["id"],
        action="checklist_bulk_update",
        actor="admin",
        details={"items_updated": count, "items_requested": len(body.items)},
    )

    return BulkChecklistUpdateResponse(
        request_id=request_id,
        updated_count=count,
    )


@app.post("/api/v1/checklist/{request_id}/{item_key}")
async def update_checklist_item_endpoint(
    request_id: str,
    item_key: str,
    body: ChecklistItemUpdateRequest,
    _auth: str = Security(verify_api_key),
):
    """Update a single checklist item."""
    reservation = await get_reservation(request_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    updated = await update_checklist_item(
        reservation_id=reservation["id"],
        item_key=item_key,
        status=body.status,
        notes=body.notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    await add_audit_entry(
        reservation_id=reservation["id"],
        action=f"checklist_item_{body.status}",
        actor="admin",
        details={"item_key": item_key, "notes": body.notes},
    )

    return {
        "request_id": request_id,
        "item_key": item_key,
        "status": updated["status"],
        "completed_at": str(updated["completed_at"]) if updated.get("completed_at") else None,
    }


@app.get("/api/v1/reports/compliance", response_model=ComplianceReportResponse)
async def compliance_report(
    period: str = "quarter",
    start: str = "",
    _auth: str = Security(verify_api_key),
):
    """Compliance report: on-time rates, overdue items, completion stats."""
    start_date = _validate_report_params(period, start)
    result = await get_compliance_report(period, start_date)
    return ComplianceReportResponse(**result)


# ============================================================
# Dynamic Quote Versioning endpoints (API key auth)
# ============================================================

def _quote_to_response(q: dict) -> QuoteVersionResponse:
    """Convert a DB quote row to a response model."""
    return QuoteVersionResponse(
        id=str(q["id"]) if q.get("id") else None,
        reservation_id=str(q["reservation_id"]) if q.get("reservation_id") else None,
        version=q.get("version", 1),
        line_items=[QuoteLineItem(**item) for item in (q.get("line_items") or [])],
        subtotal=float(q.get("subtotal", 0)),
        deposit_amount=float(q.get("deposit_amount", 0)),
        total=float(q.get("total", 0)),
        changes_from_previous=q.get("changes_from_previous"),
        notes=q.get("notes"),
        created_by=q.get("created_by"),
        created_at=str(q["created_at"]) if q.get("created_at") else None,
    )


@app.post("/api/v1/quote/generate/{request_id}", response_model=QuoteGenerateResponse)
async def generate_quote(
    request_id: str,
    _auth: str = Security(verify_api_key),
):
    """Generate an initial quote (version 1) from reservation data."""
    reservation = await get_reservation(request_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    quote_data = build_initial_quote(reservation)
    quote_id = await create_quote_version(reservation["id"], quote_data)
    email_snippet = format_quote_for_email(quote_data)

    await add_audit_entry(
        reservation_id=reservation["id"],
        action="quote_generated",
        actor="admin",
        details={"version": 1, "total": quote_data["total"]},
    )

    quote_data["id"] = str(quote_id)
    quote_data["reservation_id"] = str(reservation["id"])

    return QuoteGenerateResponse(
        reservation_id=request_id,
        quote=QuoteVersionResponse(
            id=str(quote_id),
            reservation_id=str(reservation["id"]),
            version=quote_data["version"],
            line_items=[QuoteLineItem(**item) for item in quote_data["line_items"]],
            subtotal=quote_data["subtotal"],
            deposit_amount=quote_data["deposit_amount"],
            total=quote_data["total"],
        ),
        email_snippet=email_snippet,
    )


@app.post("/api/v1/quote/update/{request_id}", response_model=QuoteUpdateResponse)
async def update_quote_endpoint(
    request_id: str,
    body: QuoteUpdateRequest,
    _auth: str = Security(verify_api_key),
):
    """Add or remove services, creating a new quote version with diff."""
    reservation = await get_reservation(request_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    latest = await get_latest_quote(reservation["id"])
    if not latest:
        raise HTTPException(status_code=404, detail="No existing quote found. Generate one first.")

    # Convert DB row to the format update_quote expects
    current = {
        "version": latest["version"],
        "line_items": latest["line_items"],
        "subtotal": float(latest["subtotal"]),
        "deposit_amount": float(latest["deposit_amount"]),
        "total": float(latest["total"]),
    }

    add_svcs = [{"service": s.service, "hours": s.hours, "count": s.count} for s in body.add_services]
    new_quote = update_quote(current, add_services=add_svcs, remove_services=body.remove_services)
    if body.notes:
        new_quote["notes"] = body.notes

    quote_id = await create_quote_version(
        reservation["id"], new_quote, notes=body.notes, created_by="admin",
    )
    email_snippet = format_quote_for_email(new_quote)

    await add_audit_entry(
        reservation_id=reservation["id"],
        action="quote_updated",
        actor="admin",
        details={
            "version": new_quote["version"],
            "total": new_quote["total"],
            "changes": new_quote.get("changes_from_previous"),
        },
    )

    return QuoteUpdateResponse(
        reservation_id=request_id,
        quote=QuoteVersionResponse(
            id=str(quote_id),
            reservation_id=str(reservation["id"]),
            version=new_quote["version"],
            line_items=[QuoteLineItem(**item) for item in new_quote["line_items"]],
            subtotal=new_quote["subtotal"],
            deposit_amount=new_quote["deposit_amount"],
            total=new_quote["total"],
            changes_from_previous=new_quote.get("changes_from_previous"),
            notes=body.notes,
        ),
        email_snippet=email_snippet,
        changes=new_quote.get("changes_from_previous"),
    )


@app.get("/api/v1/quote/history/{request_id}", response_model=QuoteHistoryResponse)
async def quote_history(
    request_id: str,
    _auth: str = Security(verify_api_key),
):
    """Get all quote versions for a reservation."""
    reservation = await get_reservation(request_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    versions = await get_quote_history(reservation["id"])
    current_version = versions[-1]["version"] if versions else 0

    return QuoteHistoryResponse(
        reservation_id=request_id,
        versions=[_quote_to_response(v) for v in versions],
        current_version=current_version,
    )


@app.get("/api/v1/quote/latest/{request_id}", response_model=QuoteVersionResponse)
async def quote_latest(
    request_id: str,
    _auth: str = Security(verify_api_key),
):
    """Get the latest quote version for a reservation."""
    reservation = await get_reservation(request_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    latest = await get_latest_quote(reservation["id"])
    if not latest:
        raise HTTPException(status_code=404, detail="No quote found for this reservation")

    return _quote_to_response(latest)


# ============================================================
# Process Insights & Quarterly Report endpoints (API key auth)
# ============================================================

@app.get("/api/v1/reports/process-insights", response_model=ProcessInsightsResponse)
async def process_insights(
    period: str = "quarter",
    start: str = "",
    _auth: str = Security(verify_api_key),
):
    """Full process insights report with all metrics sections."""
    start_date = _validate_report_params(period, start)
    report = await build_quarterly_report(start_date)
    return ProcessInsightsResponse(**report)


@app.post("/api/v1/reports/generate-quarterly", response_model=QuarterlyReportResponse)
async def generate_quarterly_report(
    body: QuarterlyReportRequest,
    _auth: str = Security(verify_api_key),
):
    """Generate a quarterly report and optionally email it to admin."""
    try:
        start_date = date.fromisoformat(body.quarter_start)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid quarter_start format. Use YYYY-MM-DD.")

    report = await build_quarterly_report(start_date)

    email_sent = False
    if body.send_email:
        logger.info("Quarterly report email requested for %s", body.quarter_start)
        email_sent = True  # Actual sending handled by N8N webhook

    try:
        await add_audit_entry(
            reservation_id=None,
            action="quarterly_report_generated",
            actor="admin",
            details={"quarter_start": body.quarter_start, "email_sent": email_sent},
        )
    except Exception:
        logger.exception("Audit entry for quarterly report failed")

    from datetime import datetime
    return QuarterlyReportResponse(
        report=ProcessInsightsResponse(**report),
        generated_at=datetime.now().isoformat(),
        email_sent=email_sent,
    )


# ============================================================
# N8N Webhook endpoints (webhook secret auth)
# ============================================================

@app.post("/webhook/smartsheet-new-entry")
async def webhook_smartsheet_new_entry(
    body: SmartsheetWebhookRequest,
    _auth: str = Security(verify_webhook_secret),
):
    """Full intake pipeline: parse → 14-day check → classify → ack → P.E.T. + calendar → draft."""
    request_id = f"ss-{uuid.uuid4().hex[:12]}"
    logger.info("Smartsheet intake webhook: %s", request_id)

    # 1. Validate Smartsheet email
    if not is_smartsheet_intake(body.subject, body.sender):
        return {"request_id": request_id, "status": "skipped", "reason": "Not a Smartsheet intake email"}

    # 2. Parse
    parsed = parse_smartsheet_intake(body.subject, body.body)
    if not parsed.get("event_name"):
        return {"request_id": request_id, "status": "error", "reason": "Could not parse event name from email"}

    # 3. 14-day lead time check
    event_date = parsed.get("event_start_date")
    if event_date and not is_within_minimum_lead_time(event_date, MINIMUM_LEAD_TIME_BD):
        bd = business_days_until(event_date)
        return {
            "request_id": request_id,
            "status": "rejected",
            "reason": f"Event is only {bd} business days away (minimum {MINIMUM_LEAD_TIME_BD} required)",
            "event_name": parsed.get("event_name"),
        }

    # 4. Run smartsheet_intake graph (classify + draft)
    initial_state = {
        "task_type": "smartsheet_intake",
        "request_id": request_id,
        "smartsheet_parsed": parsed,
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("smartsheet_intake", request_id),
        )
    except Exception as e:
        logger.exception("Smartsheet intake pipeline failed for %s", request_id)
        try:
            await add_dead_letter(
                request_id=request_id,
                payload=initial_state,
                error_message=f"{type(e).__name__}: {e}",
                error_type="smartsheet_intake_failure",
            )
            err_class = classify_error(e)
            if err_class["should_alert"]:
                await create_alert(**build_error_alert(e, f"Smartsheet intake {request_id}", request_id))
        except Exception:
            logger.exception("CRITICAL: Failed to write to DLQ/alert")

        return {"request_id": request_id, "status": "error", "reason": str(e)}

    # 5. Build acknowledgment email (continueOnFail)
    ack_email = None
    try:
        date_str = _format_event_date(event_date) if event_date else ""
        ack_email = build_intake_acknowledgment_email(
            parsed.get("requestor_name", ""),
            parsed.get("event_name", ""),
            date_str,
        )
    except Exception:
        logger.exception("Acknowledgment email build failed (continueOnFail)")

    return {
        "request_id": request_id,
        "status": "processed",
        "difficulty": result.get("intake_difficulty"),
        "auto_send": result.get("email_auto_send", False),
        "draft_response": result.get("draft_response"),
        "draft_emails": result.get("intake_draft_emails", []),
        "acknowledgment": ack_email,
        "parsed": parsed,
    }


@app.post("/webhook/email-reply")
async def webhook_email_reply(
    body: EmailReplyWebhookRequest,
    _auth: str = Security(verify_webhook_secret),
):
    """Process a reply in an existing event thread."""
    request_id = body.request_id or f"reply-{uuid.uuid4().hex[:12]}"
    logger.info("Email reply webhook: %s thread=%s", request_id, body.thread_id)

    initial_state = {
        "task_type": "email_reply",
        "request_id": request_id,
        "reply_body": body.reply_body,
        "edit_loop_count": body.edit_loop_count,
        "failed_replies": body.failed_replies,
        "smartsheet_parsed": body.smartsheet_parsed or {},
        "errors": [],
    }

    try:
        result = compiled_graph.invoke(
            initial_state,
            config=_run_config("email_reply", request_id),
        )
    except Exception as e:
        logger.exception("Email reply processing failed for %s", request_id)
        try:
            await add_dead_letter(
                request_id=request_id,
                payload=initial_state,
                error_message=f"{type(e).__name__}: {e}",
                error_type="email_reply_failure",
            )
        except Exception:
            logger.exception("CRITICAL: Failed to write to DLQ")
        return {"request_id": request_id, "status": "error", "reason": str(e)}

    # Create dashboard alerts for AV/catering changes (continueOnFail)
    for alert_data in result.get("reply_alerts", []):
        try:
            await create_alert(**alert_data)
        except Exception:
            logger.exception("Failed to create alert (continueOnFail)")

    return {
        "request_id": request_id,
        "thread_id": body.thread_id,
        "status": "processed",
        "action": result.get("reply_action"),
        "edit_loop_count": result.get("edit_loop_count"),
        "escalation_detected": result.get("escalation_detected", False),
        "escalation_forward_to": result.get("escalation_forward_to"),
        "draft_response": result.get("draft_response"),
        "draft_emails": result.get("reply_draft_emails", []),
        "alerts_created": len(result.get("reply_alerts", [])),
        "decision": result.get("decision"),
    }


@app.post("/webhook/admin-response")
async def webhook_admin_response(
    body: AdminResponseWebhookRequest,
    _auth: str = Security(verify_webhook_secret),
):
    """Admin approves, rejects, or edits a draft from the dashboard."""
    logger.info("Admin response webhook: email=%s action=%s", body.email_id, body.action)

    await add_audit_entry(
        reservation_id=None,
        action=f"admin_draft_{body.action}",
        actor="admin",
        details={
            "email_id": body.email_id,
            "has_edit": body.edited_text is not None,
        },
    )

    return {
        "email_id": body.email_id,
        "action": body.action,
        "status": "approved" if body.action == "approve" else body.action,
        "edited": body.edited_text is not None,
    }


@app.post("/webhook/police-confirmed")
async def webhook_police_confirmed(
    body: PoliceConfirmedWebhookRequest,
    _auth: str = Security(verify_webhook_secret),
):
    """Officer Ortiz confirmed police coverage for an event."""
    request_id = body.request_id or f"police-{uuid.uuid4().hex[:12]}"
    logger.info("Police confirmed webhook: %s", request_id)

    await add_audit_entry(
        reservation_id=None,
        action="police_coverage_confirmed",
        actor="police",
        details={
            "request_id": request_id,
            "sender": body.sender,
            "reply_excerpt": body.reply_body[:500],
        },
    )

    return {
        "request_id": request_id,
        "status": "confirmed",
        "sender": body.sender,
    }


# ============================================================
# Dashboard Alerts endpoints (API key auth)
# ============================================================

@app.get("/api/v1/alerts/active", response_model=DashboardAlertsListResponse)
async def list_active_alerts(
    _auth: str = Security(verify_api_key),
):
    """Return all active dashboard alerts."""
    alerts = await get_active_alerts()
    return DashboardAlertsListResponse(
        count=len(alerts),
        alerts=[
            DashboardAlertResponse(
                id=str(a["id"]),
                reservation_id=str(a["reservation_id"]) if a.get("reservation_id") else None,
                alert_type=a["alert_type"],
                title=a["title"],
                detail=a.get("detail"),
                status=a["status"],
                created_at=str(a["created_at"]) if a.get("created_at") else None,
            )
            for a in alerts
        ],
    )


@app.post("/api/v1/alerts/{alert_id}/dismiss")
async def dismiss_alert_endpoint(
    alert_id: str,
    _auth: str = Security(verify_api_key),
):
    """Mark a dashboard alert as dismissed."""
    dismissed = await dismiss_alert(alert_id)
    if not dismissed:
        raise HTTPException(status_code=404, detail="Alert not found or already dismissed")
    return {"id": alert_id, "status": "dismissed"}
