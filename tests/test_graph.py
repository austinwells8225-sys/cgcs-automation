"""Unit tests for LangGraph agent nodes and edges."""

from unittest.mock import MagicMock, patch

from app.graph.edges import after_eligibility, after_validation
from app.graph.nodes import handle_error, validate_input


class TestValidateInput:
    def test_valid_request(self, sample_request):
        result = validate_input(sample_request)
        assert result["errors"] == []

    def test_missing_required_fields(self, invalid_request):
        result = validate_input(invalid_request)
        errors = result["errors"]
        assert any("request_id" in e for e in errors)
        assert any("requester_name" in e for e in errors)
        assert any("event_name" in e for e in errors)

    def test_invalid_date_format(self, invalid_request):
        result = validate_input(invalid_request)
        assert any("date format" in e for e in result["errors"])

    def test_start_after_end(self, invalid_request):
        result = validate_input(invalid_request)
        assert any("Start time" in e for e in result["errors"])

    def test_invalid_email(self, invalid_request):
        result = validate_input(invalid_request)
        assert any("email" in e.lower() for e in result["errors"])

    def test_attendees_out_of_range(self):
        state = {
            "request_id": "test",
            "requester_name": "Test",
            "requester_email": "test@test.com",
            "event_name": "Test Event",
            "requested_date": "2026-04-15",
            "requested_start_time": "09:00",
            "requested_end_time": "12:00",
            "estimated_attendees": 1000,
            "errors": [],
        }
        result = validate_input(state)
        assert any("attendees" in e.lower() for e in result["errors"])

    def test_unknown_room_type(self):
        state = {
            "request_id": "test",
            "requester_name": "Test",
            "requester_email": "test@test.com",
            "event_name": "Test Event",
            "requested_date": "2026-04-15",
            "requested_start_time": "09:00",
            "requested_end_time": "12:00",
            "room_requested": "nonexistent_room",
            "errors": [],
        }
        result = validate_input(state)
        assert any("Unknown room" in e for e in result["errors"])


class TestEdgeRouting:
    def test_after_validation_with_errors(self):
        state = {"errors": ["some error"]}
        assert after_validation(state) == "handle_error"

    def test_after_validation_no_errors(self):
        state = {"errors": []}
        assert after_validation(state) == "evaluate_eligibility"

    def test_after_eligibility_ineligible(self):
        state = {"is_eligible": False}
        assert after_eligibility(state) == "draft_rejection"

    def test_after_eligibility_eligible(self):
        state = {"is_eligible": True}
        assert after_eligibility(state) == "determine_pricing"

    def test_after_eligibility_needs_review(self):
        state = {"decision": "needs_review"}
        assert after_eligibility(state) == "handle_error"


class TestHandleError:
    def test_generates_review_response(self, sample_request):
        sample_request["errors"] = ["Test error 1", "Test error 2"]
        result = handle_error(sample_request)
        assert result["decision"] == "needs_review"
        assert "manual review" in result["draft_response"].lower()
        assert "Test error 1" in result["draft_response"]
        assert "Test error 2" in result["draft_response"]


class TestEvaluateEligibility:
    @patch("app.graph.nodes.llm")
    def test_eligible_government_agency(self, mock_llm, sample_request):
        mock_response = MagicMock()
        mock_response.content = '{"is_eligible": true, "reason": "Government agency", "tier_suggestion": "government_agency"}'
        mock_llm.invoke.return_value = mock_response

        from app.graph.nodes import evaluate_eligibility

        result = evaluate_eligibility(sample_request)
        assert result["is_eligible"] is True
        assert result["pricing_tier"] == "government_agency"

    @patch("app.graph.nodes.llm")
    def test_ineligible_commercial(self, mock_llm, ineligible_request):
        mock_response = MagicMock()
        mock_response.content = '{"is_eligible": false, "reason": "Purely commercial event", "tier_suggestion": "external"}'
        mock_llm.invoke.return_value = mock_response

        from app.graph.nodes import evaluate_eligibility

        result = evaluate_eligibility(ineligible_request)
        assert result["is_eligible"] is False

    @patch("app.graph.nodes.llm")
    def test_handles_malformed_response(self, mock_llm, sample_request):
        mock_response = MagicMock()
        mock_response.content = "This is not JSON"
        mock_llm.invoke.return_value = mock_response

        from app.graph.nodes import evaluate_eligibility

        result = evaluate_eligibility(sample_request)
        assert result["decision"] == "needs_review"


class TestDeterminePricing:
    @patch("app.graph.nodes.llm")
    def test_government_pricing(self, mock_llm, sample_request):
        mock_response = MagicMock()
        mock_response.content = '{"pricing_tier": "government_agency", "justification": "State agency"}'
        mock_llm.invoke.return_value = mock_response
        sample_request["pricing_tier"] = "government_agency"

        from app.graph.nodes import determine_pricing

        result = determine_pricing(sample_request)
        assert result["pricing_tier"] == "government_agency"
        assert result["estimated_cost"] == 0.0

    @patch("app.graph.nodes.llm")
    def test_nonprofit_pricing(self, mock_llm):
        mock_response = MagicMock()
        mock_response.content = '{"pricing_tier": "nonprofit", "justification": "501c3 org"}'
        mock_llm.invoke.return_value = mock_response

        state = {
            "request_id": "test",
            "requester_name": "Test",
            "requester_email": "test@nonprofit.org",
            "event_name": "Community Workshop",
            "requested_date": "2026-04-15",
            "requested_start_time": "09:00",
            "requested_end_time": "12:00",
            "pricing_tier": "nonprofit",
            "errors": [],
        }

        from app.graph.nodes import determine_pricing

        result = determine_pricing(state)
        assert result["pricing_tier"] == "nonprofit"
        # 3 hours * $25/hr = $75
        assert result["estimated_cost"] == 75.0
