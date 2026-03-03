"""Checklist queries for CGCS event compliance tracking."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from app.db.connection import get_pool
from app.db.report_queries import _compute_end_date


async def insert_checklist_items(reservation_id: UUID, items: list[dict]) -> int:
    """Bulk insert checklist items for a reservation. Returns count inserted."""
    pool = await get_pool()
    count = 0
    for item in items:
        await pool.execute(
            """
            INSERT INTO cgcs.event_checklist
                (reservation_id, item_key, item_label, required, deadline_date)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (reservation_id, item_key) DO NOTHING
            """,
            reservation_id,
            item["item_key"],
            item["item_label"],
            item.get("required", True),
            item.get("deadline_date"),
        )
        count += 1
    return count


async def get_checklist(reservation_id: UUID) -> list[dict]:
    """Fetch all checklist items for a reservation, ordered by deadline."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT *
        FROM cgcs.event_checklist
        WHERE reservation_id = $1
        ORDER BY deadline_date ASC NULLS LAST, item_key ASC
        """,
        reservation_id,
    )
    return [dict(r) for r in rows]


async def update_checklist_item(
    reservation_id: UUID,
    item_key: str,
    status: str,
    notes: str | None = None,
    completed_by: str = "admin",
) -> dict | None:
    """Update a single checklist item. Sets completed_at if status=completed."""
    pool = await get_pool()
    if status == "completed":
        row = await pool.fetchrow(
            """
            UPDATE cgcs.event_checklist
            SET status = $3,
                notes = COALESCE($4, notes),
                completed_at = NOW(),
                completed_by = $5,
                updated_at = NOW()
            WHERE reservation_id = $1 AND item_key = $2
            RETURNING *
            """,
            reservation_id,
            item_key,
            status,
            notes,
            completed_by,
        )
    else:
        row = await pool.fetchrow(
            """
            UPDATE cgcs.event_checklist
            SET status = $3,
                notes = COALESCE($4, notes),
                completed_at = NULL,
                completed_by = NULL,
                updated_at = NOW()
            WHERE reservation_id = $1 AND item_key = $2
            RETURNING *
            """,
            reservation_id,
            item_key,
            status,
            notes,
        )
    return dict(row) if row else None


async def bulk_update_checklist_items(
    reservation_id: UUID,
    items: list[dict],
) -> int:
    """Update multiple checklist items. Returns count updated."""
    count = 0
    for item in items:
        result = await update_checklist_item(
            reservation_id=reservation_id,
            item_key=item["item_key"],
            status=item["status"],
            notes=item.get("notes"),
        )
        if result:
            count += 1
    return count


async def get_checklist_items_due_soon(days_ahead: int = 7) -> list[dict]:
    """Fetch pending checklist items due within the next N days, with event info."""
    pool = await get_pool()
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    rows = await pool.fetch(
        """
        SELECT
            c.item_key, c.item_label, c.deadline_date, c.status,
            r.request_id, r.event_name, r.requester_name
        FROM cgcs.event_checklist c
        JOIN cgcs.reservations r ON c.reservation_id = r.id
        WHERE c.status = 'pending'
          AND c.deadline_date >= $1
          AND c.deadline_date <= $2
        ORDER BY c.deadline_date ASC
        """,
        today,
        cutoff,
    )
    return [dict(r) for r in rows]


async def get_compliance_report(period: str, start: date) -> dict:
    """Compliance aggregation report for a time period."""
    end = _compute_end_date(start, period)
    pool = await get_pool()

    # Overall on-time rate
    summary = await pool.fetchrow(
        """
        SELECT
            COUNT(*) AS total_items,
            COUNT(*) FILTER (WHERE c.status = 'completed') AS completed_items,
            COUNT(*) FILTER (
                WHERE c.status = 'completed'
                  AND c.completed_at::date <= c.deadline_date
            ) AS on_time_items,
            COUNT(DISTINCT c.reservation_id) FILTER (
                WHERE NOT EXISTS (
                    SELECT 1 FROM cgcs.event_checklist c2
                    WHERE c2.reservation_id = c.reservation_id
                      AND c2.required = TRUE
                      AND c2.status NOT IN ('completed', 'waived')
                )
            ) AS events_all_complete
        FROM cgcs.event_checklist c
        JOIN cgcs.reservations r ON c.reservation_id = r.id
        WHERE r.created_at >= $1 AND r.created_at < $2
        """,
        start,
        end,
    )

    total = summary["total_items"] or 0
    completed = summary["completed_items"] or 0
    on_time = summary["on_time_items"] or 0

    # Most overdue items
    overdue_rows = await pool.fetch(
        """
        SELECT
            c.item_key,
            c.item_label,
            COUNT(*) AS overdue_count,
            COALESCE(AVG(CURRENT_DATE - c.deadline_date), 0) AS avg_days_overdue
        FROM cgcs.event_checklist c
        JOIN cgcs.reservations r ON c.reservation_id = r.id
        WHERE r.created_at >= $1 AND r.created_at < $2
          AND c.status = 'pending'
          AND c.deadline_date < CURRENT_DATE
        GROUP BY c.item_key, c.item_label
        ORDER BY overdue_count DESC
        LIMIT 10
        """,
        start,
        end,
    )

    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_items": total,
        "completed_items": completed,
        "on_time_rate": round(on_time / completed * 100, 1) if completed > 0 else 0.0,
        "events_all_complete": summary["events_all_complete"] or 0,
        "most_overdue_items": [
            {
                "item_key": r["item_key"],
                "item_label": r["item_label"],
                "overdue_count": r["overdue_count"],
                "avg_days_overdue": round(float(r["avg_days_overdue"]), 1),
            }
            for r in overdue_rows
        ],
    }
