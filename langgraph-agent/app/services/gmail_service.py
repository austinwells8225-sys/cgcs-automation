"""Gmail API service — send, read, and manage emails via Google Workspace.

Uses service account with domain-wide delegation to impersonate
the CGCS admin mailbox. Requires GOOGLE_SERVICE_ACCOUNT_FILE env var
and GMAIL_DELEGATED_USER for the impersonated address.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


def _get_credentials():
    """Load Google service account credentials with domain-wide delegation."""
    service_account_file = settings.google_service_account_file
    if not service_account_file:
        raise RuntimeError(
            "Gmail not configured: set GOOGLE_SERVICE_ACCOUNT_FILE"
        )

    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=SCOPES
    )
    delegated = credentials.with_subject(settings.gmail_delegated_user)
    return delegated


def _get_gmail_service():
    """Build an authorized Gmail API service client."""
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

    credentials = _get_credentials()
    credentials.refresh(Request())
    return build("gmail", "v1", credentials=credentials)


def _retry_transient(func, *args, max_attempts: int = 3, **kwargs):
    """Call func with retry on transient errors (5xx, connection, timeout)."""
    from googleapiclient.errors import HttpError

    last_error = None
    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        except HttpError as e:
            last_error = e
            if e.resp.status < 500 and e.resp.status != 429:
                raise
            logger.warning(
                "Gmail API transient error (attempt %d/%d): %s",
                attempt + 1, max_attempts, e,
            )
        except (ConnectionError, TimeoutError, OSError) as e:
            last_error = e
            logger.warning(
                "Gmail API connection error (attempt %d/%d): %s",
                attempt + 1, max_attempts, e,
            )
        if attempt < max_attempts - 1:
            delay = 1.0 * (2 ** attempt)
            time.sleep(delay)
    raise last_error


def _build_mime_message(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    attachments: list[dict] | None = None,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
) -> MIMEMultipart | MIMEText:
    """Build a MIME message for the Gmail API.

    attachments: list of {"filename": str, "content": bytes, "mime_type": str}
    """
    sender = settings.gmail_delegated_user

    if attachments:
        message = MIMEMultipart()
        message.attach(MIMEText(body, "html"))
        for attachment in attachments:
            part = MIMEBase(
                *attachment.get("mime_type", "application/octet-stream").split("/", 1)
            )
            part.set_payload(attachment["content"])
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{attachment["filename"]}"',
            )
            message.attach(part)
    else:
        message = MIMEText(body, "html")

    message["to"] = to
    message["from"] = sender
    message["subject"] = subject
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to

    return message


def _extract_header(headers: list[dict], name: str) -> str:
    """Extract a header value from Gmail API headers list."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _parse_message(msg: dict) -> dict:
    """Parse a Gmail API message resource into a clean dict."""
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])

    body_text = ""
    # Try plain text first, then HTML
    if payload.get("body", {}).get("data"):
        body_text = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    elif payload.get("parts"):
        for part in payload["parts"]:
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data")
            if data and mime == "text/plain":
                body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                break
            elif data and mime == "text/html" and not body_text:
                body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId", ""),
        "from": _extract_header(headers, "From"),
        "to": _extract_header(headers, "To"),
        "subject": _extract_header(headers, "Subject"),
        "body_text": body_text,
        "date": _extract_header(headers, "Date"),
        "labels": msg.get("labelIds", []),
    }


# ============================================================
# Public async API
# ============================================================


async def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """Send an email from admin@cgcs-acc.org.

    Returns:
        {"message_id": str, "thread_id": str}
    """
    def _send():
        service = _get_gmail_service()
        message = _build_mime_message(to, subject, body, cc=cc, bcc=bcc, attachments=attachments)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        result = _retry_transient(
            service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute,
        )
        return {
            "message_id": result.get("id", ""),
            "thread_id": result.get("threadId", ""),
        }

    return await asyncio.to_thread(_send)


async def read_inbox(query: str = "is:unread", max_results: int = 50) -> list[dict]:
    """Read inbox messages matching a query.

    Returns:
        List of {id, thread_id, from, to, subject, body_text, date, labels}
    """
    def _read():
        service = _get_gmail_service()
        response = _retry_transient(
            service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute,
        )
        messages = response.get("messages", [])
        results = []
        for msg_stub in messages:
            full = _retry_transient(
                service.users().messages().get(
                    userId="me", id=msg_stub["id"], format="full"
                ).execute,
            )
            results.append(_parse_message(full))
        return results

    return await asyncio.to_thread(_read)


