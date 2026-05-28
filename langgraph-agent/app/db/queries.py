from __future__ import annotations

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


async def get_reservation_by_uuid(reservation_id: str) -> dict | None:
    """Fetch a reservation by UUID. Returns every column including source_metadata."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM cgcs.reservations WHERE id = $1::uuid",
        reservation_id,
    )
    return dict(row) if row else None


async def get_reservation(request_id: str) -> dict | None:
    """Fetch a reservation by request_id."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM cgcs.reservations WHERE request_id = $1",
        request_id,
    )
    return dict(row) if row else None


SORTABLE_COLUMNS = {
    "date": "requested_date",
    "event": "event_name",
    "org": "requester_organization",
    "lead": "cgcs_lead",
    "category": "event_category",
    "status": "status",
    "revenue": "actual_revenue",
    "attendees": "actual_attendance",
}


VALID_EVENT_CATEGORIES = {"cgcs", "acc", "monetization"}
VALID_RESERVATION_STATUSES = {"pending_review", "approved", "rejected", "cancelled", "completed"}

# Whitelist of cgcs.reservations columns that the dashboard can update inline.
# Anything not in this set is rejected at the API layer.
TEXT_FIELDS = {"cgcs_lead", "event_name", "requester_organization", "requester_name",
               "requester_email", "event_description", "admin_notes", "room_requested"}
NUM_FIELDS = {"actual_revenue", "actual_attendance", "estimated_attendees",
              "attendance_students", "attendance_staff", "attendance_community"}
DATE_FIELDS = {"requested_date"}
TIME_FIELDS = {"requested_start_time", "requested_end_time"}
ENUM_FIELDS = {
    "status": ("reservation_status", VALID_RESERVATION_STATUSES),
    "event_category": ("cgcs.event_category", VALID_EVENT_CATEGORIES),
}
# Source metadata is a JSONB blob; updates merge new keys into the existing blob.
META_FIELDS = {"ad_astra", "tdx", "floor_layout", "walkthrough", "invoice_generated",
               "av", "catering", "staffing", "poc_name", "poc_email", "poc_phone",
               "organization", "event_title", "agreement_sent", "stage", "rooms",
               "cgcs_labor", "additional_needs", "cal_status", "internal_notes"}


def _coerce_date(v):
    """asyncpg needs a datetime.date for DATE columns."""
    from datetime import date as _date
    if v in (None, ""): return None
    if isinstance(v, _date): return v
    return _date.fromisoformat(str(v))


def _coerce_time(v):
    """asyncpg needs a datetime.time for TIME columns. Accepts HH:MM or HH:MM:SS."""
    from datetime import time as _time
    if v in (None, ""): return None
    if isinstance(v, _time): return v
    parts = str(v).split(":")
    h = int(parts[0]); m = int(parts[1]); s = int(parts[2]) if len(parts) > 2 else 0
    return _time(h, m, s)


async def auto_complete_past_events() -> int:
    """Flip status from 'approved' to 'completed' for any event whose
    requested_date is in the past. Idempotent. Returns the row count touched.
    """
    pool = await get_pool()
    res = await pool.execute(
        """
        UPDATE cgcs.reservations
        SET status = 'completed'::reservation_status,
            completed_at = COALESCE(completed_at, (requested_date + INTERVAL '0')::timestamptz),
            updated_at = NOW()
        WHERE status = 'approved'::reservation_status
          AND requested_date < CURRENT_DATE
        """
    )
    # asyncpg returns "UPDATE n" as the result string
    try:
        return int(res.split()[-1])
    except Exception:
        return 0


