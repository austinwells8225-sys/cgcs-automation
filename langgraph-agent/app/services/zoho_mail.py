"""Zoho Mail API service — read incoming emails.

Uses Zoho OAuth token auth. Requires ZOHO_MAIL_TOKEN env var.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ZOHO_API_BASE = "https://mail.zoho.com/api"


def _get_headers() -> dict:
    """Get authorization headers for Zoho Mail API."""
    token = getattr(settings, "zoho_mail_token", None)
    if not token:
        raise RuntimeError("Zoho Mail not configured: set ZOHO_MAIL_TOKEN")
    return {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json",
    }


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
                logger.warning("Zoho HTTP %s %s failed (attempt %d/3): %s", method, url, attempt + 1, e)
                time.sleep(delay)
    raise last_error


def get_unread_emails(account_id: str, folder_id: str = "inbox", limit: int = 10) -> list[dict]:
    """Fetch unread emails from Zoho Mail.

    Args:
        account_id: Zoho account ID
        folder_id: Folder to check (default: inbox)
        limit: Max number of emails to fetch

    Returns:
        List of email dicts with id, from, subject, body fields
    """
    url = f"{ZOHO_API_BASE}/accounts/{account_id}/messages/view"
    params = {
        "folderId": folder_id,
        "status": "unread",
        "limit": limit,
    }

    try:
        response = _http_with_retry("GET", url, params=params, headers=_get_headers())
        data = response.json()
        messages = data.get("data", [])

        return [
            {
                "id": msg.get("messageId", ""),
                "from": msg.get("fromAddress", ""),
                "subject": msg.get("subject", ""),
                "body": msg.get("content", ""),
                "received_at": msg.get("receivedTime", ""),
            }
            for msg in messages
        ]
    except Exception as e:
        logger.error("Failed to fetch unread emails: %s", e)
        raise


def send_email(account_id: str, to: str, subject: str, body: str, from_address: str = "") -> dict:
    """Send an email via Zoho Mail.

    Args:
        account_id: Zoho account ID
        to: Recipient email
        subject: Email subject
        body: Email body (HTML)
        from_address: From address (optional)

    Returns:
        {"message_id": str, "status": str}
    """
    url = f"{ZOHO_API_BASE}/accounts/{account_id}/messages"

    email_data = {
        "toAddress": to,
        "subject": subject,
        "content": body,
        "mailFormat": "html",
    }
    if from_address:
        email_data["fromAddress"] = from_address

    try:
        response = _http_with_retry("POST", url, json=email_data, headers=_get_headers())
        data = response.json()
        return {
            "message_id": data.get("data", {}).get("messageId", ""),
            "status": "sent",
        }
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        raise
