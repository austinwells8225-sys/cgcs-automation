"""Database queries for P.E.T. tracker staged updates."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.db.connection import get_pool


async def create_staged_update(data: dict[str, Any]) -> UUID:
    """Insert a staged P.E.T. update."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.pet_staged_updates (staged_id, row_data)
        VALUES ($1, $2::jsonb)
        RETURNING id
        """,
        data["staged_id"],
        json.dumps(data["row_data"]),
    )
    return row["id"]


async def get_staged_update(staged_id: str) -> dict | None:
    """Fetch a staged update by staged_id."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM cgcs.pet_staged_updates WHERE staged_id = $1",
        staged_id,
    )
    return dict(row) if row else None


async def get_pending_updates() -> list[dict]:
    """Fetch all pending staged updates."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM cgcs.pet_staged_updates
        WHERE status = 'pending'
        ORDER BY created_at DESC
        """
    )
    return [dict(r) for r in rows]


async def approve_staged_update(staged_id: str, approved_by: str = "admin") -> dict | None:
    """Approve a staged update."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE cgcs.pet_staged_updates
        SET status = 'approved', approved_by = $2, approved_at = NOW(), updated_at = NOW()
        WHERE staged_id = $1 AND status = 'pending'
        RETURNING *
        """,
        staged_id,
        approved_by,
    )
    return dict(row) if row else None


async def mark_update_applied(staged_id: str) -> bool:
    """Mark a staged update as applied to the spreadsheet."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE cgcs.pet_staged_updates
        SET status = 'applied', applied_at = NOW(), updated_at = NOW()
        WHERE staged_id = $1 AND status = 'approved'
        """,
        staged_id,
    )
    return result == "UPDATE 1"


async def mark_update_failed(staged_id: str, error: str) -> bool:
    """Mark a staged update as failed."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE cgcs.pet_staged_updates
        SET status = 'pending', error_message = $2, updated_at = NOW()
        WHERE staged_id = $1
        """,
        staged_id,
        error,
    )
    return result == "UPDATE 1"
