"""Google Calendar API service — check availability and create holds on CGCS Events calendar.

Uses service account authentication. Requires GOOGLE_SERVICE_ACCOUNT_FILE env var
pointing to the service account JSON key file.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CALENDAR_ID = getattr(settings, "google_calendar_id", "primary")
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_credentials():
    """Load Google service account credentials."""
    service_account_file = getattr(settings, "google_service_account_file", None)
    if not service_account_file:
        raise RuntimeError(
            "Google Calendar not configured: set GOOGLE_SERVICE_ACCOUNT_FILE"
        )

    try:
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=SCOPES
        )
        return credentials
    except ImportError:
        raise RuntimeError(
            "google-auth package not installed. Add google-auth to requirements.txt"
        )


def _http_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """HTTP request with retry and backoff."""
    import time
    last_error = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=30) as client:
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
        except Exception as e:
            last_error = e
            if attempt < 2:
                delay = 1.0 * (2 ** attempt)
                logger.warning("HTTP %s %s failed (attempt %d/3): %s", method, url, attempt + 1, e)
                time.sleep(delay)
    raise last_error


def check_availability(date: str, start_time: str, end_time: str) -> dict:
    """Check if the CGCS Events calendar is available for the given time slot.

    Args:
        date: ISO date string (YYYY-MM-DD)
        start_time: HH:MM
        end_time: HH:MM

    Returns:
        {"is_available": bool, "events": list[dict]}
    """
    try:
        credentials = _get_credentials()
        from google.auth.transport.requests import Request
        credentials.refresh(Request())

        time_min = f"{date}T{start_time}:00-06:00"  # CT timezone
        time_max = f"{date}T{end_time}:00-06:00"

        url = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"
        response = _http_with_retry(
            "GET",
            url,
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
            headers={"Authorization": f"Bearer {credentials.token}"},
        )

        data = response.json()
        events = data.get("items", [])
        return {
            "is_available": len(events) == 0,
            "events": [
                {
                    "summary": e.get("summary", ""),
                    "start": e.get("start", {}).get("dateTime", ""),
                    "end": e.get("end", {}).get("dateTime", ""),
                }
                for e in events
            ],
        }
    except Exception as e:
        logger.error("Google Calendar availability check failed: %s", e)
        raise


def create_hold(title: str, date: str, start_time: str, end_time: str) -> dict:
    """Create a hold event on the CGCS Events calendar.

    Args:
        title: Event title, e.g. "HOLD - Org Name - 2026-04-15"
        date: ISO date string
        start_time: HH:MM
        end_time: HH:MM

    Returns:
        {"event_id": str, "html_link": str}
    """
    try:
        credentials = _get_credentials()
        from google.auth.transport.requests import Request
        credentials.refresh(Request())

        event_body = {
            "summary": title,
            "start": {"dateTime": f"{date}T{start_time}:00-06:00", "timeZone": "America/Chicago"},
            "end": {"dateTime": f"{date}T{end_time}:00-06:00", "timeZone": "America/Chicago"},
            "description": "Calendar hold created by CGCS Automation Engine",
            "colorId": "5",  # Banana yellow for holds
        }

        url = f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events"
        response = _http_with_retry(
            "POST",
            url,
            json=event_body,
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json",
            },
        )

        data = response.json()
        return {
            "event_id": data["id"],
            "html_link": data.get("htmlLink", ""),
        }
    except Exception as e:
        logger.error("Google Calendar hold creation failed: %s", e)
        raise
