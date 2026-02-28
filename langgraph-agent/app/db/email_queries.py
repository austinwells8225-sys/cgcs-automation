"""Database queries for email triage tasks."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.db.connection import get_pool


async def create_email_task(data: dict[str, Any]) -> UUID:
    """Insert a new email triage task."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.email_tasks (
            request_id, email_id, email_from, email_to, email_subject, email_body,
            priority, category, draft_reply, auto_send, status
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING id
        """,
        data["request_id"],
        data.get("email_id"),
        data["email_from"],
        data.get("email_to"),
        data.get("email_subject"),
        data.get("email_body"),
        data.get("priority", "medium"),
        data.get("category", "other"),
        data.get("draft_reply"),
        data.get("auto_send", False),
        "pending_review",
    )
    return row["id"]


async def get_email_task(request_id: str) -> dict | None:
    """Fetch an email task by request_id."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM cgcs.email_tasks WHERE request_id = $1",
        request_id,
    )
    return dict(row) if row else None


async def get_pending_emails() -> list[dict]:
    """Fetch all pending email tasks."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM cgcs.email_tasks
        WHERE status = 'pending_review'
        ORDER BY created_at DESC
        """
    )
    return [dict(r) for r in rows]


async def approve_email_task(
    request_id: str,
    admin_notes: str | None = None,
    edited_reply: str | None = None,
) -> dict | None:
    """Approve an email task for sending."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE cgcs.email_tasks
        SET status = 'approved',
            admin_notes = COALESCE($2, admin_notes),
            draft_reply = COALESCE($3, draft_reply),
            updated_at = NOW()
        WHERE request_id = $1 AND status = 'pending_review'
        RETURNING *
        """,
        request_id,
        admin_notes,
        edited_reply,
    )
    return dict(row) if row else None


async def mark_email_sent(request_id: str) -> bool:
    """Mark an email task as sent."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE cgcs.email_tasks
        SET status = 'sent', sent_at = NOW(), updated_at = NOW()
        WHERE request_id = $1 AND status IN ('approved', 'pending_review')
        """,
        request_id,
    )
    return result == "UPDATE 1"