async def create_minimal_reservation(payload: dict) -> dict:
    """Create a new reservation from a small dashboard-form payload.

    Required keys: event_name, requested_date, requested_start_time, requested_end_time.
    Optional keys: everything in TEXT_FIELDS / NUM_FIELDS / META_FIELDS / ENUM_FIELDS.
    Auto-fills required-NOT-NULL columns (request_id, requester_name, requester_email)
    when the user didn't supply them.
    """
    import uuid as _uuid, json

    required = ("event_name", "requested_date", "requested_start_time", "requested_end_time")
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    pool = await get_pool()
    request_id = payload.get("request_id") or f"pet-{_uuid.uuid4().hex[:10]}"

    cols: list[str] = ["request_id", "requester_name", "requester_email", "event_name",
                       "requested_date", "requested_start_time", "requested_end_time",
                       "status", "source"]
    args: list = [
        request_id,
        payload.get("requester_name") or payload.get("cgcs_lead") or "Manual entry",
        payload.get("requester_email") or "unknown@unknown.com",
        payload["event_name"],
        _coerce_date(payload["requested_date"]),
        _coerce_time(payload["requested_start_time"]),
        _coerce_time(payload["requested_end_time"]),
        payload.get("status") or "approved",
        "manual_dashboard",
    ]
    placeholders: list[str] = [f"${i+1}" for i in range(len(args))]
    # status needs ENUM cast
    placeholders[7] = f"${8}::reservation_status"

    meta_patch: dict = {}
    for key, val in payload.items():
        if key in cols or key in required:
            continue
        if key in TEXT_FIELDS:
            cols.append(key); args.append(val if val != "" else None)
            placeholders.append(f"${len(args)}")
        elif key in NUM_FIELDS:
            cols.append(key); args.append(float(val) if val not in (None, "", "null") else None)
            placeholders.append(f"${len(args)}")
        elif key in DATE_FIELDS:
            cols.append(key); args.append(_coerce_date(val))
            placeholders.append(f"${len(args)}")
        elif key in TIME_FIELDS:
            cols.append(key); args.append(_coerce_time(val))
            placeholders.append(f"${len(args)}")
        elif key in ENUM_FIELDS:
            enum_type, allowed = ENUM_FIELDS[key]
            if val not in allowed:
                raise ValueError(f"Invalid {key}: {val!r}")
            cols.append(key); args.append(val)
            placeholders.append(f"${len(args)}::{enum_type}")
        elif key in META_FIELDS:
            meta_patch[key] = val
    if meta_patch:
        cols.append("source_metadata"); args.append(json.dumps(meta_patch))
        placeholders.append(f"${len(args)}::jsonb")

    sql = f"""
        INSERT INTO cgcs.reservations ({', '.join(cols)})
        VALUES ({', '.join(placeholders)})
        RETURNING id, request_id, event_name, requested_date, status
    """
    row = await pool.fetchrow(sql, *args)
    return dict(row) if row else {}


async def update_reservation_fields(reservation_id: str, updates: dict) -> dict | None:
    """Update any subset of allowed fields on a reservation. Returns the updated row.

    `updates` is a flat dict like {"cgcs_lead": "Cate", "status": "completed",
    "ad_astra": "#20260101-00042"}. Each key is validated against the whitelist;
    META_FIELDS get merged into source_metadata JSONB, the rest become column
    updates.
    """
    if not updates:
        return None
    pool = await get_pool()
    set_parts: list[str] = []
    args: list = [reservation_id]
    meta_patch: dict = {}

    for key, val in updates.items():
        if key in TEXT_FIELDS:
            args.append(val if val != "" else None)
            set_parts.append(f"{key} = ${len(args)}")
        elif key in NUM_FIELDS:
            args.append(float(val) if val not in (None, "", "null") else None)
            set_parts.append(f"{key} = ${len(args)}")
        elif key in DATE_FIELDS:
            args.append(_coerce_date(val))
            set_parts.append(f"{key} = ${len(args)}")
        elif key in TIME_FIELDS:
            args.append(_coerce_time(val))
            set_parts.append(f"{key} = ${len(args)}")
        elif key in ENUM_FIELDS:
            enum_type, allowed = ENUM_FIELDS[key]
            if val not in allowed:
                raise ValueError(f"Invalid {key} value: {val!r}")
            args.append(val)
            set_parts.append(f"{key} = ${len(args)}::{enum_type}")
        elif key in META_FIELDS:
            meta_patch[key] = val if val != "" else None
        else:
            raise ValueError(f"Field {key!r} is not editable via this endpoint")

    if meta_patch:
        import json
        args.append(json.dumps(meta_patch))
        set_parts.append(f"source_metadata = source_metadata || ${len(args)}::jsonb")

    if not set_parts:
        return None
    set_parts.append("updated_at = NOW()")

    sql = f"""
        UPDATE cgcs.reservations
        SET {', '.join(set_parts)}
        WHERE id = $1::uuid
        RETURNING id, event_name, status, event_category, cgcs_lead
    """
    row = await pool.fetchrow(sql, *args)
    return dict(row) if row else None


