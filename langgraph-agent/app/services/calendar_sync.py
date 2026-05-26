"""
Sync the CGCS Events Google Calendar into cgcs.reservations so the dashboard
sees events created directly on the calendar (not just via Smartsheet intake).

One-way only: calendar -> DB. The dashboard never writes back to the calendar.

Per-row classification rules (mirrors Austin's spreadsheet taxonomy):
  Title starts with "C - " or "C- " -> event_category = 'cgcs'
  Title starts with "A - " or "A- " -> event_category = 'acc'
  Title starts with "S - " or "S- " -> event_category = 'monetization'  (paid space rental)
  No recognizable prefix             -> event_category = 'monetization'  (default catch-all)

Dedupe: skip insert when a reservation with the same event_name + requested_date
already exists (from any source).

Full calendar description is stored verbatim in source_metadata.description;
common patterns (CGCS Lead, Ad Astra, POC, layout) are also pulled out into
top-level fields on cgcs_lead and source_metadata for the detail page.
"""
from __future__ import annotations
import asyncio
import json
import logging
import re
from datetime import date, datetime, time, timezone
from typing import Any

from app.db.connection import get_pool
from app.services.google_calendar import list_events as gc_list_events

logger = logging.getLogger(__name__)

_PREFIX_RE = re.compile(r"^\s*([CASca])\s*-\s*", re.IGNORECASE)
_HOLD_RE = re.compile(r"\b(?:HOLD|TENTATIVE)\b", re.IGNORECASE)


# CGCS partner events — always classified as 'cgcs' regardless of title prefix.
# These are the partner orgs Austin called out: LangChain, ACM, Austin AI Alliance, Open Austin.
_CGCS_PARTNER_PATTERNS = (
    "langchain", "lang chain",
    "acm austin", "acm monthly", "acm meetup", "acm meet up",
    "austin ai alliance",
    "open austin",
)


def _is_cgcs_partner(title: str) -> bool:
    low = title.lower()
    if any(p in low for p in _CGCS_PARTNER_PATTERNS):
        return True
    # Standalone "ACM" token (e.g. "ACM Meet", "ACM Event") — but not generic words containing acm
    if re.search(r"\bacm\b", low):
        return True
    return False


def _classify(title: str) -> tuple[str, str]:
    """Return (clean_title, event_category) per Austin's taxonomy:
      C  -> cgcs          (CGCS-led / partner events)
      A  -> monetization  (Advertising, Monetization, Incentive — anything paid externally)
      S  -> acc           (Service — internal ACC events, not charged)
    Partner-name override forces any LangChain/ACM/Austin AI Alliance/Open Austin
    event to 'cgcs' regardless of its title prefix.
    """
    # Strip the prefix first so the partner check works on the clean title
    m = _PREFIX_RE.match(title)
    cleaned = _PREFIX_RE.sub("", title, count=1).strip() if m else title.strip()
    cleaned = re.sub(r"^(EVENT|HOLD|TENTATIVE)\s*-\s*", "", cleaned, count=1, flags=re.IGNORECASE)

    if _is_cgcs_partner(cleaned) or _is_cgcs_partner(title):
        return cleaned, "cgcs"

    if not m:
        return cleaned, "monetization"  # default for un-prefixed external events
    letter = m.group(1).upper()
    mapping = {"C": "cgcs", "A": "monetization", "S": "acc"}
    return cleaned, mapping.get(letter, "monetization")


_LEAD_NAMES = ("austin", "bryan", "cate", "marisela", "stefano", "sarah",
               "allan", "tzur", "vanessa", "michelle")

# Canonical key per common label variant. Lowercased & punctuation-stripped
# label is looked up here. Anything unmatched becomes a snake_case key as-is.
_LABEL_MAP = {
    "event title": "event_title",
    "title": "event_title",
    "host": "organization",
    "host organization": "organization",
    "organization": "organization",
    "organizer": "organization",
    "date": "date_blob",
    "time block reserved": "time_block",
    "time block": "time_block",
    "time": "time_block",
    "location": "location",
    "venue": "location",
    "estimated attendance": "attendance",
    "attendance": "attendance",
    "expected attendance": "attendance",
    "event description": "event_description",
    "description": "event_description",
    "space use layout": "floor_layout",
    "space use": "floor_layout",
    "layout": "floor_layout",
    "floor layout": "floor_layout",
    "setup": "floor_layout",
    "av needs": "av",
    "a v needs": "av",
    "a v": "av",
    "av": "av",
    "audio visual": "av",
    "catering": "catering",
    "food": "catering",
    "staffing volunteers": "staffing",
    "staffing": "staffing",
    "volunteers": "staffing",
    "status": "cal_status",
    "internal notes": "internal_notes",
    "notes": "internal_notes",
    "poc": "poc",
    "point of contact": "poc",
    "poc name": "poc_name",
    "poc email": "poc_email",
    "poc phone": "poc_phone",
    "ad astra": "ad_astra",
    "ad astra number": "ad_astra",
    "tdx request": "tdx",
    "smartsheet": "tdx",
    "cgcs lead": "cgcs_lead",
    "lead": "cgcs_lead",
    "billing": "billing",
    "invoice": "billing",
    "agreement": "agreement",
    "user agreement": "agreement",
}


