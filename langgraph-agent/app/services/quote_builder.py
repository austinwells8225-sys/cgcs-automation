"""Quote builder — pure functions for building and updating itemized quotes."""

from __future__ import annotations

from app.cgcs_constants import AMI_ADDONS, AMI_FACILITY_PRICING, DEPOSIT_RATE
from app.data.pricing import PRICING_TIERS, compute_cost

# Maps user-facing service keys to AMI_ADDONS keys + metadata
SERVICE_KEY_MAP: dict[str, dict] = {
    "av_equipment": {"addon_key": "av", "description": "AV Equipment", "needs": "hours"},
    "av_webcast": {"addon_key": None, "description": "Webcast Surcharge", "flat_rate": 100.0},
    "av_technician": {"addon_key": "acc_technician", "description": "ACC Technician"},
    "furniture_rental": {"addon_key": "furniture", "description": "Furniture Rental"},
    "round_tables": {"addon_key": "round_tables", "description": "Round Tables", "needs": "count"},
    "stage_setup": {"addon_key": "stage_setup", "description": "Stage Setup"},
    "stage_teardown": {"addon_key": "stage_teardown", "description": "Stage Teardown"},
    "admin_support": {"addon_key": "admin_support", "description": "Admin Support"},
    "signage": {"addon_key": "signage", "description": "Signage"},
    "catering_coordination": {"addon_key": "catering_coord", "description": "Catering Coordination"},
    "police": {"addon_key": "police", "description": "Police/Security", "needs": "hours"},
}


def _compute_duration_hours(start_time: str, end_time: str) -> float:
    """Compute duration in hours from HH:MM strings."""
    try:
        sh, sm = map(int, start_time.split(":"))
        eh, em = map(int, end_time.split(":"))
        return max((eh + em / 60) - (sh + sm / 60), 0)
    except (ValueError, AttributeError):
        return 0.0


def _pick_ami_block(duration_hours: float) -> tuple[str, float]:
    """Pick the best AMI facility pricing block based on duration."""
    if duration_hours > 8:
        return "Extended", AMI_FACILITY_PRICING["extended"]
    if duration_hours > 4:
        return "Full Day", AMI_FACILITY_PRICING["full_day"]
    return "Half Day Block", AMI_FACILITY_PRICING["morning"]


def _build_service_line_item(
    service_key: str,
    hours: int | None = None,
    count: int | None = None,
) -> dict | None:
    """Build a line item dict from a service key."""
    mapping = SERVICE_KEY_MAP.get(service_key)
    if not mapping:
        return None

    description = mapping["description"]

    # Special case: webcast surcharge (not in AMI_ADDONS)
    if mapping.get("flat_rate") is not None:
        rate = mapping["flat_rate"]
        return {
            "service": service_key,
            "description": description,
            "quantity": 1,
            "unit_price": rate,
            "total": rate,
        }

    addon_key = mapping.get("addon_key")
    addon = AMI_ADDONS.get(addon_key) if addon_key else None
    if not addon:
        return None

    rate = addon["rate"]
    unit = addon.get("unit", "flat")

    if unit == "per_hour":
        qty = hours or 1
        minimum = addon.get("minimum_hours", 0)
        if minimum and qty < minimum:
            qty = minimum
        desc_suffix = f" ({qty} hrs)"
        return {
            "service": service_key,
            "description": description + desc_suffix,
            "quantity": qty,
            "unit_price": rate,
            "total": round(rate * qty, 2),
        }

    if unit == "each":
        qty = count or 1
        desc_suffix = f" (×{qty})"
        return {
            "service": service_key,
            "description": description + desc_suffix,
            "quantity": qty,
            "unit_price": rate,
            "total": round(rate * qty, 2),
        }

    # flat / up_to / surcharge
    return {
        "service": service_key,
        "description": description,
        "quantity": 1,
        "unit_price": rate,
        "total": rate,
    }


def _detect_addons_from_setup(setup_config: dict | None) -> list[dict]:
    """Auto-detect add-on line items from setup_config keywords."""
    if not setup_config:
        return []

    items = []
    config_str = str(setup_config).lower()

    if setup_config.get("projector") or setup_config.get("video_conferencing"):
        item = _build_service_line_item("av_equipment", hours=1)
        if item:
            items.append(item)

    if setup_config.get("catering"):
        item = _build_service_line_item("catering_coordination")
        if item:
            items.append(item)

    if "stage" in config_str:
        item = _build_service_line_item("stage_setup")
        if item:
            items.append(item)

    tables = setup_config.get("tables")
    if tables and isinstance(tables, int) and tables > 0:
        if "round" in config_str:
            item = _build_service_line_item("round_tables", count=tables)
            if item:
                items.append(item)

    return items


