"""
Queries for the Fogg Ledger budget data — used by /api/v1/budget endpoints and
the dashboard's /budget + updated Impact homepage.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any

from app.db.connection import get_pool


TXN_SORTABLE = {
    "date": "transaction_date",
    "description": "description",
    "category": "category",
    "expense": "expense",
    "revenue": "revenue",
    "balance": "running_balance",
}


async def get_fiscal_year(fy_label: str | None = None) -> dict | None:
    """Return one fiscal year row. If fy_label is None, return the current FY."""
    pool = await get_pool()
    if fy_label:
        row = await pool.fetchrow(
            "SELECT * FROM cgcs.fiscal_years WHERE fy_label = $1", fy_label
        )
    else:
        row = await pool.fetchrow(
            "SELECT * FROM cgcs.fiscal_years WHERE is_current = TRUE LIMIT 1"
        )
    return dict(row) if row else None


async def list_fiscal_years() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT * FROM cgcs.fiscal_years ORDER BY start_date DESC"
    )
    return [dict(r) for r in rows]


async def get_category_rollup(fy_label: str, exclude_holds: bool = True) -> list[dict]:
    """Per-category expense/revenue/net for one FY."""
    pool = await get_pool()
    where = "fy_label = $1"
    if exclude_holds:
        # Skip rows whose source_tag or notes mark them as TBD / HOLD.
        where += " AND (notes IS NULL OR notes NOT ILIKE 'HOLD%')"
    rows = await pool.fetch(f"""
        SELECT category,
               COUNT(*) AS row_count,
               COALESCE(SUM(expense), 0)::numeric(12,2) AS expense_total,
               COALESCE(SUM(revenue), 0)::numeric(12,2) AS revenue_total,
               (COALESCE(SUM(revenue), 0) - COALESCE(SUM(expense), 0))::numeric(12,2) AS net
          FROM cgcs.ledger_transactions
         WHERE {where} AND category IS NOT NULL
         GROUP BY category
         ORDER BY expense_total DESC NULLS LAST
    """, fy_label)
    return [dict(r) for r in rows]


def _money(v) -> float:
    if v is None: return 0.0
    return float(v)


def _burn_rate(current_balance: float, end_date: date, today: date | None = None) -> dict:
    """Days/weeks/months remaining and even-spend allowance."""
    today = today or date.today()
    days_left = max((end_date - today).days, 0)
    weeks_left = round(days_left / 7, 1)
    months_left = round(days_left / 30.42, 1)  # average month length
    return {
        "days_left": days_left,
        "weeks_left": weeks_left,
        "months_left": months_left,
        "per_day": round(current_balance / days_left, 2) if days_left else 0.0,
        "per_week": round(current_balance / weeks_left, 2) if weeks_left else 0.0,
        "per_month": round(current_balance / months_left, 2) if months_left else 0.0,
    }


async def get_budget_summary(fy_label: str | None = None) -> dict[str, Any]:
    """Everything the /budget dashboard page needs: balance, burn rate, totals,
    category rollup, recent transactions, FY metadata."""
    fy = await get_fiscal_year(fy_label)
    if not fy:
        return {"error": f"No fiscal year found for label {fy_label!r}"}

    label = fy["fy_label"]
    pool = await get_pool()

    totals = await pool.fetchrow("""
        SELECT
            COALESCE(SUM(expense), 0)::numeric(12,2) AS total_expense,
            COALESCE(SUM(revenue), 0)::numeric(12,2) AS total_revenue,
            COALESCE(SUM(expense) FILTER (WHERE category = 'Wage'), 0)::numeric(12,2) AS wage_expense,
            COALESCE(SUM(expense) FILTER (WHERE category <> 'Wage'), 0)::numeric(12,2) AS non_wage_expense,
            COUNT(*) AS txn_count
          FROM cgcs.ledger_transactions
         WHERE fy_label = $1
           AND (notes IS NULL OR notes NOT ILIKE 'HOLD%')
    """, label)

    starting = _money(fy["starting_balance"])
    expense = _money(totals["total_expense"])
    revenue = _money(totals["total_revenue"])
    # Per the spreadsheet's model: revenue earned is a carry-forward to next
    # FY, not added back to the current operating balance. So:
    current_balance = starting - expense

    burn = _burn_rate(current_balance, fy["end_date"])
    categories = await get_category_rollup(label)

    recent = await pool.fetch("""
        SELECT id, transaction_date, description, category, payment_method,
               expense, revenue, running_balance, linked_reservation_id, notes
          FROM cgcs.ledger_transactions
         WHERE fy_label = $1
         ORDER BY transaction_date DESC NULLS LAST, created_at DESC
         LIMIT 10
    """, label)

    return {
        "fiscal_year": {
            "label": label,
            "start_date": fy["start_date"].isoformat(),
            "end_date": fy["end_date"].isoformat(),
            "starting_balance": starting,
            "holdover_to_next": _money(fy["holdover_to_next"]),
        },
        "totals": {
            "expense": expense,
            "revenue": revenue,
            "wage_expense": _money(totals["wage_expense"]),
            "non_wage_expense": _money(totals["non_wage_expense"]),
            "current_balance": round(current_balance, 2),
            "txn_count": totals["txn_count"],
        },
        "burn_rate": burn,
        "categories": [
            {
                "category": r["category"],
                "row_count": r["row_count"],
                "expense_total": _money(r["expense_total"]),
                "revenue_total": _money(r["revenue_total"]),
                "net": _money(r["net"]),
            }
            for r in categories
        ],
        "recent_transactions": [
            {
                "id": str(r["id"]),
                "date": r["transaction_date"].isoformat() if r["transaction_date"] else None,
                "description": r["description"],
                "category": r["category"],
                "payment_method": r["payment_method"],
                "expense": _money(r["expense"]),
                "revenue": _money(r["revenue"]),
                "running_balance": _money(r["running_balance"]),
                "linked_reservation_id": str(r["linked_reservation_id"]) if r["linked_reservation_id"] else None,
                "notes": r["notes"],
            }
            for r in recent
        ],
    }


async def list_transactions(
    fy_label: str | None = None,
    category: str | None = None,
    sort: str | None = None,
    direction: str = "desc",
    limit: int = 500,
) -> list[dict]:
    pool = await get_pool()
    if not fy_label:
        fy = await get_fiscal_year()
        if fy: fy_label = fy["fy_label"]
    column = TXN_SORTABLE.get((sort or "").lower(), "transaction_date")
    dir_sql = "ASC" if direction.lower() == "asc" else "DESC"

    where_parts: list[str] = []
    args: list[Any] = [limit]
    if fy_label:
        args.append(fy_label)
        where_parts.append(f"fy_label = ${len(args)}")
    if category:
        args.append(category)
        where_parts.append(f"category = ${len(args)}")
    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    rows = await pool.fetch(f"""
        SELECT id, fy_label, transaction_date, description, category, payment_method,
               expense, revenue, running_balance, transfer_required, transfer_confirmed,
               notes, source_tag, linked_reservation_id, created_at
          FROM cgcs.ledger_transactions
          {where_sql}
         ORDER BY {column} {dir_sql} NULLS LAST, created_at DESC
         LIMIT $1
    """, *args)
    return [dict(r) for r in rows]
