"""Impact metric rollups — Bryan's storytelling tiers.

Four-tier breakdown:
  1. Community  — everything in the space (all reservations)
  2. Monetization — revenue-generating events
  3. ACC — internal ACC events (non-CGCS)
  4. CGCS — events designed/led/co-branded by CGCS, including off-site

Each tier reports: total events, total people, total hours.
CGCS tier additionally reports training hours, on-site vs off-site split,
and attendance disaggregated by audience (students / staff / community).

YoY comparison computes the same window one year earlier.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from app.db.connection import get_pool


def _compute_end_date(start: date, period: str) -> date:
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


def _shift_year(d: date, years: int = -1) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # Feb 29 -> Feb 28 in non-leap target year.
        return d.replace(year=d.year + years, day=28)


_HOURS_EXPR = """
    EXTRACT(EPOCH FROM (requested_end_time - requested_start_time)) / 3600.0
"""


async def _tier_rollup(start: date, end: date, where_clause: str, params: list) -> dict:
    """Run the standard tier rollup with an arbitrary WHERE clause.

    `where_clause` must reference $1, $2 for [start, end] and additional
    params via $3, $4, ... matching `params`.
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT
            COUNT(*) AS total_events,
            COALESCE(SUM(COALESCE(actual_attendance, estimated_attendees, 0)), 0)
                AS total_people,
            COALESCE(SUM({_HOURS_EXPR}), 0) AS total_hours,
            COALESCE(SUM(actual_revenue), 0) AS total_revenue
        FROM cgcs.reservations
        WHERE requested_date >= $1 AND requested_date < $2
          AND status IN ('approved'::cgcs.reservation_status,
                         'completed'::cgcs.reservation_status)
          AND {where_clause}
        """,
        start, end, *params,
    )
    return {
        "total_events": int(row["total_events"] or 0),
        "total_people": int(row["total_people"] or 0),
        "total_hours": round(float(row["total_hours"] or 0), 1),
        "total_revenue": float(row["total_revenue"] or 0),
    }


async def _community_tier(start: date, end: date) -> dict:
    return await _tier_rollup(start, end, "TRUE", [])


async def _monetization_tier(start: date, end: date) -> dict:
    return await _tier_rollup(
        start, end,
        "event_category = 'monetization'::cgcs.event_category",
        [],
    )


async def _acc_tier(start: date, end: date) -> dict:
    return await _tier_rollup(
        start, end,
        "event_category = 'acc'::cgcs.event_category",
        [],
    )


async def _cgcs_tier(start: date, end: date) -> dict:
    """CGCS tier with extras: training hours, on/off-site, audience split."""
    base = await _tier_rollup(
        start, end,
        "event_category = 'cgcs'::cgcs.event_category",
        [],
    )

    pool = await get_pool()
    extras = await pool.fetchrow(
        f"""
        SELECT
            COALESCE(SUM(training_hours_delivered), 0) AS training_hours,
            COALESCE(SUM({_HOURS_EXPR})
                FILTER (WHERE event_location = 'on_site'::cgcs.event_location), 0)
                AS on_site_hours,
            COALESCE(SUM({_HOURS_EXPR})
                FILTER (WHERE event_location = 'off_site'::cgcs.event_location), 0)
                AS off_site_hours,
            COUNT(*) FILTER (WHERE event_location = 'on_site'::cgcs.event_location)
                AS on_site_events,
            COUNT(*) FILTER (WHERE event_location = 'off_site'::cgcs.event_location)
                AS off_site_events,
            COUNT(*) FILTER (WHERE event_subtype = 'training'::cgcs.event_subtype)
                AS training_events,
            COALESCE(SUM(attendance_students), 0) AS students,
            COALESCE(SUM(attendance_staff), 0) AS staff,
            COALESCE(SUM(attendance_community), 0) AS community
        FROM cgcs.reservations
        WHERE requested_date >= $1 AND requested_date < $2
          AND status IN ('approved'::cgcs.reservation_status,
                         'completed'::cgcs.reservation_status)
          AND event_category = 'cgcs'::cgcs.event_category
        """,
        start, end,
    )

    base["training_hours"] = round(float(extras["training_hours"] or 0), 1)
    base["training_events"] = int(extras["training_events"] or 0)
    base["on_site_events"] = int(extras["on_site_events"] or 0)
    base["off_site_events"] = int(extras["off_site_events"] or 0)
    base["on_site_hours"] = round(float(extras["on_site_hours"] or 0), 1)
    base["off_site_hours"] = round(float(extras["off_site_hours"] or 0), 1)
    base["audience"] = {
        "students": int(extras["students"] or 0),
        "staff": int(extras["staff"] or 0),
        "community": int(extras["community"] or 0),
    }
    return base


async def get_impact_report(period: str, start: date) -> dict:
    """Four-tier impact rollup with year-over-year comparison."""
    end = _compute_end_date(start, period)
    prev_start = _shift_year(start)
    prev_end = _shift_year(end)

    community = await _community_tier(start, end)
    monetization = await _monetization_tier(start, end)
    acc = await _acc_tier(start, end)
    cgcs = await _cgcs_tier(start, end)

    prev_community = await _community_tier(prev_start, prev_end)
    prev_monetization = await _monetization_tier(prev_start, prev_end)
    prev_acc = await _acc_tier(prev_start, prev_end)
    prev_cgcs = await _cgcs_tier(prev_start, prev_end)

    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "current": {
            "community": community,
            "monetization": monetization,
            "acc": acc,
            "cgcs": cgcs,
        },
        "previous_year": {
            "start": prev_start.isoformat(),
            "end": prev_end.isoformat(),
            "community": prev_community,
            "monetization": prev_monetization,
            "acc": prev_acc,
            "cgcs": prev_cgcs,
        },
    }


# --- Manual off-site CGCS event entry -------------------------------------

async def create_manual_event(
    request_id: str,
    event_name: str,
    requested_date: date,
    requested_start_time,
    requested_end_time,
    requester_name: str = "CGCS",
    requester_email: str = "admin@cgcs-acc.org",
    requester_organization: str | None = "CGCS",
    estimated_attendees: int | None = None,
    actual_attendance: int | None = None,
    actual_revenue: float | None = None,
    event_subtype: str | None = None,
    event_location: str = "off_site",
    attendance_students: int | None = None,
    attendance_staff: int | None = None,
    attendance_community: int | None = None,
    training_hours_delivered: float | None = None,
    notes: str | None = None,
) -> dict:
    """Insert a manually-entered CGCS event (typically off-site).

    Goes straight to status='completed' since manual entries are after the
    fact. Bypasses the intake workflow entirely — these are CGCS-led events
    captured for impact metrics.
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cgcs.reservations (
            request_id, requester_name, requester_email, requester_organization,
            event_name, event_description,
            requested_date, requested_start_time, requested_end_time,
            estimated_attendees, actual_attendance, actual_revenue,
            event_category, event_subtype, event_location,
            attendance_students, attendance_staff, attendance_community,
            training_hours_delivered,
            status, source, completed_at
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
            'cgcs'::cgcs.event_category,
            $13::cgcs.event_subtype,
            $14::cgcs.event_location,
            $15, $16, $17, $18,
            'completed'::cgcs.reservation_status, 'manual', NOW()
        )
        RETURNING id, request_id, event_name, requested_date,
                  event_category, event_subtype, event_location, source
        """,
        request_id, requester_name, requester_email, requester_organization,
        event_name, notes,
        requested_date, requested_start_time, requested_end_time,
        estimated_attendees, actual_attendance, actual_revenue,
        event_subtype, event_location,
        attendance_students, attendance_staff, attendance_community,
        training_hours_delivered,
    )
    return dict(row) if row else {}
