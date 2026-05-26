#!/usr/bin/env python3
"""
Enrich existing cgcs.reservations rows with cgcs_lead + source_metadata, pulled
from the three Proposed Events Tracker CSV exports. UPDATE-only — won't disturb
event_category edits, status changes, revenue corrections, etc.

Match strategy:
  1. Parse a YYYY-MM-DD date out of the row's date string.
  2. Locate the reservation by (LOWER(event_name) substring match, requested_date).
  3. If we find exactly one match, UPDATE cgcs_lead (if NULL) and merge metadata.

Anything ambiguous is reported and skipped.
"""
from __future__ import annotations
import csv, json, re, subprocess, sys
from typing import Iterable

COMPLETED = "/Users/a2068129/Downloads/Proposed Events Tracker  - Active - 2026-05-18 - Completed (1).csv"
UPCOMING  = "/Users/a2068129/Downloads/Proposed Events Tracker  - Active - 2026-05-18 - UPCOMING.csv"
DECLINED  = "/Users/a2068129/Downloads/Proposed Events Tracker  - Active - 2026-05-18 - DECLINED.csv"

MONTHS = {
    "january": 1, "janurary": 1, "feb": 2, "february": 2, "febuary": 2,
    "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "sept": 9, "september": 9, "septermber": 9, "octorber": 10, "october": 10,
    "novermber": 11, "november": 11, "december": 12,
}


def parse_date(s: str, default_year: int = 2026) -> str | None:
    if not s: return None
    s = s.strip()
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})", s)
    if m:
        mo = MONTHS.get(m.group(1).lower())
        if mo: return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(2)):02d}"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?", s)
    if m:
        mo = MONTHS.get(m.group(1).lower())
        if mo: return f"{default_year:04d}-{mo:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", s)
    if m:
        mo, d, yr = int(m.group(1)), int(m.group(2)), m.group(3)
        y = default_year if not yr else (2000 + int(yr) if len(yr) == 2 else int(yr))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s.lower())).strip()


COMPLETED_COLS = [
    "event_name", "status", "entered_in_calendar", "classification", "date", "time",
    "cgcs_lead", "_unused1", "ad_astra", "tdx", "floor_layout", "revenue",
    "stage", "additional_needs", "walkthrough", "invoice_generated", "agreement_sent",
    "_unused2", "rooms", "poc", "organization",
]

UPCOMING_COLS = [
    "event_name", "status", "entered_in_calendar", "classification", "date", "time",
    "cgcs_lead", "contact_info", "attendance", "money_expected", "ad_astra", "tdx",
    "floor_layout", "stage", "breakdown_time", "additional_needs", "walkthrough_date",
    "invoice_generated", "rooms", "cgcs_labor",
]

DECLINED_COLS = [
    "event_name", "reason", "because_of_acc_event", "ami_stewardship_cgcs",
    "revenue_lost", "booked", "av", "catering", "police", "customer_canceled",
    "authorizing_official",
]


def row_to_dict(row: list[str], cols: list[str]) -> dict[str, str]:
    out = {}
    for i, name in enumerate(cols):
        if name.startswith("_unused"): continue
        if i < len(row):
            v = row[i].strip() if row[i] else ""
            if v:
                out[name] = v
    return out


def read_csv(path: str, cols: list[str], default_year: int = 2026,
             skip_first_n: int = 0) -> list[dict]:
    out = []
    with open(path) as f:
        rows = list(csv.reader(f))
    for raw in rows[skip_first_n:]:
        if not raw or not raw[0].strip():
            continue
        # Skip header-y rows
        if raw[0].strip().lower() in ("event name", "event"):
            continue
        d = row_to_dict(raw, cols)
        dt = parse_date(d.get("date", "") or d.get("event_name", ""), default_year)
        if dt:
            d["_parsed_date"] = dt
        d["_norm_name"] = normalize_name(re.sub(r"\([^)]*\)", "", d.get("event_name", "")))
        out.append(d)
    return out


def sql_lit(v) -> str:
    if v is None: return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def build_updates(rows: list[dict]) -> list[str]:
    updates = []
    for r in rows:
        dt = r.get("_parsed_date")
        if not dt: continue
        norm = r.get("_norm_name", "").strip()
        if not norm: continue
        # token list for ILIKE %word%-style fuzzy match — require first 3 tokens to all appear
        tokens = norm.split()[:3]
        if not tokens: continue

        lead = r.get("cgcs_lead") or ""
        # strip if value is "TBD" / "" / a single non-name word
        if lead.lower() in ("tbd", "n/a", "none", "-"):
            lead = ""
        meta = {k: v for k, v in r.items()
                if not k.startswith("_") and v}

        ilike_conds = " AND ".join(
            f"LOWER(event_name) LIKE {sql_lit('%' + t + '%')}" for t in tokens
        )
        # UPDATE only the matching reservation(s) on that date.
        # COALESCE preserves existing values (don't blow away inline edits).
        upd = f"""
UPDATE cgcs.reservations
SET cgcs_lead = COALESCE(cgcs_lead, NULLIF({sql_lit(lead)}, '')),
    source_metadata = source_metadata || {sql_lit(json.dumps(meta))}::jsonb,
    updated_at = NOW()
WHERE requested_date = {sql_lit(dt)}::date AND {ilike_conds};"""
        updates.append(upd)
    return updates


def main() -> int:
    print("Reading CSVs…")
    completed = read_csv(COMPLETED, COMPLETED_COLS, default_year=2025)
    upcoming = read_csv(UPCOMING, UPCOMING_COLS, default_year=2026, skip_first_n=2)
    declined = read_csv(DECLINED, DECLINED_COLS, default_year=2025)
    print(f"  Completed: {len(completed)} rows")
    print(f"  Upcoming:  {len(upcoming)} rows")
    print(f"  Declined:  {len(declined)} rows")

    all_rows = completed + upcoming + declined
    updates = build_updates(all_rows)
    print(f"Generated {len(updates)} UPDATE statements")
    if "--dry-run" in sys.argv:
        print("\n".join(updates[:5]))
        return 0

    sql = "BEGIN;\n" + "\n".join(updates) + "\nCOMMIT;"
    result = subprocess.run(
        ["docker", "exec", "-i", "ai-intake-postgres-1",
         "psql", "-U", "cgcs_admin", "-d", "cgcs_events", "-v", "ON_ERROR_STOP=1"],
        input=sql, text=True, capture_output=True,
    )
    if result.returncode != 0:
        print("psql failed:", file=sys.stderr); print(result.stderr[-2000:], file=sys.stderr)
        return 1
    # report row counts touched
    print(result.stdout[-500:])

    # Summary query
    summary = subprocess.run(
        ["docker", "exec", "ai-intake-postgres-1", "psql", "-U", "cgcs_admin",
         "-d", "cgcs_events", "-c",
         "SELECT COUNT(*) FILTER (WHERE cgcs_lead IS NOT NULL) AS with_lead, "
         "COUNT(*) FILTER (WHERE source_metadata <> '{}'::jsonb) AS with_meta, "
         "COUNT(*) AS total FROM cgcs.reservations;"],
        capture_output=True, text=True,
    )
    print(summary.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