def _decode_entities(s: str) -> str:
    """Decode the few HTML entities we actually see."""
    return (
        s.replace("&amp;", "&")
         .replace("&lt;", "<")
         .replace("&gt;", ">")
         .replace("&quot;", '"')
         .replace("&#39;", "'")
         .replace("&apos;", "'")
         .replace("&nbsp;", " ")
         .replace("&ndash;", "–")
         .replace("&mdash;", "—")
    )


def _strip_html(s: str) -> str:
    """HTML -> plain text. <br> becomes newline; lists keep bullet points; everything else stripped."""
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</li\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<li\s*>", "• ", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = _decode_entities(s)
    # collapse 3+ blank lines, trim trailing whitespace per line
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _norm_label(label: str) -> str:
    """Normalize a section label for the LABEL_MAP lookup. Decodes HTML entities
    BEFORE stripping non-alpha so '&amp;' doesn't leave the literal text 'amp' behind."""
    lab = _decode_entities(label).lower()
    lab = re.sub(r"[^a-z0-9 ]+", " ", lab)
    lab = re.sub(r"\s+", " ", lab).strip()
    return lab


def _heuristic_lead_from_desc(desc: str) -> str | None:
    """Fallback: scan the plain description for any first name from the known CGCS team list."""
    if not desc: return None
    low = desc.lower()
    for name in _LEAD_NAMES:
        if re.search(rf"\b{name}\b", low):
            return name.title()
    return None


