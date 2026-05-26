#!/usr/bin/env python3
"""
Import UPCOMING and DECLINED tabs from the Proposed Events Tracker CSV exports
into cgcs.reservations.

Status mapping:
  UPCOMING tab:
    "Scheduled" / "In Progress" -> reservation_status = 'approved'
    "Cancelled"                 -> reservation_status = 'cancelled'
    "?"                         -> reservation_status = 'pending_review'
  DECLINED tab:
    all rows                    -> reservation_status = 'rejected'

Category mapping (same as Completed import):
  Internal-S/A -> acc | Internal-C -> cgcs
  External-S/A -> monetization | External-C -> cgcs
  (DECLINED uses AMI/Stewardship/CGCS column: CGCS->cgcs, else monetization)

Skipped rows are listed at the end.
"""
from __future__ import annotations
import csv, re, subprocess, sys
from datetime import date

UPCOMING_PATH = "/Users/a2068129/Downloads/Proposed Events Tracker  - Active - 2026-05-18 - UPCOMING.csv"
DECLINED_PATH = "/Users/a2068129/Downloads/Proposed Events Tracker  - Active - 2026-05-18 - DECLINED.csv"

MONTHS = {
    "january": 1, "janurary": 1, "feb": 2, "february": 2, "febuary": 2,
    "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "sept": 9, "september": 9, "septermber": 9, "octorber": 10, "october": 10,
    "novermber": 11, "november": 11, "december": 12,
}


def parse_date(s: str, default_year: int = 2026) -> str | None:
    """Parse messy date strings into ISO YYYY-MM-DD. Returns None if unparseable."""
    if not s: return None
    s = s.strip()
    # Explicit year, e.g. "September 15th, 2026"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})", s)
    if m:
        month = MONTHS.get(m.group(1).lower())
        if month: return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"
    # "Month Day" no year
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?", s)
    if m:
        month = MONTHS.get(m.group(1).lower())
        if month: return f"{default_year:04d}-{month:02d}-{int(m.group(2)):02d}"
    # "M/D" or "M/D/YY" embedded
    m = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", s)
    if m:
        mo, d, yr = int(m.group(1)), int(m.group(2)), m.group(3)
        y = default_year if not yr else (2000 + int(yr) if len(yr) == 2 else int(yr))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def parse_time_range(s: str) -> tuple[str, str] | None:
    """Parse '5PM-9PM' / '8:00AM-3:00PM' / '8AM-12PM' -> ('17:00:00','21:00:00'). None if unparseable."""
    if not s: return None
    s = s.replace("–", "-").replace("—", "-").strip()
    # Try to find two time tokens separated by dash or space
    parts = re.split(r"\s*-\s*", s)
    if len(parts) != 2: return None
    def to24(tok: str) -> str | None:
        tok = tok.strip().upper().replace(" ", "")
        m = re.match(r"^(\d{1,2})(?::(\d{2}))?(AM|PM)?$", tok)
        if not m: return None
        h, mn, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if ap == "PM" and h != 12: h += 12
        if ap == "AM" and h == 12: h = 0
        if not ap and h < 8:  # heuristic: bare "12-4" likely PM
            h += 12
        return f"{h:02d}:{mn:02d}:00"
    # Carry AM/PM from second token back if first has none
    second = to24(parts[1])
    first_tok = parts[0].strip().upper().replace(" ", "")
    if not re.search(r"AM|PM", first_tok) and second:
        # use second's AM/PM only if first is < 12; otherwise treat first as AM
        ap = "PM" if "PM" in parts[1].upper() else "AM"
        first_tok = first_tok + ap
    first = to24(first_tok)
    if first and second: return first, second
    return None


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
def extract_email(s: str) -> str:
    m = EMAIL_RE.search(s or "")
    return m.group(0).lower() if m else "unknown@unknown.com"


def map_room(s: str) -> str:
    s = (s or "").lower()
    if "3328" in s: return "classroom"
    if any(x in s for x in ("3346", "3347", "3348", "3344", "3345", "confer")): return "small_conference"
    return "event_hall"  # default (3340 / unspecified)


