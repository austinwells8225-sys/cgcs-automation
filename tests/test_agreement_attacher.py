"""Tests for the agreement attacher — internal/external classification + PDF load."""

from __future__ import annotations

import pytest

from app.services.agreement_attacher import (
    INTERNAL_PDF,
    EXTERNAL_PDF,
    build_agreement_attachment,
    is_internal_sender,
    select_agreement_path,
)


# --- is_internal_sender ---

@pytest.mark.parametrize("email", [
    "austin.wells@austincc.edu",
    "AUSTIN.WELLS@AUSTINCC.EDU",
    "michelle.raymond@austincc.edu",
    "admin@cgcs-acc.org",
    "bryan.port@austincc.edu",
    "  someone@austincc.edu  ",
])
def test_is_internal_sender_recognizes_acc_domains(email):
    assert is_internal_sender(email) is True


@pytest.mark.parametrize("email", [
    "renter@gmail.com",
    "events@nonprofit.org",
    "ceo@randomcompany.com",
    "person@ut.edu",  # Other .edu — still external for our purposes
    "person@texas.gov",
])
def test_is_internal_sender_rejects_external_domains(email):
    assert is_internal_sender(email) is False


@pytest.mark.parametrize("email", ["", None, "notanemail", "@nodomain"])
def test_is_internal_sender_handles_garbage(email):
    assert is_internal_sender(email) is False


# --- select_agreement_path ---

def test_select_agreement_path_internal():
    assert select_agreement_path("austin.wells@austincc.edu") == INTERNAL_PDF


def test_select_agreement_path_external():
    assert select_agreement_path("renter@gmail.com") == EXTERNAL_PDF


def test_select_agreement_path_garbage_defaults_to_external():
    # Unknown sender domain = treat as external (safer — they get the
    # full agreement; an internal user accidentally getting external is
    # an obvious-to-fix issue, while the reverse leaves a legal gap).
    assert select_agreement_path("") == EXTERNAL_PDF


# --- build_agreement_attachment ---

def test_build_attachment_internal_returns_pdf_dict():
    attachment = build_agreement_attachment("austin.wells@austincc.edu")
    assert attachment is not None
    assert attachment["filename"] == "CGCS Internal User Agreement.pdf"
    assert attachment["mime_type"] == "application/pdf"
    assert isinstance(attachment["content"], bytes)
    assert attachment["content"][:4] == b"%PDF"  # PDF magic bytes


def test_build_attachment_external_returns_pdf_dict():
    attachment = build_agreement_attachment("renter@gmail.com")
    assert attachment is not None
    assert attachment["filename"] == "CGCS External User Agreement.pdf"
    assert attachment["mime_type"] == "application/pdf"
    assert isinstance(attachment["content"], bytes)
    assert attachment["content"][:4] == b"%PDF"


def test_build_attachment_handles_missing_pdf(monkeypatch, tmp_path):
    """If the PDF file is gone, we log + return None, never raise."""
    from app.services import agreement_attacher
    monkeypatch.setattr(
        agreement_attacher,
        "EXTERNAL_PDF",
        tmp_path / "does-not-exist.pdf",
    )
    monkeypatch.setattr(
        agreement_attacher,
        "INTERNAL_PDF",
        tmp_path / "does-not-exist.pdf",
    )
    assert agreement_attacher.build_agreement_attachment("renter@gmail.com") is None
