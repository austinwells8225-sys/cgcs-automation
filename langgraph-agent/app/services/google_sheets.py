"""Google Sheets API service — read/write P.E.T. tracker spreadsheet.

Uses service account authentication. Requires GOOGLE_SERVICE_ACCOUNT_FILE and
PET_TRACKER_SPREADSHEET_ID env vars.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SPREADSHEET_ID = getattr(settings, "pet_tracker_spreadsheet_id", "")
SHEET_RANGE = "Sheet1"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_credentials():
    """Load Google service account credentials for Sheets API."""
    service_account_file = getattr(settings, "google_service_account_file", None)
    if not service_account_file:
        raise RuntimeError(
            "Google Sheets not configured: set GOOGLE_SERVICE_ACCOUNT_FILE"
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


def read_sheet(query: str = "") -> dict:
    """Read data from the P.E.T. tracker spreadsheet.

    Args:
        query: Optional filter query string

    Returns:
        {"headers": list[str], "rows": list[list[str]]}
    """
    if not SPREADSHEET_ID:
        raise RuntimeError("PET_TRACKER_SPREADSHEET_ID not configured")

    try:
        credentials = _get_credentials()
        from google.auth.transport.requests import Request
        credentials.refresh(Request())

        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
            f"/values/{SHEET_RANGE}"
        )

        with httpx.Client(timeout=30) as client:
            response = client.get(
                url,
                headers={"Authorization": f"Bearer {credentials.token}"},
            )
            response.raise_for_status()

        data = response.json()
        values = data.get("values", [])

        if not values:
            return {"headers": [], "rows": []}

        headers = values[0]
        rows = values[1:]

        # Apply simple text filter if provided
        if query:
            query_lower = query.lower()
            rows = [
                row for row in rows
                if any(query_lower in cell.lower() for cell in row if cell)
            ]

        return {"headers": headers, "rows": rows}
    except Exception as e:
        logger.error("Google Sheets read failed: %s", e)
        raise


def prepare_update(row_data: dict) -> dict:
    """Stage an update for the P.E.T. tracker (does not apply immediately).

    Args:
        row_data: Dict with column names as keys and values to update

    Returns:
        {"staged_id": str, "row_data": dict, "status": "staged"}
    """
    import uuid
    staged_id = str(uuid.uuid4())[:8]

    logger.info("P.E.T. update staged: %s with data: %s", staged_id, row_data)

    return {
        "staged_id": staged_id,
        "row_data": row_data,
        "status": "staged",
    }


def append_row(values: list[str], spreadsheet_id: str = "", sheet_range: str = SHEET_RANGE) -> dict:
    """Append a single row to the P.E.T. tracker spreadsheet.

    Args:
        values: List of cell values (one per column, matching PET_COLUMNS order).
        spreadsheet_id: Override spreadsheet ID (defaults to PET_TRACKER_SPREADSHEET_ID).
        sheet_range: Sheet range in A1 notation (default: Sheet1).

    Returns:
        {"updated_range": str, "updated_rows": int}
    """
    sid = spreadsheet_id or SPREADSHEET_ID
    if not sid:
        raise RuntimeError("PET_TRACKER_SPREADSHEET_ID not configured")

    try:
        credentials = _get_credentials()
        from google.auth.transport.requests import Request
        credentials.refresh(Request())

        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{sid}"
            f"/values/{sheet_range}:append?valueInputOption=USER_ENTERED"
            f"&insertDataOption=INSERT_ROWS"
        )

        with httpx.Client(timeout=30) as client:
            response = client.post(
                url,
                json={"values": [values]},
                headers={
                    "Authorization": f"Bearer {credentials.token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()

        data = response.json()
        updates = data.get("updates", {})
        return {
            "updated_range": updates.get("updatedRange", ""),
            "updated_rows": updates.get("updatedRows", 0),
        }
    except Exception as e:
        logger.error("Google Sheets append failed: %s", e)
        raise


def apply_update(spreadsheet_id: str, range_: str, values: list[list]) -> dict:
    """Apply a previously staged update to the spreadsheet.

    Args:
        spreadsheet_id: The spreadsheet ID
        range_: The A1 notation range to update
        values: 2D array of values

    Returns:
        {"updated_cells": int}
    """
    try:
        credentials = _get_credentials()
        from google.auth.transport.requests import Request
        credentials.refresh(Request())

        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
            f"/values/{range_}?valueInputOption=USER_ENTERED"
        )

        with httpx.Client(timeout=30) as client:
            response = client.put(
                url,
                json={"values": values},
                headers={
                    "Authorization": f"Bearer {credentials.token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()

        data = response.json()
        return {"updated_cells": data.get("updatedCells", 0)}
    except Exception as e:
        logger.error("Google Sheets update failed: %s", e)
        raise
