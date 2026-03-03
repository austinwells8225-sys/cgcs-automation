"""Process insights — analytics layer over existing CGCS data."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from app.db.connection import get_pool
from app.db.report_queries import (
    get_revenue_report,
    get_top_organizations,
)
from app.graph.nodes.shared import _invoke_with_retry, _parse_json_response

logger = logging.getLogger(__name__)

RECOMMENDATIONS_SYSTEM_PROMPT = """\
You are a process improvement analyst for CGCS event operations at Austin \
Community College. Given these operational metrics, generate 3-5 specific, \
actionable recommendations for improving the intake process.

Be concrete and reference specific numbers from the data. Focus on:
- Reducing turnaround times
- Improving email draft quality (reducing rejections)
- Streamlining the quote process
- Ensuring compliance deadlines are met
- Increasing conversion rates

Respond with ONLY valid JSON:
{"recommendations": ["recommendation 1", "recommendation 2", ...]}
"""


async def get_email_metrics(start_date: date, end_date: date) -> dict:
    """Email drafting performance: rejection rates and trends."""
    pool = await get_pool()

    summary = await pool.fetchrow(
        """
        SELECT
            COUNT(*) AS total_drafts,
            COUNT(*) FILTER (WHERE status = 'rejected') AS rejected_count
        FROM cgcs.email_tasks
        WHERE created_at >= $1 AND created_at < $2
        """,
        start_date,
        end_date,
    )

    total = summary["total_drafts"] or 0
    rejected = summary["rejected_count"] or 0

    # Average revisions per rejected email
    rev_row = await pool.fetchrow(
        """
        SELECT COALESCE(AVG(
            CASE WHEN selected_revision_index IS NOT NULL THEN 1 ELSE 0 END + 1
        ), 0) AS avg_revisions
        FROM cgcs.email_rejection_patterns
        WHERE created_at >= $1 AND created_at < $2
        """,
        start_date,
        end_date,
    )

    # Top rejection reasons by category
    reason_rows = await pool.fetch(
        """
        SELECT category, COUNT(*) AS count
        FROM cgcs.email_rejection_patterns
        WHERE created_at >= $1 AND created_at < $2
          AND category IS NOT NULL
        GROUP BY category
        ORDER BY count DESC
        LIMIT 5
        """,
        start_date,
        end_date,
    )

    # Improvement trend: first half vs second half rejection rate
    midpoint = start_date + (end_date - start_date) / 2
    trend_row = await pool.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE created_at < $3) AS first_half_total,
            COUNT(*) FILTER (WHERE created_at < $3 AND status = 'rejected') AS first_half_rejected,
            COUNT(*) FILTER (WHERE created_at >= $3) AS second_half_total,
            COUNT(*) FILTER (WHERE created_at >= $3 AND status = 'rejected') AS second_half_rejected
        FROM cgcs.email_tasks
        WHERE created_at >= $1 AND created_at < $2
        """,
        start_date,
        end_date,
        midpoint,
    )

    fh_total = trend_row["first_half_total"] or 0
    fh_rejected = trend_row["first_half_rejected"] or 0
    sh_total = trend_row["second_half_total"] or 0
    sh_rejected = trend_row["second_half_rejected"] or 0

    return {
        "total_drafts": total,
        "rejection_rate": round(rejected / total * 100, 1) if total > 0 else 0.0,
        "avg_revisions_per_email": round(float(rev_row["avg_revisions"]), 2),
        "top_rejection_reasons": [
            {"category": r["category"], "count": r["count"]} for r in reason_rows
        ],
        "improvement_trend": {
            "first_half_rejection_rate": round(fh_rejected / fh_total * 100, 1) if fh_total > 0 else 0.0,
            "second_half_rejection_rate": round(sh_rejected / sh_total * 100, 1) if sh_total > 0 else 0.0,
        },
    }


