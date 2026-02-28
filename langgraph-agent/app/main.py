import json
import logging
import traceback
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
    EvaluateRequest,
    EvaluateResponse,
    HealthResponse,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CGCS LangGraph Agent starting up")
    yield
    logger.info("Shutting down, closing DB pool")
    await close_pool()


app = FastAPI(
    title="CGCS Event Space Evaluation Agent",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None,
)


# --- Health (unauthenticated) ---

@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", environment=settings.environment)


# --- Evaluate (webhook secret auth) ---

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
        result = compiled_graph.invoke(initial_state)
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


# --- Admin endpoints (API key auth) ---

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


# --- Dead letter queue admin endpoints ---

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
