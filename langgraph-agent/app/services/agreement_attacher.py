"""Pick the right CGCS user-agreement PDF and load it as a Gmail attachment.

Used by the email-triage draft step when the classifier flags an incoming
message as an initial event-space reachout. Internal ACC senders get the
internal agreement; everyone else gets the external (with the additional
clauses for outside-org rentals).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

INTERNAL_DOMAINS = frozenset({
    "austincc.edu",
    "cgcs-acc.org",
})

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets" / "agreements"
INTERNAL_PDF = ASSETS_DIR / "cgcs_internal_user_agreement.pdf"
EXTERNAL_PDF = ASSETS_DIR / "cgcs_external_user_agreement.pdf"


def _domain(email: str) -> str:
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].strip().lower().rstrip(">")


def is_internal_sender(email_from: str) -> bool:
    """Return True if the sender's domain is an ACC/CGCS domain."""
    return _domain(email_from) in INTERNAL_DOMAINS


def select_agreement_path(email_from: str) -> Path:
    """Pick the internal or external agreement PDF for this sender."""
    return INTERNAL_PDF if is_internal_sender(email_from) else EXTERNAL_PDF


def build_agreement_attachment(email_from: str) -> dict | None:
    """Load the right agreement PDF as an attachment dict for gmail_service.

    Returns a dict shaped for `_build_mime_message`'s `attachments=` param,
    or None if the PDF file is missing on disk (logged, not raised, so a
    deployment without the assets bundled doesn't 500 the whole pipeline).
    """
    path = select_agreement_path(email_from)
    if not path.exists():
        logger.error("Agreement PDF missing: %s", path)
        return None

    label = "Internal" if is_internal_sender(email_from) else "External"
    filename = f"CGCS {label} User Agreement.pdf"
    return {
        "filename": filename,
        "content": path.read_bytes(),
        "mime_type": "application/pdf",
    }
