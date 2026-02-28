from __future__ import annotations

PRICING_TIERS: dict[str, dict] = {
    "acc_internal": {"hourly_rate": 0.00, "minimum_hours": 1},
    "government_agency": {"hourly_rate": 0.00, "minimum_hours": 1},
    "nonprofit": {"hourly_rate": 25.00, "minimum_hours": 2},
    "community_partner": {"hourly_rate": 50.00, "minimum_hours": 2},
    "external": {"hourly_rate": 100.00, "minimum_hours": 3},
}


def compute_cost(pricing_tier: str, start_time: str, end_time: str) -> float:
    """Compute estimated cost from pricing tier and duration."""
    tier = PRICING_TIERS.get(pricing_tier)
    if not tier:
        return 0.0

    start_h, start_m = map(int, start_time.split(":"))
    end_h, end_m = map(int, end_time.split(":"))
    duration_hours = (end_h + end_m / 60) - (start_h + start_m / 60)

    if duration_hours <= 0:
        return 0.0

    billable_hours = max(duration_hours, tier["minimum_hours"])
    return round(billable_hours * tier["hourly_rate"], 2)