async def get_quote_metrics(start_date: date, end_date: date) -> dict:
    """Quote versioning stats: revision frequency, popular add-ons."""
    pool = await get_pool()

    summary = await pool.fetchrow(
        """
        SELECT
            COUNT(DISTINCT qv.reservation_id) AS total_quotes,
            COALESCE(AVG(qv.max_ver), 0) AS avg_revisions
        FROM (
            SELECT reservation_id, MAX(version) AS max_ver
            FROM cgcs.quote_versions qv2
            JOIN cgcs.reservations r ON qv2.reservation_id = r.id
            WHERE r.created_at >= $1 AND r.created_at < $2
            GROUP BY reservation_id
        ) qv
        """,
        start_date,
        end_date,
    )

    # Most added service from changes_from_previous
    service_rows = await pool.fetch(
        """
        SELECT elem->>'service' AS service, COUNT(*) AS add_count
        FROM cgcs.quote_versions qv
        JOIN cgcs.reservations r ON qv.reservation_id = r.id,
             jsonb_array_elements(
                 COALESCE(qv.changes_from_previous->'added', '[]'::jsonb)
             ) AS elem
        WHERE r.created_at >= $1 AND r.created_at < $2
          AND qv.changes_from_previous IS NOT NULL
        GROUP BY elem->>'service'
        ORDER BY add_count DESC
        LIMIT 1
        """,
        start_date,
        end_date,
    )

    # Average quote increase percentage (v1 total vs latest total)
    increase_row = await pool.fetchrow(
        """
        SELECT COALESCE(AVG(
            CASE WHEN first_total > 0
                 THEN ((latest_total - first_total) / first_total) * 100
                 ELSE 0
            END
        ), 0) AS avg_increase_pct
        FROM (
            SELECT
                reservation_id,
                (SELECT total FROM cgcs.quote_versions
                 WHERE reservation_id = qv.reservation_id AND version = 1) AS first_total,
                (SELECT total FROM cgcs.quote_versions
                 WHERE reservation_id = qv.reservation_id
                 ORDER BY version DESC LIMIT 1) AS latest_total
            FROM (
                SELECT DISTINCT reservation_id
                FROM cgcs.quote_versions qv2
                JOIN cgcs.reservations r ON qv2.reservation_id = r.id
                WHERE r.created_at >= $1 AND r.created_at < $2
            ) qv
        ) sub
        WHERE latest_total IS NOT NULL AND first_total IS NOT NULL
        """,
        start_date,
        end_date,
    )

    return {
        "total_quotes": summary["total_quotes"] or 0,
        "avg_revisions_per_quote": round(float(summary["avg_revisions"]), 2),
        "most_added_service": service_rows[0]["service"] if service_rows else None,
        "avg_quote_increase_pct": round(float(increase_row["avg_increase_pct"]), 1),
    }


async def get_turnaround_metrics(start_date: date, end_date: date) -> dict:
    """Processing speed: intake to response, approval, and event."""
    pool = await get_pool()

    row = await pool.fetchrow(
        """
        SELECT
            COALESCE(AVG(
                EXTRACT(EPOCH FROM (first_action - r.created_at)) / 3600
            ), 0) AS avg_intake_to_response_hours,
            COALESCE(AVG(
                EXTRACT(EPOCH FROM (r.admin_approved_at - r.created_at)) / 86400
            ), 0) AS avg_intake_to_approval_days,
            COALESCE(AVG(
                r.requested_date - r.created_at::date
            ), 0) AS avg_intake_to_event_days
        FROM cgcs.reservations r
        LEFT JOIN LATERAL (
            SELECT MIN(a.created_at) AS first_action
            FROM cgcs.audit_trail a
            WHERE a.reservation_id = r.id
              AND a.actor != 'system'
        ) fa ON TRUE
        WHERE r.created_at >= $1 AND r.created_at < $2
        """,
        start_date,
        end_date,
    )

    return {
        "avg_intake_to_response_hours": round(float(row["avg_intake_to_response_hours"]), 1),
        "avg_intake_to_approval_days": round(float(row["avg_intake_to_approval_days"]), 1),
        "avg_intake_to_event_days": round(float(row["avg_intake_to_event_days"]), 1),
    }