async def get_email(message_id: str) -> dict:
    """Get full email details by message ID.

    Returns:
        {id, thread_id, from, to, subject, body_text, date, labels}
    """
    def _get():
        service = _get_gmail_service()
        msg = _retry_transient(
            service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute,
        )
        return _parse_message(msg)

    return await asyncio.to_thread(_get)


async def mark_as_read(message_id: str) -> bool:
    """Remove UNREAD label from a message.

    Returns:
        True on success.
    """
    def _mark():
        service = _get_gmail_service()
        _retry_transient(
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute,
        )
        return True

    return await asyncio.to_thread(_mark)


async def reply_to_thread(
    thread_id: str,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
) -> dict:
    """Reply within an existing email thread.

    Returns:
        {"message_id": str, "thread_id": str}
    """
    def _reply():
        service = _get_gmail_service()

        # Fetch the thread to get the original Message-ID header for In-Reply-To
        thread = _retry_transient(
            service.users().threads().get(
                userId="me", id=thread_id, format="metadata",
                metadataHeaders=["Message-Id"],
            ).execute,
        )
        original_message_id = ""
        if thread.get("messages"):
            last_msg = thread["messages"][-1]
            original_message_id = _extract_header(
                last_msg.get("payload", {}).get("headers", []),
                "Message-Id",
            )

        message = _build_mime_message(
            to, subject, body, cc=cc,
            in_reply_to=original_message_id,
        )
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        result = _retry_transient(
            service.users().messages().send(
                userId="me", body={"raw": raw, "threadId": thread_id}
            ).execute,
        )
        return {
            "message_id": result.get("id", ""),
            "thread_id": result.get("threadId", ""),
        }

    return await asyncio.to_thread(_reply)


async def create_draft(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """Create a Gmail draft (NOT sent) in admin@cgcs-acc.org's Drafts folder.

    Use this for AI-generated replies that need human review before sending.
    Austin opens Gmail, sees the draft, edits, hits Send.

    Returns:
        {"draft_id": str, "message_id": str, "thread_id": str}
    """
    def _create():
        service = _get_gmail_service()
        message = _build_mime_message(to, subject, body, cc=cc, bcc=bcc, attachments=attachments)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        result = _retry_transient(
            service.users().drafts().create(
                userId="me",
                body={"message": {"raw": raw}},
            ).execute,
        )
        msg = result.get("message", {}) or {}
        return {
            "draft_id": result.get("id", ""),
            "message_id": msg.get("id", ""),
            "thread_id": msg.get("threadId", ""),
        }

    return await asyncio.to_thread(_create)


async def create_draft_reply(
    thread_id: str,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
) -> dict:
    """Create a Gmail draft threaded as a reply to an existing message.

    The draft will appear in the original email's thread, so when Austin
    opens Gmail he sees it attached to the original Smartsheet notification
    (not floating in the Drafts folder as a standalone).

    Returns:
        {"draft_id": str, "message_id": str, "thread_id": str}
    """
    def _create():
        service = _get_gmail_service()

        # Look up the Message-Id of the last message in the thread so we can
        # set In-Reply-To / References headers correctly.
        thread = _retry_transient(
            service.users().threads().get(
                userId="me", id=thread_id, format="metadata",
                metadataHeaders=["Message-Id"],
            ).execute,
        )
        original_message_id = ""
        if thread.get("messages"):
            last_msg = thread["messages"][-1]
            original_message_id = _extract_header(
                last_msg.get("payload", {}).get("headers", []),
                "Message-Id",
            )

        message = _build_mime_message(
            to, subject, body, cc=cc,
            in_reply_to=original_message_id,
        )
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        result = _retry_transient(
            service.users().drafts().create(
                userId="me",
                body={
                    "message": {
                        "raw": raw,
                        "threadId": thread_id,
                    }
                },
            ).execute,
        )
        msg = result.get("message", {}) or {}
        return {
            "draft_id": result.get("id", ""),
            "message_id": msg.get("id", ""),
            "thread_id": msg.get("threadId", ""),
        }

    return await asyncio.to_thread(_create)
