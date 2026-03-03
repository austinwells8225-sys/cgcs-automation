"""Tests for email rejection / self-improving draft system."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.prompt_tuning import get_rejection_lessons

client = TestClient(app)

AUTH_HEADERS = {"Authorization": f"Bearer {settings.langgraph_api_key}"} if settings.langgraph_api_key else {}
WEBHOOK_HEADERS = {"X-Webhook-Secret": settings.webhook_secret} if settings.webhook_secret else {}

MOCK_REVISIONS = [
    {"label": "Conservative", "draft": "Dear Sir, revised version 1..."},
    {"label": "Moderate", "draft": "Hello, revised version 2..."},
    {"label": "Bold", "draft": "Hi there, revised version 3..."},
]


class TestRejectAndReworkEndpoint:
    @patch("app.main.create_rejection_pattern", new_callable=AsyncMock)
    @patch("app.main._parse_json_response")
    @patch("app.main._invoke_with_retry")
    def test_reject_and_rework_returns_revisions(
        self, mock_invoke, mock_parse, mock_create
    ):
        mock_invoke.return_value = '{"revisions": [...]}'
        mock_parse.return_value = {"revisions": MOCK_REVISIONS}
        mock_create.return_value = 42

        response = client.post(
            "/api/v1/email/reject-and-rework/email-123",
            headers=AUTH_HEADERS,
            json={
                "rejection_reason": "Too formal",
                "email_from": "test@example.com",
                "email_subject": "Room inquiry",
                "original_draft": "Dear Sir/Madam, I am writing...",
                "category": "question",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email_id"] == "email-123"
        assert data["pattern_id"] == 42
        assert len(data["revisions"]) == 3
        assert data["revisions"][0]["label"] == "Conservative"
        mock_create.assert_called_once()

    @patch("app.main._invoke_with_retry")
    def test_reject_and_rework_handles_llm_failure(self, mock_invoke):
        mock_invoke.side_effect = ConnectionError("LLM down")

        response = client.post(
            "/api/v1/email/reject-and-rework/email-123",
            headers=AUTH_HEADERS,
            json={
                "rejection_reason": "Too formal",
            },
        )

        assert response.status_code == 502

    def test_reject_and_rework_rejects_missing_reason(self):
        response = client.post(
            "/api/v1/email/reject-and-rework/email-123",
            headers=AUTH_HEADERS,
            json={},
        )
        assert response.status_code == 422


class TestSelectRevisionEndpoint:
    @patch("app.main.select_revision", new_callable=AsyncMock)
    @patch("app.main.get_rejection_patterns", new_callable=AsyncMock)
    def test_select_revision_by_index(self, mock_patterns, mock_select):
        mock_patterns.return_value = [
            {
                "id": 42,
                "revision_options": MOCK_REVISIONS,
            }
        ]
        mock_select.return_value = True

        response = client.post(
            "/api/v1/email/select-revision/42",
            headers=AUTH_HEADERS,
            json={"revision_index": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pattern_id"] == 42
        assert data["status"] == "revision_selected"
        assert "revised version 2" in data["final_draft"]

    @patch("app.main.select_revision", new_callable=AsyncMock)
    def test_select_revision_custom_draft(self, mock_select):
        mock_select.return_value = True

        response = client.post(
            "/api/v1/email/select-revision/42",
            headers=AUTH_HEADERS,
            json={"final_draft": "My completely custom reply."},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["final_draft"] == "My completely custom reply."

    def test_select_revision_requires_index_or_draft(self):
        response = client.post(
            "/api/v1/email/select-revision/42",
            headers=AUTH_HEADERS,
            json={},
        )
        assert response.status_code == 422

    @patch("app.main.select_revision", new_callable=AsyncMock)
    def test_select_revision_pattern_not_found(self, mock_select):
        mock_select.return_value = False

        response = client.post(
            "/api/v1/email/select-revision/999",
            headers=AUTH_HEADERS,
            json={"final_draft": "Some draft"},
        )
        assert response.status_code == 404


class TestRejectionInsightsEndpoint:
    @patch("app.main.get_rejection_insights", new_callable=AsyncMock)
    def test_rejection_insights(self, mock_insights):
        mock_insights.return_value = {
            "total_rejections": 15,
            "improvement_rate": 73.3,
            "top_reasons": [
                {"reason": "Too formal", "count": 8},
                {"reason": "Missing details", "count": 5},
            ],
            "category_breakdown": [
                {"category": "question", "count": 10},
                {"category": "event_request", "count": 5},
            ],
        }

        response = client.get(
            "/api/v1/email/rejection-insights",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_rejections"] == 15
        assert data["improvement_rate"] == 73.3
        assert len(data["top_reasons"]) == 2

    @patch("app.main.get_rejection_insights", new_callable=AsyncMock)
    def test_rejection_insights_with_category_filter(self, mock_insights):
        mock_insights.return_value = {
            "total_rejections": 5,
            "improvement_rate": 80.0,
            "top_reasons": [{"reason": "Too formal", "count": 5}],
            "category_breakdown": [{"category": "question", "count": 5}],
        }

        response = client.get(
            "/api/v1/email/rejection-insights?category=question",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        mock_insights.assert_called_once_with(category="question")


class TestEmailApproveWithRejectionReason:
    @patch("app.main.create_rejection_pattern", new_callable=AsyncMock)
    @patch("app.main._parse_json_response")
    @patch("app.main._invoke_with_retry")
    def test_reject_with_reason_triggers_rework(
        self, mock_invoke, mock_parse, mock_create
    ):
        mock_invoke.return_value = '{"revisions": [...]}'
        mock_parse.return_value = {"revisions": MOCK_REVISIONS}
        mock_create.return_value = 7

        response = client.post(
            "/api/v1/email/approve/email-456",
            headers=AUTH_HEADERS,
            json={
                "action": "reject",
                "rejection_reason": "Tone is wrong",
                "edited_reply": "Original draft text here",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rework_generated"
        assert data["pattern_id"] == 7
        assert len(data["revisions"]) == 3

    def test_reject_without_reason_returns_simple_status(self):
        response = client.post(
            "/api/v1/email/approve/email-456",
            headers=AUTH_HEADERS,
            json={"action": "reject"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert "revisions" not in data

    def test_approve_still_works(self):
        response = client.post(
            "/api/v1/email/approve/email-456",
            headers=AUTH_HEADERS,
            json={"action": "approve"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"


class TestEmailTriageWithLessons:
    @patch("app.main.compiled_graph")
    @patch("app.main.get_rejection_lessons", new_callable=AsyncMock)
    def test_lessons_injected_into_initial_state(self, mock_lessons, mock_graph):
        mock_lessons.return_value = "## Past Rejection Lessons\n1. Avoid being too formal."
        mock_graph.invoke.return_value = {
            "email_priority": "medium",
            "email_category": "question",
            "email_draft_reply": "Hello!",
            "email_auto_send": False,
            "decision": "needs_review",
            "errors": [],
        }

        response = client.post(
            "/api/v1/email/triage",
            headers=WEBHOOK_HEADERS,
            json={
                "email_from": "test@example.com",
                "email_subject": "Question",
                "email_body": "What are your hours?",
            },
        )

        assert response.status_code == 200
        # Verify the lessons were passed to graph invoke
        call_args = mock_graph.invoke.call_args
        state = call_args[0][0]
        assert state["email_rejection_lessons"] == "## Past Rejection Lessons\n1. Avoid being too formal."

    @patch("app.main.compiled_graph")
    @patch("app.main.get_rejection_lessons", new_callable=AsyncMock)
    def test_lessons_failure_doesnt_block_triage(self, mock_lessons, mock_graph):
        mock_lessons.side_effect = ConnectionError("DB down")
        mock_graph.invoke.return_value = {
            "email_priority": "medium",
            "email_category": "question",
            "email_draft_reply": "Hello!",
            "email_auto_send": False,
            "decision": "needs_review",
            "errors": [],
        }

        response = client.post(
            "/api/v1/email/triage",
            headers=WEBHOOK_HEADERS,
            json={
                "email_from": "test@example.com",
                "email_subject": "Question",
                "email_body": "What are your hours?",
            },
        )

        assert response.status_code == 200
        # Lessons should be empty string when fetch fails
        call_args = mock_graph.invoke.call_args
        state = call_args[0][0]
        assert state["email_rejection_lessons"] == ""


class TestGetRejectionLessons:
    @patch("app.prompt_tuning.get_rejection_patterns", new_callable=AsyncMock)
    def test_no_patterns_returns_empty(self, mock_patterns):
        import asyncio
        mock_patterns.return_value = []
        result = asyncio.get_event_loop().run_until_complete(get_rejection_lessons())
        assert result == ""

    @patch("app.prompt_tuning.get_rejection_patterns", new_callable=AsyncMock)
    def test_patterns_format_correctly(self, mock_patterns):
        import asyncio
        mock_patterns.return_value = [
            {
                "rejection_reason": "Too formal",
                "selected_revision_index": 1,
                "final_draft": "Better version",
            },
            {
                "rejection_reason": "Missing details",
                "selected_revision_index": None,
                "final_draft": "Custom rewrite",
            },
        ]
        result = asyncio.get_event_loop().run_until_complete(get_rejection_lessons())
        assert "Past Rejection Lessons" in result
        assert "Too formal" in result
        assert "chose revision #2" in result
        assert "custom replacement" in result

    @patch("app.prompt_tuning.get_rejection_patterns", new_callable=AsyncMock)
    def test_db_error_returns_empty(self, mock_patterns):
        import asyncio
        mock_patterns.side_effect = ConnectionError("DB down")
        result = asyncio.get_event_loop().run_until_complete(get_rejection_lessons())
        assert result == ""

    @patch("app.prompt_tuning.get_rejection_patterns", new_callable=AsyncMock)
    def test_unresolved_pattern(self, mock_patterns):
        import asyncio
        mock_patterns.return_value = [
            {
                "rejection_reason": "Needs work",
                "selected_revision_index": None,
                "final_draft": None,
            },
        ]
        result = asyncio.get_event_loop().run_until_complete(get_rejection_lessons())
        assert "No resolution selected yet" in result


class TestDraftEmailReplyWithLessons:
    @patch("app.graph.nodes.shared.llm")
    def test_lessons_appended_to_system_prompt(self, mock_llm):
        from app.graph.nodes.email_triage import draft_email_reply

        mock_response = MagicMock()
        mock_response.content = "Thank you for your inquiry..."
        mock_llm.invoke.return_value = mock_response

        state = {
            "email_from": "user@org.com",
            "email_subject": "Question",
            "email_body": "What rooms are available?",
            "email_category": "question",
            "email_priority": "medium",
            "email_rejection_lessons": "## Past Lessons\n1. Be warmer in tone.",
            "errors": [],
        }
        result = draft_email_reply(state)

        # Verify the system prompt included the lessons
        call_args = mock_llm.invoke.call_args[0][0]
        system_msg = call_args[0]  # first message dict
        assert "Past Lessons" in system_msg["content"]

    @patch("app.graph.nodes.shared.llm")
    def test_no_lessons_uses_default_prompt(self, mock_llm):
        from app.graph.nodes.email_triage import draft_email_reply
        from app.prompts.templates import EMAIL_TRIAGE_SYSTEM_PROMPT

        mock_response = MagicMock()
        mock_response.content = "Thank you..."
        mock_llm.invoke.return_value = mock_response

        state = {
            "email_from": "user@org.com",
            "email_subject": "Question",
            "email_body": "What rooms?",
            "email_category": "question",
            "email_priority": "medium",
            "errors": [],
        }
        result = draft_email_reply(state)

        call_args = mock_llm.invoke.call_args[0][0]
        system_msg = call_args[0]  # first message dict
        # Should use the base prompt without any lessons appended
        assert system_msg["content"] == EMAIL_TRIAGE_SYSTEM_PROMPT