async def get_compliance_metrics(start_date: date, end_date: date) -> dict:
    """Checklist compliance: on-time rates, overdue patterns."""
    pool = await get_pool()

    summary = await pool.fetchrow(
        """
        SELECT
            COUNT(*) AS total_items,
            COUNT(*) FILTER (
                WHERE c.status = 'completed'
                  AND c.completed_at::date <= c.deadline_date
            ) AS on_time_items,
            COUNT(*) FILTER (WHERE c.status = 'completed') AS completed_items,
            COUNT(*) FILTER (
                WHERE c.status = 'pending'
                  AND c.deadline_date < CURRENT_DATE
                  AND r.requested_date < CURRENT_DATE
            ) AS items_never_completed
        FROM cgcs.event_checklist c
        JOIN cgcs.reservations r ON c.reservation_id = r.id
        WHERE r.created_at >= $1 AND r.created_at < $2
        """,
        start_date,
        end_date,
    )

    total = summary["total_items"] or 0
    on_time = summary["on_time_items"] or 0

    # Most overdue items by item_key
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
        start_date,
        end_date,
    )

    return {
        "on_time_rate": round(on_time / total * 100, 1) if total > 0 else 0.0,
        "most_overdue_items": [
            {
                "item_key": r["item_key"],
                "item_label": r["item_label"],
                "overdue_count": r["overdue_count"],
                "avg_days_overdue": round(float(r["avg_days_overdue"]), 1),
            }
            for r in overdue_rows
        ],
        "avg_overdue_days_per_item": [
            {
                "item_key": r["item_key"],
                "avg_days": round(float(r["avg_days_overdue"]), 1),
            }
            for r in overdue_rows
        ],
        "items_never_completed": summary["items_never_completed"] or 0,
    }


async def get_conversion_funnel_metrics(start_date: date, end_date: date) -> dict:
    """Reservation conversion funnel."""
    pool = await get_pool()

    row = await pool.fetchrow(
        """
        SELECT
            COUNT(*) AS submitted,
            COUNT(*) FILTER (WHERE status IN ('approved', 'completed')) AS approved,
            COUNT(*) FILTER (WHERE status = 'completed'::cgcs.reservation_status) AS completed,
            COUNT(*) FILTER (WHERE status = 'cancelled'::cgcs.reservation_status) AS cancelled,
            COUNT(*) FILTER (WHERE status = 'rejected'::cgcs.reservation_status) AS rejected
        FROM cgcs.reservations
        WHERE created_at >= $1 AND created_at < $2
        """,
        start_date,
        end_date,
    )

    submitted = row["submitted"] or 0
    completed = row["completed"] or 0

    return {
        "submitted": submitted,
        "approved": row["approved"] or 0,
        "completed": completed,
        "cancelled": row["cancelled"] or 0,
        "rejected": row["rejected"] or 0,
        "conversion_rate": round(completed / submitted * 100, 1) if submitted > 0 else 0.0,
    }


def generate_recommendations(all_metrics: dict) -> list[str]:
    """Use Claude to generate actionable process improvement recommendations."""
    # Check if metrics are mostly empty (first quarter scenario)
    has_data = (
        all_metrics.get("email", {}).get("total_drafts", 0) > 0
        or all_metrics.get("conversion", {}).get("submitted", 0) > 0
        or all_metrics.get("compliance", {}).get("on_time_rate", 0) > 0
    )

    if not has_data:
        return [
            "Insufficient data for detailed recommendations. Continue collecting operational data.",
            "Ensure all event requests are processed through the intake system to build a baseline.",
            "Review checklist deadlines to confirm they align with actual operational timelines.",
        ]

    metrics_summary = json.dumps(all_metrics, indent=2, default=str)
    try:
        content = _invoke_with_retry([
            {"role": "system", "content": RECOMMENDATIONS_SYSTEM_PROMPT},
            {"role": "user", "content": f"Here are the operational metrics:\n\n{metrics_summary}"},
        ])
        result = _parse_json_response(content)
        recommendations = result.get("recommendations", [])
        if isinstance(recommendations, list) and len(recommendations) > 0:
            return recommendations[:5]
    except Exception:
        logger.exception("Failed to generate AI recommendations")

    return [
        "Review email draft rejection patterns to improve initial draft quality.",
        "Monitor turnaround times and set internal SLAs for intake processing.",
        "Ensure compliance checklists are completed before event deadlines.",
    ]


