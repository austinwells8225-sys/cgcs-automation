"""Database queries for event leads and reminders."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from app.db.connection import get_pool


async def create_event_lead(data: dict[str, Any]) -> UUID:
    """Insert a new event lead assignment."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.event_leads (reservation_id, request_id, staff_name, staff_email)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (reservation_id) DO UPDATE SET
            staff_name = EXCLUDED.staff_name,
            staff_email = EXCLUDED.staff_email,
            updated_at = NOW()
        RETURNING id
        """,
        data.get("reservation_id"),
        data.get("request_id"),
        data["staff_name"],
        data["staff_email"],
    )
    return row["id"]


async def get_event_lead(reservation_id: UUID) -> dict | None:
    """Fetch the lead for a reservation."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM cgcs.event_leads WHERE reservation_id = $1",
        reservation_id,
    )
    return dict(row) if row else None


async def get_lead_by_request_id(request_id: str) -> dict | None:
    """Fetch a lead by request_id."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM cgcs.event_leads WHERE request_id = $1",
        request_id,
    )
    return dict(row) if row else None


async def create_reminder(data: dict[str, Any]) -> UUID:
    """Insert a scheduled reminder."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.event_reminders (
            reservation_id, lead_id, staff_email, reminder_type, remind_date
        ) VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        data.get("reservation_id"),
        data.get("lead_id"),
        data["staff_email"],
        data["reminder_type"],
        data["remind_date"],
    )
    return row["id"]


async def get_due_reminders(as_of: date | None = None) -> list[dict]:
    """Fetch all pending reminders due on or before the given date."""
    if as_of is None:
        as_of = date.today()
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT r.*, l.staff_name, l.reservation_id as lead_reservation_id
        FROM cgcs.event_reminders r
        JOIN cgcs.event_leads l ON r.lead_id = l.id
        WHERE r.status = 'pending' AND r.remind_date <= $1
        ORDER BY r.remind_date ASC
        """,
        as_of,
    )
    return [dict(r) for r in rows]


async def mark_reminder_sent(reminder_id: UUID) -> bool:
    """Mark a reminder as sent."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE cgcs.event_reminders
        SET status = 'sent', sent_at = NOW(), updated_at = NOW()
        WHERE id = $1 AND status = 'pending'
        """,
        reminder_id,
    )
    return result == "UPDATE 1"


async def mark_reminder_failed(reminder_id: UUID, error: str) -> bool:
    """Mark a reminder as failed."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE cgcs.event_reminders
        SET status = 'failed', error_message = $2, updated_at = NOW()
        WHERE id = $1
        """,
        reminder_id,
        error,
    )
    return result == "UPDATE 1"
