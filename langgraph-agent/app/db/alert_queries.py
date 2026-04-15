"""Dashboard alert queries for CGCS automation."""

from __future__ import annotations

from uuid import UUID

from app.db.connection import get_pool


async def create_alert(
    alert_type: str,
    title: str,
    detail: str | None = None,
    reservation_id: UUID | None = None,
) -> str:
    """Insert a new dashboard alert. Returns the alert ID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.dashboard_alerts
            (reservation_id, alert_type, title, detail)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        reservation_id,
        alert_type,
        title,
        detail,
    )
    return str(row["id"])


async def get_active_alerts() -> list[dict]:
    """Fetch all active (non-dismissed) dashboard alerts."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, reservation_id, alert_type, title, detail, status, created_at
        FROM cgcs.dashboard_alerts
        WHERE status = 'active'
        ORDER BY created_at DESC
        """
    )
    return [dict(r) for r in rows]


async def dismiss_alert(alert_id: str) -> bool:
    """Mark a dashboard alert as dismissed. Returns True if found and updated."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE cgcs.dashboard_alerts
        SET status = 'dismissed'
        WHERE id = $1 AND status = 'active'
        """,
        alert_id if not isinstance(alert_id, UUID) else alert_id,
    )
    return result == "UPDATE 1"