def build_initial_quote(reservation: dict) -> dict:
    """Build the first quote version from reservation data.

    Args:
        reservation: dict with pricing_tier, requested_start_time,
            requested_end_time, event_type, setup_config, etc.

    Returns:
        Quote dict with version, line_items, subtotal, deposit_amount, total.
    """
    pricing_tier = reservation.get("pricing_tier", "external")
    start_time = str(reservation.get("requested_start_time", "09:00"))
    end_time = str(reservation.get("requested_end_time", "17:00"))
    event_type = reservation.get("event_type", "")
    setup_config = reservation.get("setup_config")
    if isinstance(setup_config, str):
        import json
        try:
            setup_config = json.loads(setup_config)
        except (json.JSONDecodeError, TypeError):
            setup_config = None

    duration = _compute_duration_hours(start_time, end_time)
    line_items: list[dict] = []

    # Base facility cost
    if event_type == "A-EVENT":
        block_name, block_cost = _pick_ami_block(duration)
        line_items.append({
            "service": "facility",
            "description": f"Event Hall — {block_name}",
            "quantity": 1,
            "unit_price": block_cost,
            "total": block_cost,
        })
    else:
        base_cost = compute_cost(pricing_tier, start_time, end_time)
        tier_info = PRICING_TIERS.get(pricing_tier, {})
        hourly_rate = tier_info.get("hourly_rate", 0)
        if base_cost > 0:
            billable = max(duration, tier_info.get("minimum_hours", 1))
            line_items.append({
                "service": "facility",
                "description": f"Facility — {pricing_tier} (${hourly_rate:.0f}/hr × {billable:.1f} hrs)",
                "quantity": billable,
                "unit_price": hourly_rate,
                "total": base_cost,
            })
        else:
            line_items.append({
                "service": "facility",
                "description": f"Facility — {pricing_tier} (no charge)",
                "quantity": 1,
                "unit_price": 0.0,
                "total": 0.0,
            })

    # Auto-detect add-ons from setup config
    addon_items = _detect_addons_from_setup(setup_config)
    line_items.extend(addon_items)

    subtotal = round(sum(item["total"] for item in line_items), 2)
    deposit = round(subtotal * DEPOSIT_RATE, 2) if event_type == "A-EVENT" else 0.0

    return {
        "version": 1,
        "line_items": line_items,
        "subtotal": subtotal,
        "deposit_amount": deposit,
        "total": subtotal,
        "changes_from_previous": None,
        "notes": None,
    }


def update_quote(
    current_quote: dict,
    add_services: list[dict] | None = None,
    remove_services: list[str] | None = None,
) -> dict:
    """Create a new quote version by adding/removing services.

    Args:
        current_quote: The latest quote version dict.
        add_services: List of {"service": str, "hours": int|None, "count": int|None}.
        remove_services: List of service key strings to remove.

    Returns:
        New quote dict with incremented version and changes_from_previous.
    """
    add_services = add_services or []
    remove_services = remove_services or []

    # Copy existing line items
    existing_items = list(current_quote.get("line_items", []))
    previous_total = current_quote.get("total", 0)
    had_deposit = current_quote.get("deposit_amount", 0) > 0

    added: list[dict] = []
    removed: list[dict] = []

    # Remove services
    for svc_key in remove_services:
        for i, item in enumerate(existing_items):
            if item["service"] == svc_key:
                removed.append({"service": svc_key, "description": item["description"], "total": item["total"]})
                existing_items.pop(i)
                break

    # Add services
    for svc in add_services:
        svc_key = svc.get("service", "")
        hours = svc.get("hours")
        count = svc.get("count")
        item = _build_service_line_item(svc_key, hours=hours, count=count)
        if item:
            existing_items.append(item)
            added.append({"service": svc_key, "description": item["description"], "total": item["total"]})

    subtotal = round(sum(item["total"] for item in existing_items), 2)
    deposit = round(subtotal * DEPOSIT_RATE, 2) if had_deposit else 0.0

    changes = {
        "added": added,
        "removed": removed,
        "previous_total": previous_total,
        "new_total": subtotal,
        "difference": round(subtotal - previous_total, 2),
    }

    return {
        "version": current_quote.get("version", 1) + 1,
        "line_items": existing_items,
        "subtotal": subtotal,
        "deposit_amount": deposit,
        "total": subtotal,
        "changes_from_previous": changes,
        "notes": None,
    }


def format_quote_for_email(quote_version: dict) -> str:
    """Format a quote version as a clean text block for embedding in emails."""
    version = quote_version.get("version", 1)
    line_items = quote_version.get("line_items", [])
    subtotal = quote_version.get("subtotal", 0)
    deposit = quote_version.get("deposit_amount", 0)
    total = quote_version.get("total", 0)
    changes = quote_version.get("changes_from_previous")

    added_services = set()
    if changes:
        added_services = {a["service"] for a in changes.get("added", [])}

    lines: list[str] = []
    lines.append(f"Updated Quote — Version {version}")
    lines.append("─" * 40)

    for item in line_items:
        desc = item["description"]
        item_total = item["total"]
        marker = "  ← NEW" if item["service"] in added_services else ""
        lines.append(f"  {desc:<30} ${item_total:>10,.2f}{marker}")

    lines.append("─" * 40)
    lines.append(f"  {'Subtotal:':<30} ${subtotal:>10,.2f}")
    if deposit > 0:
        lines.append(f"  {'Deposit (5%):':<30} ${deposit:>10,.2f}")
    lines.append(f"  {'Total:':<30} ${total:>10,.2f}")

    if changes:
        lines.append("")
        lines.append("Changes from previous quote:")
        for a in changes.get("added", []):
            lines.append(f"  + Added {a['description']}: ${a['total']:,.2f}")
        for r in changes.get("removed", []):
            lines.append(f"  - Removed {r['description']}: -${r['total']:,.2f}")
        diff = changes.get("difference", 0)
        prev = changes.get("previous_total", 0)
        sign = "+" if diff >= 0 else ""
        lines.append(f"  Previous total: ${prev:,.2f} → New total: ${total:,.2f} ({sign}${diff:,.2f})")

    return "\n".join(lines)
