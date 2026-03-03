"""Tests for Step 1A — automatic acknowledgment email."""

from app.cgcs_constants import build_acknowledgment_email


class TestBuildAcknowledgmentEmail:
    def test_basic_acknowledgment(self):
        result = build_acknowledgment_email("Jane Doe")
        assert result["subject"] == "Thank You — CGCS Event Request Received"
        assert "Hi Jane," in result["body"]
        assert "CGCS Team" in result["body"]

    def test_first_name_extraction_from_multipart_name(self):
        result = build_acknowledgment_email("Maria Elena Garcia de Lopez")
        assert "Hi Maria," in result["body"]
        assert "Garcia" not in result["body"].split(",")[0]

    def test_empty_name_fallback(self):
        result = build_acknowledgment_email("")
        assert "Hi there," in result["body"]
        assert "CGCS Team" in result["body"]