def map_category(int_ext: str, status_suffix: str) -> str:
    """Internal/External + -S/-A/-C -> event_category."""
    ie = (int_ext or "").lower()
    sfx = status_suffix.lower()
    if "internal" in ie:
        return "cgcs" if sfx == "c" else "acc"
    return "cgcs" if sfx == "c" else "monetization"


def extract_status_suffix(status: str) -> str:
    """'Scheduled - C' -> 'c'; 'In Progress' -> '' """
    m = re.search(r"-\s*([SAC])\s*$", status, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def map_revenue(s: str) -> float:
    if not s: return 0.0
    # Strip $, commas, then keep first numeric token
    s = s.replace("$", "").replace(",", "").replace("?", "0").strip()
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else 0.0


def sql_escape(v) -> str:
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def gen_insert(req_id, name_evt, email, name_poc, org, dt, start, end, room,
               revenue, category, status, source, completed_at=None,
               cancelled_at=None, notes=None) -> str:
    subtype = "co_branded" if category == "cgcs" else "other"
    return f"""
INSERT INTO cgcs.reservations (
    request_id, requester_name, requester_email, requester_organization,
    event_name, requested_date, requested_start_time, requested_end_time,
    room_requested, actual_revenue,
    event_category, event_subtype, event_location,
    status, source, completed_at, cancelled_at, admin_notes
) VALUES (
    {sql_escape(req_id)}, {sql_escape(name_poc)}, {sql_escape(email)}, {sql_escape(org)},
    {sql_escape(name_evt)}, {sql_escape(dt)}, {sql_escape(start)}, {sql_escape(end)},
    {sql_escape(room)}::room_type, {revenue},
    {sql_escape(category)}::cgcs.event_category,
    {sql_escape(subtype)}::cgcs.event_subtype,
    'on_site'::cgcs.event_location,
    {sql_escape(status)}::reservation_status,
    {sql_escape(source)},
    {sql_escape(completed_at)}::timestamptz,
    {sql_escape(cancelled_at)}::timestamptz,
    {sql_escape(notes)}
) ON CONFLICT DO NOTHING;"""


def process_upcoming() -> tuple[list[str], list[tuple[str, str]]]:
    inserts, skipped = [], []
    with open(UPCOMING_PATH) as f:
        rows = list(csv.reader(f))
    # rows[0]=header, rows[1]=key, rows[2:]=data
    for i, r in enumerate(rows[2:], start=3):
        if not r or not r[0].strip(): continue
        name = r[0].strip()
        status_raw = r[1].strip() if len(r) > 1 else ""
        int_ext = r[3].strip() if len(r) > 3 else ""
        date_raw = r[4].strip() if len(r) > 4 else ""
        time_raw = r[5].strip() if len(r) > 5 else ""
        contact = r[7] if len(r) > 7 else ""
        revenue_raw = r[9].strip() if len(r) > 9 else ""
        tdx = r[11].strip() if len(r) > 11 else ""
        rooms = r[18].strip() if len(r) > 18 else ""

        # Status -> reservation_status
        s_lower = status_raw.lower()
        if "cancel" in s_lower:
            res_status = "cancelled"
        elif "?" in s_lower:
            res_status = "pending_review"
        else:
            res_status = "approved"

        # Category
        sfx = extract_status_suffix(status_raw)
        category = map_category(int_ext, sfx)

        dt = parse_date(date_raw, 2026)
        if not dt:
            skipped.append((name, f"unparseable date: {date_raw!r}"))
            continue
        tr = parse_time_range(time_raw)
        if not tr:
            if res_status == "cancelled":
                # Cancelled events: time often unknown; use 00:00 placeholder
                tr = ("00:00:00", "00:00:00")
            else:
                skipped.append((name, f"unparseable time: {time_raw!r}"))
                continue

        req_id = tdx.lstrip("#").strip() or f"upcoming-{i:03d}"
        email = extract_email(contact)
        poc_name = (contact.split("\n")[0].strip()[:200] or "Unknown")
        room = map_room(rooms)
        rev = map_revenue(revenue_raw)
        cancelled_at = f"{dt} 00:00:00+00" if res_status == "cancelled" else None
        notes_bits = []
        if "in progress" in s_lower: notes_bits.append("Was 'In Progress' in tracker.")
        if "–" in date_raw or "-" in date_raw and not re.match(r"^\d", date_raw):
            notes_bits.append(f"Original date string: {date_raw!r}")
        notes = " | ".join(notes_bits) or None

        inserts.append(gen_insert(req_id, name, email, poc_name, None, dt,
                                  tr[0], tr[1], room, rev, category,
                                  res_status, "manual_backfill",
                                  cancelled_at=cancelled_at, notes=notes))
    return inserts, skipped


def process_declined() -> tuple[list[str], list[tuple[str, str]]]:
    inserts, skipped = [], []
    with open(DECLINED_PATH) as f:
        rows = list(csv.reader(f))
    for i, r in enumerate(rows[1:], start=2):  # skip header
        if not r or not r[0].strip(): continue
        name_with_date = r[0].strip()
        reason = r[1].strip() if len(r) > 1 else ""
        ami_col = r[3].strip().lower() if len(r) > 3 else ""
        revenue_raw = r[4].strip() if len(r) > 4 else ""

        # Extract date from event name e.g. "Foo (6/10)" or "Foo (2/2-2/4)" — first M/D match
        dm = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", name_with_date)
        if not dm:
            skipped.append((name_with_date, "no date found in event name"))
            continue
        mo, d, yr = int(dm.group(1)), int(dm.group(2)), dm.group(3)
        # Year heuristic: if month >= 7, it's 2025; else 2026
        # (declined events are recent past relative to current date 2026-05-26)
        y = (2000 + int(yr) if yr and len(yr) == 2 else
             int(yr) if yr else (2025 if mo >= 7 else 2026))
        dt = f"{y:04d}-{mo:02d}-{d:02d}"
        evt_name = re.sub(r"\s*\([^)]*\)\s*$", "", name_with_date).strip()

        # Category from AMI col
        if "cgcs" in ami_col:
            category = "cgcs"
        elif "stewardship" in ami_col:
            category = "acc"
        else:
            category = "monetization"

        rev = map_revenue(revenue_raw)
        req_id = f"declined-{i:03d}"
        notes = f"Reason: {reason}" if reason else None

        inserts.append(gen_insert(req_id, evt_name, "unknown@unknown.com",
                                  "Unknown", None, dt, "00:00:00", "00:00:00",
                                  "event_hall", rev, category,
                                  "rejected", "manual_backfill_declined",
                                  notes=notes))
    return inserts, skipped


def main():
    up_inserts, up_skipped = process_upcoming()
    dec_inserts, dec_skipped = process_declined()

    print(f"UPCOMING: {len(up_inserts)} to insert, {len(up_skipped)} skipped")
    print(f"DECLINED: {len(dec_inserts)} to insert, {len(dec_skipped)} skipped")
    if "--dry-run" in sys.argv:
        print("\n".join(up_inserts + dec_inserts))
        return 0

    sql = "BEGIN;\n" + "\n".join(up_inserts + dec_inserts) + "\nCOMMIT;"
    result = subprocess.run(
        ["docker", "exec", "-i", "ai-intake-postgres-1",
         "psql", "-U", "cgcs_admin", "-d", "cgcs_events", "-v", "ON_ERROR_STOP=1"],
        input=sql, text=True, capture_output=True,
    )
    if result.returncode != 0:
        print("psql failed:", file=sys.stderr); print(result.stderr, file=sys.stderr)
        return 1
    print(result.stdout[-500:])

    if up_skipped or dec_skipped:
        print("\nSkipped rows (need manual cleanup):")
        for name, why in up_skipped + dec_skipped:
            print(f"  - {name[:70]}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
