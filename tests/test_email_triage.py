"""Unit tests for email triage nodes."""

from unittest.mock import MagicMock, patch

from app.graph.nodes.email_triage import (
    AUTO_SEND_ALLOWLIST,
    check_auto_send,
    classify_email,
    draft_email_reply,
)


class TestClassifyEmail:
    @patch("app.graph.nodes.shared.llm")
    def test_classifies_event_request(self, mock_llm):
        mock_response = MagicMock()
        mock_response.content = '{"priority": "medium", "category": "event_request", "reasoning": "Reservation inquiry"}'
        mock_llm.invoke.return_value = mock_response

        state = {
            "email_from": "user@org.com",
            "email_subject": "Reserve event hall",
            "email_body": "I'd like to book the event hall for a conference.",
            "errors": [],
        }
        result = classify_email(state)
        assert result["email_priority"] == "medium"
        assert result["email_category"] == "event_request"

    @patch("app.graph.nodes.shared.llm")
    def test_classifies_high_priority(self, mock_llm):
        mock_response = MagicMock()
        mock_response.content = '{"priority": "high", "category": "complaint", "reasoning": "Urgent complaint"}'
        mock_llm.invoke.return_value = mock_response

        state = {
            "email_from": "official@txgov.gov",
            "email_subject": "Complaint about facilities",
            "email_body": "There was an issue with our event last week.",
            "errors": [],
        }
        result = classify_email(state)
        assert result["email_priority"] == "high"
        assert result["email_category"] == "complaint"

    def test_empty_email_returns_error(self):
        state = {
            "email_from": "test@test.com",
            "email_subject": "",
            "email_body": "",
            "errors": [],
        }
        result = classify_email(state)
        assert result["decision"] == "needs_review"
        assert any("no subject or body" in e.lower() for e in result.get("errors", []))

    @patch("app.graph.nodes.shared.llm")
    def test_handles_malformed_response(self, mock_llm):
        mock_response = MagicMock()
        mock_response.content = "Not valid JSON at all"
        mock_llm.invoke.return_value = mock_response

        state = {
            "email_from": "test@test.com",
            "email_subject": "Test",
            "email_body": "Test body",
            "errors": [],
        }
        result = classify_email(state)
        assert result["email_priority"] == "medium"
        assert result["email_category"] == "other"


class TestDraftEmailReply:
    @patch("app.graph.nodes.shared.llm")
    def test_drafts_reply(self, mock_llm):
        mock_response = MagicMock()
        mock_response.content = "Thank you for your inquiry. We'd be happy to help..."
        mock_llm.invoke.return_value = mock_response

        state = {
            "email_from": "user@org.com",
            "email_subject": "Question about rooms",
            "email_body": "What rooms are available?",
            "email_category": "question",
            "email_priority": "medium",
            "errors": [],
        }
        result = draft_email_reply(state)
        assert result["email_draft_reply"] is not None
        assert result["requires_approval"] is True

    @patch("app.graph.nodes.shared.llm")
    def test_handles_llm_failure(self, mock_llm):
        mock_llm.invoke.side_effect = ConnectionError("API down")

        state = {
            "email_from": "user@org.com",
            "email_subject": "Test",
            "email_body": "Test body",
            "email_category": "question",
            "email_priority": "medium",
            "errors": [],
        }
        result = draft_email_reply(state)
        assert result["decision"] == "needs_review"


class TestCheckAutoSend:
    def test_allowlisted_sender(self):
        state = {
            "email_from": "stefano.casafrancalaos@austincc.edu",
            "email_draft_reply": "Reply content",
            "errors": [],
        }
        result = check_auto_send(state)
        assert result["email_auto_send"] is True
        assert result["approved"] is True

    def test_non_allowlisted_sender(self):
        state = {
            "email_from": "random@external.com",
            "email_draft_reply": "Reply content",
            "errors": [],
        }
        result = check_auto_send(state)
        assert result["email_auto_send"] is False
        assert result["requires_approval"] is True

    def test_allowlist_contains_expected_addresses(self):
        assert "stefano.casafrancalaos@austincc.edu" in AUTO_SEND_ALLOWLIST
        assert "marisela.perez@austincc.edu" in AUTO_SEND_ALLOWLIST

    def test_case_insensitive_match(self):
        state = {
            "email_from": "  Stefano.Casafrancalaos@austincc.edu  ",
            "errors": [],
        }
        result = check_auto_send(state)
        assert result["email_auto_send"] is True
