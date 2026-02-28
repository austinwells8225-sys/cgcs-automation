import json
import logging
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, Security
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
from app.models import (
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

    initial_state = {
        "task_type": "email_triage",
        "request_id": request_id,
        "email_id": request.email_id,
        "email_from": request.email_from,
        "email_subject": request.email_subject,
        "email_body": request.email_body,
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
    """Admin approves or rejects an email draft reply."""
    # In production, this looks up from cgcs.email_tasks and sends via Zoho
    logger.info("Email %s %sd by admin", email_id, body.action)
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
