import json
from typing import Any
from uuid import UUID

from app.db.connection import get_pool


async def create_reservation(data: dict[str, Any]) -> UUID:
    """Insert a new reservation record and return its UUID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.reservations (
            request_id, requester_name, requester_email, requester_organization,
            event_name, event_description, requested_date, requested_start_time,
            requested_end_time, room_requested, estimated_attendees,
            setup_requirements, pricing_tier, estimated_cost,
            is_eligible, eligibility_reason, calendar_available,
            ai_decision, ai_draft_response, status
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9,
            $10::cgcs.room_type, $11,
            $12::jsonb, $13::cgcs.pricing_tier, $14,
            $15, $16, $17, $18, $19,
            'pending_review'::cgcs.reservation_status
        )
        RETURNING id
        """,
        data["request_id"],
        data["requester_name"],
        data["requester_email"],
        data.get("requester_organization"),
        data["event_name"],
        data.get("event_description"),
        data["requested_date"],
        data["requested_start_time"],
        data["requested_end_time"],
        data.get("room_assignment") or data.get("room_requested"),
        data.get("estimated_attendees"),
        data.get("setup_config"),
        data.get("pricing_tier"),
        data.get("estimated_cost"),
        data.get("is_eligible"),
        data.get("eligibility_reason"),
        data.get("calendar_available"),
        data.get("decision"),
        data.get("draft_response"),
    )
    return row["id"]


async def get_reservation(request_id: str) -> dict | None:
    """Fetch a reservation by request_id."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM cgcs.reservations WHERE request_id = $1",
        request_id,
    )
    return dict(row) if row else None


async def approve_reservation(
    request_id: str,
    admin_notes: str | None = None,
    edited_response: str | None = None,
) -> dict | None:
    """Mark a reservation as approved by admin."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE cgcs.reservations
        SET status = 'approved'::cgcs.reservation_status,
            admin_approved_at = NOW(),
            admin_notes = COALESCE($2, admin_notes),
            ai_draft_response = COALESCE($3, ai_draft_response),
            updated_at = NOW()
        WHERE request_id = $1 AND status = 'pending_review'::cgcs.reservation_status
        RETURNING *
        """,
        request_id,
        admin_notes,
        edited_response,
    )
    return dict(row) if row else None


async def reject_reservation(
    request_id: str,
    admin_notes: str | None = None,
) -> dict | None:
    """Mark a reservation as rejected by admin."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE cgcs.reservations
        SET status = 'rejected'::cgcs.reservation_status,
            admin_approved_at = NOW(),
            admin_notes = COALESCE($2, admin_notes),
            updated_at = NOW()
        WHERE request_id = $1 AND status = 'pending_review'::cgcs.reservation_status
        RETURNING *
        """,
        request_id,
        admin_notes,
    )
    return dict(row) if row else None


async def add_audit_entry(
    reservation_id: UUID,
    action: str,
    actor: str,
    details: dict | None = None,
) -> None:
    """Insert an audit trail entry."""
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO cgcs.audit_trail (reservation_id, action, actor, details)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        reservation_id,
        action,
        actor,
        json.dumps(details) if details else None,
    )


async def add_dead_letter(
    request_id: str | None,
    payload: dict,
    error_message: str,
    error_type: str,
) -> int:
    """Insert a failed request into the dead letter queue. Returns the DLQ entry ID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.dead_letter_queue (request_id, payload, error_message, error_type)
        VALUES ($1, $2::jsonb, $3, $4)
        RETURNING id
        """,
        request_id,
        json.dumps(payload),
        error_message,
        error_type,
    )
    return row["id"]


async def increment_dead_letter_failure(request_id: str) -> int:
    """Increment failure count for an existing DLQ entry. Returns new count."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE cgcs.dead_letter_queue
        SET failure_count = failure_count + 1,
            error_message = error_message
        WHERE request_id = $1 AND status = 'pending'
        RETURNING failure_count
        """,
        request_id,
    )
    return row["failure_count"] if row else 0


async def get_dead_letter_entries(status: str = "pending") -> list[dict]:
    """Fetch dead letter queue entries by status."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM cgcs.dead_letter_queue
        WHERE status = $1
        ORDER BY created_at DESC
        """,
        status,
    )
    return [dict(r) for r in rows]


async def resolve_dead_letter(dlq_id: int, resolved_by: str = "admin") -> bool:
    """Mark a dead letter entry as resolved."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE cgcs.dead_letter_queue
        SET status = 'resolved', resolved_at = NOW(), resolved_by = $2
        WHERE id = $1 AND status = 'pending'
        """,
        dlq_id,
        resolved_by,
    )
    return result == "UPDATE 1"
