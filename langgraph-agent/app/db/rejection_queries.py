"""Database queries for email rejection patterns and self-improving prompts."""

from __future__ import annotations

import json
from typing import Any

from app.db.connection import get_pool


async def create_rejection_pattern(
    email_task_id: str | None,
    original_draft: str,
    rejection_reason: str,
    revision_options: list[dict],
    category: str | None = None,
) -> int:
    """Insert a new rejection pattern with AI-generated revisions."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.email_rejection_patterns (
            email_task_id, original_draft, rejection_reason,
            revision_options, category
        ) VALUES ($1, $2, $3, $4::jsonb, $5)
        RETURNING id
        """,
        email_task_id,
        original_draft,
        rejection_reason,
        json.dumps(revision_options),
        category,
    )
    return row["id"]


async def select_revision(
    pattern_id: int,
    revision_index: int | None,
    final_draft: str,
) -> bool:
    """Record which revision the admin selected (or custom draft)."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE cgcs.email_rejection_patterns
        SET selected_revision_index = $2,
            final_draft = $3,
            updated_at = NOW()
        WHERE id = $1
        """,
        pattern_id,
        revision_index,
        final_draft,
    )
    return result == "UPDATE 1"


async def get_rejection_patterns(
    category: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Fetch recent rejection patterns, optionally filtered by category."""
    pool = await get_pool()
    if category:
        rows = await pool.fetch(
            """
            SELECT id, email_task_id, original_draft, rejection_reason,
                   revision_options, selected_revision_index, final_draft,
                   category, created_at
            FROM cgcs.email_rejection_patterns
            WHERE category = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            category,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, email_task_id, original_draft, rejection_reason,
                   revision_options, selected_revision_index, final_draft,
                   category, created_at
            FROM cgcs.email_rejection_patterns
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


async def get_rejection_insights(category: str | None = None) -> dict:
    """Aggregate rejection analytics."""
    pool = await get_pool()

    where_clause = "WHERE category = $1" if category else ""
    params: list[Any] = [category] if category else []

    # Total rejections
    total_row = await pool.fetchrow(
        f"SELECT COUNT(*) AS total FROM cgcs.email_rejection_patterns {where_clause}",
        *params,
    )
    total = total_row["total"] if total_row else 0

    # Improvement rate: % where a revision was selected (not custom)
    selected_row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(*) FILTER (WHERE selected_revision_index IS NOT NULL) AS revision_selected,
            COUNT(*) FILTER (WHERE final_draft IS NOT NULL) AS total_resolved
        FROM cgcs.email_rejection_patterns
        {where_clause}
        """,
        *params,
    )
    revision_selected = selected_row["revision_selected"] if selected_row else 0
    total_resolved = selected_row["total_resolved"] if selected_row else 0
    improvement_rate = (revision_selected / total_resolved * 100) if total_resolved > 0 else 0.0

    # Top rejection reasons
    reason_rows = await pool.fetch(
        f"""
        SELECT rejection_reason, COUNT(*) AS count
        FROM cgcs.email_rejection_patterns
        {where_clause}
        GROUP BY rejection_reason
        ORDER BY count DESC
        LIMIT 10
        """,
        *params,
    )
    top_reasons = [{"reason": r["rejection_reason"], "count": r["count"]} for r in reason_rows]

    # Category breakdown
    cat_rows = await pool.fetch(
        """
        SELECT category, COUNT(*) AS count
        FROM cgcs.email_rejection_patterns
        GROUP BY category
        ORDER BY count DESC
        """,
    )
    category_breakdown = [{"category": r["category"] or "uncategorized", "count": r["count"]} for r in cat_rows]

    return {
        "total_rejections": total,
        "improvement_rate": round(improvement_rate, 1),
        "top_reasons": top_reasons,
        "category_breakdown": category_breakdown,
    }
