#!/usr/bin/env python3
"""
Import the Fogg Ledger budget CSV (FY 2025-2026 tab) into cgcs.ledger_transactions
and seed cgcs.fiscal_years. Tries to link each Event Income / Event Expense row
to a matching reservation by description ~ event_name.

Idempotent: clears the FY's existing rows on each run before re-inserting, so
edits in the source spreadsheet propagate cleanly on re-run.
"""
from __future__ import annotations
import csv, re, subprocess, sys
from decimal import Decimal, InvalidOperation
from typing import Any

LEDGER_CSV = "/Users/a2068129/Downloads/Fogg Ledger - Budget - Active - 2026-05-18   - FY 2025-2026 Ledger.csv"
DASHBOARD_CSV = "/Users/a2068129/Downloads/Fogg Ledger - Budget - Active - 2026-05-18   - Dashboard.csv"

FY_LABEL = "FY 2025-2026"
FY_START = "2025-09-01"
FY_END = "2026-08-31"


def money(s: str) -> Decimal | None:
    if s is None: return None
    s = s.strip()
    if not s or s == "-" or s == "—":
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").strip()
    if not s: return None
    try:
        v = Decimal(s)
        return -v if neg else v
    except InvalidOperation:
        return None


def bool_yn(s: str) -> bool | None:
    if not s: return None
    s = s.strip().lower()
    if s in ("yes", "y", "true"): return True
    if s in ("no", "n", "false"): return False
    return None


def sql_lit(v: Any) -> str:
    if v is None: return "NULL"
    if isinstance(v, bool): return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float, Decimal)): return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def parse_ledger(path: str) -> tuple[dict, list[dict]]:
    """Return (fy_meta, transactions)."""
    with open(path) as f:
        rows = list(csv.reader(f))

    fy_meta = {
        "fy_label": FY_LABEL,
        "start_date": FY_START,
        "end_date": FY_END,
        "starting_balance": None,
        "holdover_to_next": None,
        "is_current": True,
        "notes": None,
    }
    transactions: list[dict] = []

    # Header row index — find "Date,Description,Category,...".
    header_idx = None
    for i, r in enumerate(rows):
        if r and r[0].strip().lower() == "date":
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError("Could not find header row in ledger CSV")

    # Pull starting balance — sits a couple rows above the header.
    for r in rows[: header_idx]:
        if r and r[0].strip().lower() == "starting balance":
            # Starting Balance is in col G (index 6) per the spreadsheet
            for cell in r[6:]:
                v = money(cell)
                if v is not None:
                    fy_meta["starting_balance"] = v
                    break
            break

    # Data rows: from header_idx+1 until first blank or "TOTALS" row.
    for r in rows[header_idx + 1:]:
        if not r or not any(c.strip() for c in r):
            continue
        head = r[0].strip().lower() if r[0] else ""
        if head in ("totals", "net change", "total"):
            continue
        # Pad row if short
        while len(r) < 11:
            r.append("")
        dt, desc, category, pmt, exp, rev, running, treq, tconf, notes, source = r[:11]
        if not desc.strip():
            continue
        # Date may be blank for the "Climate Summit" placeholder etc.
        dt_clean = dt.strip() if dt and re.match(r"^\d{4}-\d{2}-\d{2}$", dt.strip()) else None
        transactions.append({
            "transaction_date": dt_clean,
            "description": desc.strip(),
            "category": category.strip() or None,
            "payment_method": pmt.strip() or None,
            "expense": money(exp),
            "revenue": money(rev),
            "running_balance": money(running),
            "transfer_required": bool_yn(treq),
            "transfer_confirmed": bool_yn(tconf),
            "notes": notes.strip() or None,
            "source_tag": source.strip() or None,
        })

    return fy_meta, transactions


def parse_dashboard_holdover(path: str) -> Decimal | None:
    """Read 'FY 2026-2027 Holdover (already allocated)' from the dashboard CSV."""
    with open(path) as f:
        for row in csv.reader(f):
            joined = ",".join(c.strip() for c in row)
            if "fy 2026-2027 holdover" in joined.lower():
                for c in row:
                    v = money(c)
                    if v and v > 1000:
                        return v
    return None