async def build_quarterly_report(quarter_start: date) -> dict:
    """Build a comprehensive quarterly report combining all metrics."""
    # Compute quarter end (3 months later)
    month = quarter_start.month + 3
    year = quarter_start.year
    while month > 12:
        month -= 12
        year += 1
    end_date = date(year, month, 1)

    period_str = "quarter"
    start_str = quarter_start.isoformat()
    end_str = end_date.isoformat()

    # Gather all metrics (continueOnFail for each)
    email = {}
    try:
        email = await get_email_metrics(quarter_start, end_date)
    except Exception:
        logger.exception("Email metrics failed")

    quotes = {}
    try:
        quotes = await get_quote_metrics(quarter_start, end_date)
    except Exception:
        logger.exception("Quote metrics failed")

    turnaround = {}
    try:
        turnaround = await get_turnaround_metrics(quarter_start, end_date)
    except Exception:
        logger.exception("Turnaround metrics failed")

    compliance = {}
    try:
        compliance = await get_compliance_metrics(quarter_start, end_date)
    except Exception:
        logger.exception("Compliance metrics failed")

    conversion = {}
    try:
        conversion = await get_conversion_funnel_metrics(quarter_start, end_date)
    except Exception:
        logger.exception("Conversion funnel metrics failed")

    revenue = {}
    try:
        revenue = await get_revenue_report(period_str, quarter_start)
    except Exception:
        logger.exception("Revenue report failed")

    top_orgs = []
    try:
        top_orgs = await get_top_organizations(period_str, quarter_start, limit=10)
    except Exception:
        logger.exception("Top organizations failed")

    # Generate AI recommendations
    all_metrics = {
        "email": email,
        "quotes": quotes,
        "turnaround": turnaround,
        "compliance": compliance,
        "conversion": conversion,
        "revenue": revenue,
    }
    recommendations = generate_recommendations(all_metrics)

    return {
        "period": period_str,
        "start": start_str,
        "end": end_str,
        "email": email,
        "quotes": quotes,
        "turnaround": turnaround,
        "compliance": compliance,
        "conversion": conversion,
        "revenue": revenue,
        "top_organizations": top_orgs,
        "recommendations": recommendations,
    }


async def get_monthly_quick_stats(month_start: date) -> dict:
    """Lightweight monthly stats for the daily digest."""
    # Compute month end
    if month_start.month == 12:
        month_end = date(month_start.year + 1, 1, 1)
    else:
        month_end = date(month_start.year, month_start.month + 1, 1)

    pool = await get_pool()

    row = await pool.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE status IN ('approved', 'completed', 'pending_review')
            ) AS events_this_month,
            COALESCE(SUM(actual_revenue) FILTER (
                WHERE status = 'completed'::cgcs.reservation_status
            ), 0) AS revenue_this_month,
            COUNT(*) FILTER (
                WHERE status = 'pending_review'::cgcs.reservation_status
            ) AS pending_approvals
        FROM cgcs.reservations
        WHERE created_at >= $1 AND created_at < $2
        """,
        month_start,
        month_end,
    )

    # On-time checklist rate
    checklist_row = await pool.fetchrow(
        """
        SELECT
            COUNT(*) AS total_items,
            COUNT(*) FILTER (
                WHERE c.status = 'completed'
                  AND c.completed_at::date <= c.deadline_date
            ) AS on_time_items
        FROM cgcs.event_checklist c
        JOIN cgcs.reservations r ON c.reservation_id = r.id
        WHERE r.created_at >= $1 AND r.created_at < $2
          AND c.deadline_date IS NOT NULL
        """,
        month_start,
        month_end,
    )

    cl_total = checklist_row["total_items"] or 0
    cl_on_time = checklist_row["on_time_items"] or 0

    return {
        "events_this_month": row["events_this_month"] or 0,
        "revenue_this_month": float(row["revenue_this_month"]),
        "pending_approvals": row["pending_approvals"] or 0,
        "on_time_checklist_rate": round(cl_on_time / cl_total * 100, 1) if cl_total > 0 else 0.0,
    }
