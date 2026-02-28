"""Database queries for calendar holds."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.connection import get_pool


async def create_hold(data: dict[str, Any]) -> UUID:
    """Insert a new calendar hold record."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.calendar_holds (
            request_id, org_name, hold_date, start_time, end_time,
            google_event_id, created_by
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """,
        data.get("request_id"),
        data["org_name"],
        data["hold_date"],
        data["start_time"],
        data["end_time"],
        data.get("google_event_id"),
        data.get("created_by", "admin"),
    )
    return row["id"]


async def get_hold(hold_id: UUID) -> dict | None:
    """Fetch a calendar hold by ID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM cgcs.calendar_holds WHERE id = $1",
        hold_id,
    )
    return dict(row) if row else None


async def get_active_holds(hold_date: str | None = None) -> list[dict]:
    """Fetch active holds, optionally filtered by date."""
    pool = await get_pool()
    if hold_date:
        rows = await pool.fetch(
            """
            SELECT * FROM cgcs.calendar_holds
            WHERE status = 'active' AND hold_date = $1
            ORDER BY start_time ASC
            """,
            hold_date,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM cgcs.calendar_holds
            WHERE status = 'active'
            ORDER BY hold_date ASC, start_time ASC
            """
        )
    return [dict(r) for r in rows]


async def release_hold(hold_id: UUID) -> bool:
    """Release (cancel) a calendar hold."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE cgcs.calendar_holds
        SET status = 'released', released_at = NOW(), updated_at = NOW()
        WHERE id = $1 AND status = 'active'
        """,
        hold_id,
    )
    return result == "UPDATE 1"


async def convert_hold(hold_id: UUID) -> bool:
    """Convert a hold to a confirmed reservation."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE cgcs.calendar_holds
        SET status = 'converted', updated_at = NOW()
        WHERE id = $1 AND status = 'active'
        """,
        hold_id,
    )
    return result == "UPDATE 1"
