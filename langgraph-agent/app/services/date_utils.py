"""Date utility functions for CGCS event scheduling.

Business day calculations, lead time validation, and weekend/evening detection.
"""

from __future__ import annotations

from datetime import date, timedelta


def business_days_until(target_date: date, from_date: date | None = None) -> int:
    """Count business days (Mon-Fri) between from_date and target_date.

    Args:
        target_date: The target date to count toward.
        from_date: Starting date. Defaults to today.

    Returns:
        Number of business days. Negative if target_date is in the past.
        The from_date itself is not counted; the target_date is counted
        only if it falls on a business day.
    """
    if from_date is None:
        from_date = date.today()

    if target_date == from_date:
        return 0

    direction = 1 if target_date > from_date else -1
    count = 0
    current = from_date

    while current != target_date:
        current += timedelta(days=direction)
        if current.weekday() < 5:  # Mon-Fri
            count += direction

    return count


def is_within_minimum_lead_time(
    event_date: date,
    min_days: int = 14,
    from_date: date | None = None,
) -> bool:
    """Return True if event_date is at least min_days business days from from_date.

    Args:
        event_date: The proposed event date.
        min_days: Minimum business days required (default 14).
        from_date: Reference date. Defaults to today.
    """
    return business_days_until(event_date, from_date) >= min_days


def is_weekend_or_evening(event_date: date, end_time: str) -> bool:
    """Return True if the event falls on a weekend or ends after 5:00 PM.

    Args:
        event_date: The event date.
        end_time: End time as HH:MM (24h) or "H:MM PM" format.
    """
    if event_date.weekday() >= 5:
        return True

    normalized = _normalize_time(end_time)
    if normalized and normalized > "17:00":
        return True

    return False


def _normalize_time(time_str: str) -> str | None:
    """Convert time string to HH:MM 24-hour format.

    Handles: "17:00", "5:00 PM", "9:00 AM", "21:00"
    Returns None if unparseable.
    """
    if not time_str:
        return None

    time_str = time_str.strip().upper()

    # Already 24h format (HH:MM)
    if len(time_str) == 5 and time_str[2] == ":":
        return time_str

    # 12h format: "5:00 PM", "12:30 AM"
    import re
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", time_str)
    if m:
        hour = int(m.group(1))
        minute = m.group(2)
        period = m.group(3)
        if period == "PM" and hour != 12:
            hour += 12
        elif period == "AM" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute}"

    return None
