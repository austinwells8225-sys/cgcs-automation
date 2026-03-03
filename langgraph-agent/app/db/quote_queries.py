"""Database queries for quote versioning."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.db.connection import get_pool


async def create_quote_version(
    reservation_id: UUID | str,
    quote_data: dict,
    notes: str | None = None,
    created_by: str = "system",
) -> UUID:
    """Insert a new quote version."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.quote_versions (
            reservation_id, version, line_items, subtotal,
            deposit_amount, total, changes_from_previous, notes, created_by
        ) VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7::jsonb, $8, $9)
        RETURNING id
        """,
        reservation_id if isinstance(reservation_id, UUID) else UUID(str(reservation_id)),
        quote_data["version"],
        json.dumps(quote_data["line_items"]),
        quote_data["subtotal"],
        quote_data.get("deposit_amount", 0),
        quote_data["total"],
        json.dumps(quote_data["changes_from_previous"]) if quote_data.get("changes_from_previous") else None,
        notes or quote_data.get("notes"),
        created_by,
    )
    return row["id"]


async def get_latest_quote(reservation_id: UUID | str) -> dict | None:
    """Fetch the latest quote version for a reservation."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, reservation_id, version, line_items, subtotal,
               deposit_amount, total, changes_from_previous, notes,
               created_by, created_at
        FROM cgcs.quote_versions
        WHERE reservation_id = $1
        ORDER BY version DESC
        LIMIT 1
        """,
        reservation_id if isinstance(reservation_id, UUID) else UUID(str(reservation_id)),
    )
    return dict(row) if row else None


async def get_quote_history(reservation_id: UUID | str) -> list[dict]:
    """Fetch all quote versions for a reservation, ordered by version."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, reservation_id, version, line_items, subtotal,
               deposit_amount, total, changes_from_previous, notes,
               created_by, created_at
        FROM cgcs.quote_versions
        WHERE reservation_id = $1
        ORDER BY version ASC
        """,
        reservation_id if isinstance(reservation_id, UUID) else UUID(str(reservation_id)),
    )
    return [dict(r) for r in rows]


async def get_quote_version(quote_id: UUID | str) -> dict | None:
    """Fetch a specific quote version by ID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, reservation_id, version, line_items, subtotal,
               deposit_amount, total, changes_from_previous, notes,
               created_by, created_at
        FROM cgcs.quote_versions
        WHERE id = $1
        """,
        quote_id if isinstance(quote_id, UUID) else UUID(str(quote_id)),
    )
    return dict(row) if row else None