# Match  <p>...<strong>LABEL:</strong>...VALUE...</p>  blocks
_HTML_SECTION_RE = re.compile(
    r"<p[^>]*>\s*<strong[^>]*>(?P<label>[^<]+?):?</strong>\s*(?:<br\s*/?>)?(?P<value>.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)

# Plain-text "Label: value" line (fallback for non-HTML descriptions)
_PLAIN_LINE_RE = re.compile(
    r"^[\s•\-*]*([A-Za-z][A-Za-z0-9 /&]{2,40}?)\s*[:\-]\s*(.+)$",
    re.MULTILINE,
)


def _parse_description(desc: str) -> dict[str, Any]:
    """
    Extract structured fields from a calendar event description.
    Accepts HTML (the common case) or plain text.
    Returns a dict mapped to canonical snake_case keys defined in _LABEL_MAP.
    Unknown labels are preserved with a sanitized snake_case version of their original.
    Also returns a 'description_plain' field with HTML stripped, for the UI to display.
    """
    out: dict[str, Any] = {}
    if not desc:
        return out

    # Always emit a plain-text view of the description for the detail page.
    plain = _strip_html(desc)
    if plain:
        out["description_plain"] = plain

    # Pass 1: HTML <p><strong>Label:</strong>value</p> sections (the format Austin's calendar uses).
    matches = list(_HTML_SECTION_RE.finditer(desc))
    if matches:
        for m in matches:
            label = _norm_label(m.group("label"))
            value = _strip_html(m.group("value")).strip().rstrip(",;.")
            if not value or value.lower() in ("n/a", "none", "tbd", "-", "—"):
                continue
            key = _LABEL_MAP.get(label) or re.sub(r"\s+", "_", label)
            # First match wins so we don't overwrite richer earlier values.
            out.setdefault(key, value)
        return out

    # Pass 2: plain-text "Label: value" lines (handles non-HTML descriptions).
    for m in _PLAIN_LINE_RE.finditer(plain):
        label = _norm_label(m.group(1))
        value = m.group(2).strip().rstrip(",;.")
        if not value or value.lower() in ("n/a", "none", "tbd", "-"):
            continue
        key = _LABEL_MAP.get(label)
        if key:  # only keep recognized labels in plain mode (avoid noise)
            out.setdefault(key, value)
    return out


def _subtype_for(title: str, category: str) -> str:
    t = title.lower()
    if any(k in t for k in ("training", "orientation", "cohort", "workshop", "fellows")):
        return "training"
    if any(k in t for k in ("convening", "summit", "conference", "retreat", "meetup", "roundtable")):
        return "convening"
    if category == "cgcs":
        return "co_branded"
    return "other"


def _split_dt(iso: str) -> tuple[date, time, str]:
    """RFC3339 -> (date, time, original ISO). Returns (date, time(0,0), iso) for all-day."""
    if "T" in iso:
        dt = datetime.fromisoformat(iso)
        return dt.date(), dt.time().replace(tzinfo=None), iso
    return date.fromisoformat(iso), time(0, 0, 0), iso


async def sync_range(start: str, end: str) -> dict[str, Any]:
    """Sync a date range. start/end are YYYY-MM-DD (end exclusive)."""
    time_min = f"{start}T00:00:00-06:00"
    time_max = f"{end}T00:00:00-06:00"
    events = await asyncio.to_thread(gc_list_events, time_min, time_max)

    pool = await get_pool()
    today = date.today()
    inserted = 0
    enriched = 0
    skipped_dedup = 0
    skipped_other = 0
    errors: list[str] = []

    for ev in events:
        try:
            cal_id = ev["id"]
            raw_summary = ev.get("summary") or "(no title)"
            location = ev.get("location") or ""
            description = ev.get("description") or ""

            start_iso = ev.get("start")
            end_iso = ev.get("end")
            if not start_iso or not end_iso:
                skipped_other += 1
                continue

            evt_date, start_time, _ = _split_dt(start_iso)
            _, end_time, _ = _split_dt(end_iso)

            clean_name, category = _classify(raw_summary)
            subtype = _subtype_for(clean_name, category)
            is_hold = bool(_HOLD_RE.search(raw_summary))
            res_status = "completed" if evt_date < today else "approved"

            # Existing row? If yes, enrich metadata instead of inserting a duplicate.
            request_id = f"cal-{cal_id[:48]}"
            parsed_for_meta = _parse_description(description)
            lead_for_existing = parsed_for_meta.get("cgcs_lead") or _heuristic_lead_from_desc(description)
            existing_meta: dict[str, Any] = {
                "calendar_event_id": cal_id,
                "calendar_html_link": ev.get("html_link") or "",
                "raw_title": raw_summary,
                "is_hold": is_hold,
            }
            if location: existing_meta["location"] = location
            if description: existing_meta["description"] = description
            existing_meta.update(parsed_for_meta)

            existing = await pool.fetchrow(
                """
                SELECT id FROM cgcs.reservations
                WHERE LOWER(event_name) = LOWER($1) AND requested_date = $2
                LIMIT 1
                """,
                clean_name, evt_date,
            )
            if existing:
                await pool.execute(
                    """
                    UPDATE cgcs.reservations
                    SET cgcs_lead = COALESCE(cgcs_lead, $1),
                        source_metadata = source_metadata || $2::jsonb,
                        updated_at = NOW()
                    WHERE id = $3
                    """,
                    lead_for_existing, json.dumps(existing_meta), existing["id"],
                )
                enriched += 1
                continue
            parsed = _parse_description(description)
            cgcs_lead = parsed.get("cgcs_lead") or _heuristic_lead_from_desc(description)

            metadata: dict[str, Any] = {
                "calendar_event_id": cal_id,
                "calendar_html_link": ev.get("html_link") or "",
                "raw_title": raw_summary,
                "is_hold": is_hold,
            }
            if location: metadata["location"] = location
            if description: metadata["description"] = description
            for k, v in parsed.items():
                metadata[k] = v

            notes_bits = []
            if is_hold: notes_bits.append("Calendar HOLD (tentative)")
            if location: notes_bits.append(f"Location: {location}")
            notes = " | ".join(notes_bits) or None

            await pool.execute(
                """
                INSERT INTO cgcs.reservations (
                    request_id, requester_name, requester_email,
                    event_name, requested_date, requested_start_time, requested_end_time,
                    room_requested, event_category, event_subtype, event_location,
                    status, source, admin_notes,
                    completed_at, cgcs_lead, source_metadata
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7,
                    'event_hall'::room_type, $8::cgcs.event_category,
                    $9::cgcs.event_subtype, 'on_site'::cgcs.event_location,
                    $10::reservation_status, 'calendar_sync', $11,
                    $12, $13, $14::jsonb
                )
                ON CONFLICT DO NOTHING
                """,
                request_id, "CGCS Events Calendar", "calendar@cgcs-acc.org",
                clean_name, evt_date, start_time, end_time,
                category, subtype, res_status, notes,
                datetime.combine(evt_date, datetime.min.time(), tzinfo=timezone.utc)
                if res_status == "completed" else None,
                cgcs_lead, json.dumps(metadata),
            )
            inserted += 1
        except Exception as e:
            errors.append(f"{ev.get('id','?')}: {e!r}")
            logger.exception("calendar sync row failed")

    summary = {
        "range": {"start": start, "end": end},
        "fetched": len(events),
        "inserted": inserted,
        "enriched": enriched,
        "skipped_dedup": skipped_dedup,
        "skipped_other": skipped_other,
        "errors": errors,
    }
    logger.info("calendar sync: %s", summary)
    return summary
