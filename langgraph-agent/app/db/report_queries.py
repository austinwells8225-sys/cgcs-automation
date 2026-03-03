"""Reporting and revenue tracking queries for CGCS reservations."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from app.db.connection import get_pool


async def complete_reservation(
    request_id: str,
    actual_revenue: float | None = None,
    actual_attendance: int | None = None,
    event_department: str | None = None,
) -> dict | None:
    """Mark an approved reservation as completed and record actuals."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE cgcs.reservations
        SET status = 'completed'::cgcs.reservation_status,
            actual_revenue = $2,
            actual_attendance = $3,
            event_department = $4,
            completed_at = NOW(),
            updated_at = NOW()
        WHERE request_id = $1 AND status = 'approved'::cgcs.reservation_status
        RETURNING *
        """,
        request_id,
        actual_revenue,
        actual_attendance,
        event_department,
    )
    return dict(row) if row else None


def _compute_end_date(start: date, period: str) -> date:
    """Compute the end date for a reporting period."""
    if period == "week":
        return start + timedelta(days=7)

    months_to_add = {"month": 1, "quarter": 3, "year": 12}.get(period, 1)
    month = start.month + months_to_add
    year = start.year
    while month > 12:
        month -= 12
        year += 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(start.day, max_day)
    return date(year, month, day)


async def get_revenue_report(period: str, start: date) -> dict:
    """Revenue aggregations for a time period."""
    end = _compute_end_date(start, period)
    pool = await get_pool()

    summary = await pool.fetchrow(
        """
        SELECT
            COUNT(*) AS total_events,
            COALESCE(SUM(actual_revenue), 0) AS total_revenue,
            COALESCE(AVG(actual_revenue), 0) AS avg_revenue,
            COALESCE(SUM(actual_attendance), 0) AS total_attendance,
            COALESCE(AVG(actual_attendance), 0) AS avg_attendance
        FROM cgcs.reservations
        WHERE status = 'completed'::cgcs.reservation_status
          AND completed_at >= $1 AND completed_at < $2
        """,
        start,
        end,
    )

    breakdown = await pool.fetch(
        """
        SELECT
            CASE
                WHEN event_name LIKE 'A-EVENT%' THEN 'A-EVENT'
                WHEN event_name LIKE 'C-EVENT%' THEN 'C-EVENT'
                WHEN event_name LIKE 'S-EVENT%' THEN 'S-EVENT'
                ELSE 'OTHER'
            END AS event_type,
            COUNT(*) AS event_count,
            COALESCE(SUM(actual_revenue), 0) AS revenue,
            COALESCE(SUM(actual_attendance), 0) AS attendance
        FROM cgcs.reservations
        WHERE status = 'completed'::cgcs.reservation_status
          AND completed_at >= $1 AND completed_at < $2
        GROUP BY event_type
        ORDER BY revenue DESC
        """,
        start,
        end,
    )

    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_events": summary["total_events"],
        "total_revenue": float(summary["total_revenue"]),
        "avg_revenue": float(summary["avg_revenue"]),
        "total_attendance": int(summary["total_attendance"]),
        "avg_attendance": float(summary["avg_attendance"]),
        "breakdown_by_type": [dict(r) for r in breakdown],
    }


async def get_conversion_funnel(period: str, start: date) -> dict:
    """Conversion funnel: counts at each stage and conversion rates."""
    end = _compute_end_date(start, period)
    pool = await get_pool()

    row = await pool.fetchrow(
        """
        SELECT
            COUNT(*) AS total_submitted,
            COUNT(*) FILTER (WHERE status IN ('approved', 'completed')) AS approved,
            COUNT(*) FILTER (WHERE status = 'completed'::cgcs.reservation_status) AS completed,
            COUNT(*) FILTER (WHERE status = 'rejected'::cgcs.reservation_status) AS rejected,
            COUNT(*) FILTER (WHERE status = 'cancelled'::cgcs.reservation_status) AS cancelled,
            COUNT(*) FILTER (WHERE status = 'pending_review'::cgcs.reservation_status) AS pending
        FROM cgcs.reservations
        WHERE created_at >= $1 AND created_at < $2
        """,
        start,
        end,
    )

    total = row["total_submitted"] or 0
    approved = row["approved"] or 0
    completed = row["completed"] or 0

    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_submitted": total,
        "pending": row["pending"],
        "approved": approved,
        "completed": completed,
        "rejected": row["rejected"],
        "cancelled": row["cancelled"],
        "approval_rate": round(approved / total * 100, 1) if total > 0 else 0.0,
        "completion_rate": round(completed / total * 100, 1) if total > 0 else 0.0,
    }


async def get_reservations_for_export(period: str, start: date) -> list[dict]:
    """Fetch all reservations in the period for CSV export."""
    end = _compute_end_date(start, period)
    pool = await get_pool()

    rows = await pool.fetch(
        """
        SELECT
            request_id, requester_name, requester_email, requester_organization,
            event_name, requested_date, requested_start_time, requested_end_time,
            room_requested, estimated_attendees, pricing_tier, estimated_cost,
            status, actual_revenue, actual_attendance, event_department,
            created_at, completed_at, cancelled_at
        FROM cgcs.reservations
        WHERE created_at >= $1 AND created_at < $2
        ORDER BY created_at ASC
        """,
        start,
        end,
    )
    return [dict(r) for r in rows]


async def get_top_organizations(period: str, start: date, limit: int = 10) -> list[dict]:
    """Top organizations by booking count within a period."""
    end = _compute_end_date(start, period)
    pool = await get_pool()

    rows = await pool.fetch(
        """
        SELECT
            COALESCE(requester_organization, 'Unknown') AS organization,
            COUNT(*) AS total_bookings,
            COUNT(*) FILTER (WHERE status = 'completed'::cgcs.reservation_status) AS completed_bookings,
            COALESCE(SUM(actual_revenue), 0) AS total_revenue,
            COALESCE(SUM(actual_attendance), 0) AS total_attendance
        FROM cgcs.reservations
        WHERE created_at >= $1 AND created_at < $2
        GROUP BY requester_organization
        ORDER BY total_bookings DESC
        LIMIT $3
        """,
        start,
        end,
        limit,
    )
    return [dict(r) for r in rows]