def build_sql(fy_meta: dict, txns: list[dict]) -> str:
    parts = ["BEGIN;"]
    # Upsert fiscal_year
    parts.append(f"""
INSERT INTO cgcs.fiscal_years (fy_label, start_date, end_date, starting_balance, holdover_to_next, is_current)
VALUES ({sql_lit(fy_meta["fy_label"])}, {sql_lit(fy_meta["start_date"])}::date,
        {sql_lit(fy_meta["end_date"])}::date, {sql_lit(fy_meta["starting_balance"])},
        {sql_lit(fy_meta["holdover_to_next"])}, TRUE)
ON CONFLICT (fy_label) DO UPDATE SET
    start_date = EXCLUDED.start_date,
    end_date = EXCLUDED.end_date,
    starting_balance = EXCLUDED.starting_balance,
    holdover_to_next = EXCLUDED.holdover_to_next,
    is_current = EXCLUDED.is_current;
""")
    # Wipe + re-insert transactions for this FY (idempotent)
    parts.append(f"DELETE FROM cgcs.ledger_transactions WHERE fy_label = {sql_lit(FY_LABEL)};")

    for t in txns:
        parts.append(f"""
INSERT INTO cgcs.ledger_transactions
    (fy_label, transaction_date, description, category, payment_method,
     expense, revenue, running_balance, transfer_required, transfer_confirmed,
     notes, source_tag)
VALUES
    ({sql_lit(FY_LABEL)}, {sql_lit(t["transaction_date"])}::date,
     {sql_lit(t["description"])}, {sql_lit(t["category"])},
     {sql_lit(t["payment_method"])}, {sql_lit(t["expense"])},
     {sql_lit(t["revenue"])}, {sql_lit(t["running_balance"])},
     {sql_lit(t["transfer_required"])}, {sql_lit(t["transfer_confirmed"])},
     {sql_lit(t["notes"])}, {sql_lit(t["source_tag"])});""")

    # Best-effort link to reservations by description ~ event_name.
    parts.append("""
UPDATE cgcs.ledger_transactions lt
SET linked_reservation_id = r.id
FROM cgcs.reservations r
WHERE lt.linked_reservation_id IS NULL
  AND lt.category IN ('Event Income','Event Expenses')
  AND LOWER(lt.description) = LOWER(r.event_name);""")

    # Looser match: try LIKE for substring containment.
    parts.append("""
UPDATE cgcs.ledger_transactions lt
SET linked_reservation_id = (
    SELECT r.id FROM cgcs.reservations r
    WHERE LOWER(r.event_name) LIKE '%' || LOWER(lt.description) || '%'
       OR LOWER(lt.description) LIKE '%' || LOWER(r.event_name) || '%'
    ORDER BY ABS(r.requested_date - lt.transaction_date)
    LIMIT 1
)
WHERE lt.linked_reservation_id IS NULL
  AND lt.category IN ('Event Income','Event Expenses')
  AND lt.transaction_date IS NOT NULL;""")

    parts.append("COMMIT;")
    return "\n".join(parts)


def main():
    fy_meta, txns = parse_ledger(LEDGER_CSV)
    holdover = parse_dashboard_holdover(DASHBOARD_CSV)
    if holdover:
        fy_meta["holdover_to_next"] = holdover

    print(f"FY {fy_meta['fy_label']}:")
    print(f"  start: {fy_meta['start_date']}  end: {fy_meta['end_date']}")
    print(f"  starting balance: ${fy_meta['starting_balance']}")
    print(f"  holdover to next: ${fy_meta['holdover_to_next']}")
    print(f"Transactions parsed: {len(txns)}")

    sql = build_sql(fy_meta, txns)
    if "--dry-run" in sys.argv:
        print(sql[:2000])
        return 0

    result = subprocess.run(
        ["docker", "exec", "-i", "ai-intake-postgres-1",
         "psql", "-U", "cgcs_admin", "-d", "cgcs_events", "-v", "ON_ERROR_STOP=1"],
        input=sql, text=True, capture_output=True,
    )
    if result.returncode != 0:
        print("psql failed:", file=sys.stderr); print(result.stderr[-2000:], file=sys.stderr)
        return 1
    print(result.stdout[-300:])

    # Summary
    summary = subprocess.run(
        ["docker", "exec", "ai-intake-postgres-1", "psql", "-U", "cgcs_admin",
         "-d", "cgcs_events", "-c", f"""
SELECT category,
       COUNT(*) AS rows,
       COALESCE(SUM(expense),0)::numeric(12,2) AS total_expense,
       COALESCE(SUM(revenue),0)::numeric(12,2) AS total_revenue,
       COUNT(*) FILTER (WHERE linked_reservation_id IS NOT NULL) AS linked
FROM cgcs.ledger_transactions
WHERE fy_label = '{FY_LABEL}'
GROUP BY category ORDER BY total_expense DESC NULLS LAST;
"""],
        capture_output=True, text=True,
    )
    print(summary.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