async def update_reservation_category(reservation_id: str, category: str) -> dict | None:
    """Update a reservation's event_category by UUID. Returns the updated row or None."""
    if category not in VALID_EVENT_CATEGORIES:
        raise ValueError(f"Invalid category: {category!r}")
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE cgcs.reservations
        SET event_category = $2::cgcs.event_category, updated_at = NOW()
        WHERE id = $1::uuid
        RETURNING id, event_name, event_category
        """,
        reservation_id, category,
    )
    return dict(row) if row else None


async def list_reservations(
    status: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 500,
    sort: str | None = None,
    direction: str = "desc",
) -> list[dict]:
    """List reservations for the dashboard table."""
    pool = await get_pool()
    # Default sort = "upcoming first, then most-recent past."
    # Only kicks in when caller didn't explicitly ask for a sort column.
    if not sort or sort.lower() == "date":
        order_clause = (
            "(requested_date >= CURRENT_DATE) DESC, "
            "CASE WHEN requested_date >= CURRENT_DATE THEN requested_date END ASC NULLS LAST, "
            "CASE WHEN requested_date <  CURRENT_DATE THEN requested_date END DESC NULLS LAST, "
            "created_at DESC"
        )
    else:
        column = SORTABLE_COLUMNS.get(sort.lower(), "requested_date")
        dir_sql = "ASC" if direction.lower() == "asc" else "DESC"
        order_clause = f"{column} {dir_sql} NULLS LAST, created_at DESC"

    where_parts: list[str] = []
    args: list = [limit]
    if status:
        args.append(status)
        where_parts.append(f"status = ${len(args)}::reservation_status")
    if category:
        args.append(category)
        where_parts.append(f"event_category = ${len(args)}::cgcs.event_category")
    if date_from:
        args.append(date_from)
        where_parts.append(f"requested_date >= ${len(args)}::date")
    if date_to:
        args.append(date_to)
        where_parts.append(f"requested_date < ${len(args)}::date")
    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    rows = await pool.fetch(
        f"""
        SELECT id, request_id, event_name, requester_organization,
               requested_date, requested_start_time, requested_end_time,
               room_requested, status, event_category, event_subtype,
               actual_revenue, actual_attendance, source, cgcs_lead, created_at,
               source_metadata->>'ad_astra'         AS meta_ad_astra,
               source_metadata->>'tdx'              AS meta_tdx,
               source_metadata->>'floor_layout'     AS meta_layout,
               source_metadata->>'walkthrough'      AS meta_walkthrough,
               source_metadata->>'invoice_generated' AS meta_invoice,
               source_metadata->>'av'               AS meta_av,
               source_metadata->>'catering'         AS meta_catering,
               source_metadata->>'poc_email'        AS meta_poc_email,
               source_metadata->>'poc_phone'        AS meta_poc_phone
        FROM cgcs.reservations
        {where_sql}
        ORDER BY {order_clause}
        LIMIT $1
        """,
        *args,
    )
    return [dict(r) for r in rows]


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
