"""Tests for process insights, quarterly reports, and daily digest stats."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.process_insights import (
    build_quarterly_report,
    generate_recommendations,
    get_monthly_quick_stats,
)

client = TestClient(app)

AUTH_HEADERS = (
    {"Authorization": f"Bearer {settings.langgraph_api_key}"}
    if settings.langgraph_api_key
    else {}
)


# ============================================================
# Unit tests for get_email_metrics
# ============================================================


class TestGetEmailMetrics:
    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_email_metrics_with_data(self, mock_pool):
        from app.services.process_insights import get_email_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        # Summary query
        pool.fetchrow.side_effect = [
            {"total_drafts": 20, "rejected_count": 4},  # summary
            {"avg_revisions": 1.5},  # revisions
            {  # improvement trend
                "first_half_total": 10,
                "first_half_rejected": 3,
                "second_half_total": 10,
                "second_half_rejected": 1,
            },
        ]
        pool.fetch.return_value = [
            {"category": "too_formal", "count": 3},
            {"category": "missing_info", "count": 1},
        ]

        result = asyncio.get_event_loop().run_until_complete(
            get_email_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["total_drafts"] == 20
        assert result["rejection_rate"] == 20.0
        assert result["avg_revisions_per_email"] == 1.5
        assert len(result["top_rejection_reasons"]) == 2
        assert result["improvement_trend"]["first_half_rejection_rate"] == 30.0
        assert result["improvement_trend"]["second_half_rejection_rate"] == 10.0

    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_email_metrics_empty(self, mock_pool):
        from app.services.process_insights import get_email_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.side_effect = [
            {"total_drafts": 0, "rejected_count": 0},
            {"avg_revisions": 0},
            {
                "first_half_total": 0,
                "first_half_rejected": 0,
                "second_half_total": 0,
                "second_half_rejected": 0,
            },
        ]
        pool.fetch.return_value = []

        result = asyncio.get_event_loop().run_until_complete(
            get_email_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["total_drafts"] == 0
        assert result["rejection_rate"] == 0.0
        assert result["top_rejection_reasons"] == []

    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_email_metrics_improvement_trend(self, mock_pool):
        from app.services.process_insights import get_email_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.side_effect = [
            {"total_drafts": 40, "rejected_count": 12},
            {"avg_revisions": 2.0},
            {
                "first_half_total": 20,
                "first_half_rejected": 8,
                "second_half_total": 20,
                "second_half_rejected": 4,
            },
        ]
        pool.fetch.return_value = []

        result = asyncio.get_event_loop().run_until_complete(
            get_email_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["improvement_trend"]["first_half_rejection_rate"] == 40.0
        assert result["improvement_trend"]["second_half_rejection_rate"] == 20.0


# ============================================================
# Unit tests for get_quote_metrics
# ============================================================


class TestGetQuoteMetrics:
    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_quote_metrics_with_data(self, mock_pool):
        from app.services.process_insights import get_quote_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.side_effect = [
            {"total_quotes": 8, "avg_revisions": 2.3},  # summary
            {"avg_increase_pct": 15.5},  # increase
        ]
        pool.fetch.return_value = [
            {"service": "av_equipment", "add_count": 5},
        ]

        result = asyncio.get_event_loop().run_until_complete(
            get_quote_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["total_quotes"] == 8
        assert result["avg_revisions_per_quote"] == 2.3
        assert result["most_added_service"] == "av_equipment"
        assert result["avg_quote_increase_pct"] == 15.5

    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_quote_metrics_empty(self, mock_pool):
        from app.services.process_insights import get_quote_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.side_effect = [
            {"total_quotes": 0, "avg_revisions": 0},
            {"avg_increase_pct": 0},
        ]
        pool.fetch.return_value = []

        result = asyncio.get_event_loop().run_until_complete(
            get_quote_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["total_quotes"] == 0
        assert result["most_added_service"] is None
        assert result["avg_quote_increase_pct"] == 0.0

    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_quote_increase_percentage(self, mock_pool):
        from app.services.process_insights import get_quote_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.side_effect = [
            {"total_quotes": 3, "avg_revisions": 1.7},
            {"avg_increase_pct": 22.8},
        ]
        pool.fetch.return_value = [{"service": "police", "add_count": 2}]

        result = asyncio.get_event_loop().run_until_complete(
            get_quote_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["avg_quote_increase_pct"] == 22.8


# ============================================================
# Unit tests for get_turnaround_metrics
# ============================================================


class TestGetTurnaroundMetrics:
    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_turnaround_with_data(self, mock_pool):
        from app.services.process_insights import get_turnaround_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.return_value = {
            "avg_intake_to_response_hours": 4.5,
            "avg_intake_to_approval_days": 1.2,
            "avg_intake_to_event_days": 21.0,
        }

        result = asyncio.get_event_loop().run_until_complete(
            get_turnaround_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["avg_intake_to_response_hours"] == 4.5
        assert result["avg_intake_to_approval_days"] == 1.2
        assert result["avg_intake_to_event_days"] == 21.0

    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_turnaround_no_data(self, mock_pool):
        from app.services.process_insights import get_turnaround_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.return_value = {
            "avg_intake_to_response_hours": 0,
            "avg_intake_to_approval_days": 0,
            "avg_intake_to_event_days": 0,
        }

        result = asyncio.get_event_loop().run_until_complete(
            get_turnaround_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["avg_intake_to_response_hours"] == 0.0
        assert result["avg_intake_to_approval_days"] == 0.0


# ============================================================
# Unit tests for get_compliance_metrics
# ============================================================


class TestGetComplianceMetrics:
    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_compliance_with_data(self, mock_pool):
        from app.services.process_insights import get_compliance_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.return_value = {
            "total_items": 50,
            "on_time_items": 40,
            "completed_items": 45,
            "items_never_completed": 3,
        }
        pool.fetch.return_value = [
            {
                "item_key": "tdx_av",
                "item_label": "TDX AV Request",
                "overdue_count": 5,
                "avg_days_overdue": 3.2,
            },
            {
                "item_key": "walkthrough",
                "item_label": "Walkthrough",
                "overdue_count": 2,
                "avg_days_overdue": 1.5,
            },
        ]

        result = asyncio.get_event_loop().run_until_complete(
            get_compliance_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["on_time_rate"] == 80.0
        assert result["items_never_completed"] == 3
        assert len(result["most_overdue_items"]) == 2
        assert result["most_overdue_items"][0]["item_key"] == "tdx_av"

    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_compliance_empty(self, mock_pool):
        from app.services.process_insights import get_compliance_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.return_value = {
            "total_items": 0,
            "on_time_items": 0,
            "completed_items": 0,
            "items_never_completed": 0,
        }
        pool.fetch.return_value = []

        result = asyncio.get_event_loop().run_until_complete(
            get_compliance_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["on_time_rate"] == 0.0
        assert result["most_overdue_items"] == []

    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_compliance_overdue_ranking(self, mock_pool):
        from app.services.process_insights import get_compliance_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.return_value = {
            "total_items": 30,
            "on_time_items": 20,
            "completed_items": 25,
            "items_never_completed": 2,
        }
        pool.fetch.return_value = [
            {"item_key": "catering", "item_label": "Catering", "overdue_count": 8, "avg_days_overdue": 5.0},
            {"item_key": "tdx_av", "item_label": "TDX AV", "overdue_count": 3, "avg_days_overdue": 2.0},
        ]

        result = asyncio.get_event_loop().run_until_complete(
            get_compliance_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["most_overdue_items"][0]["overdue_count"] == 8
        assert result["avg_overdue_days_per_item"][0]["avg_days"] == 5.0


# ============================================================
# Unit tests for get_conversion_funnel_metrics
# ============================================================


class TestGetConversionFunnel:
    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_funnel_with_data(self, mock_pool):
        from app.services.process_insights import get_conversion_funnel_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.return_value = {
            "submitted": 20,
            "approved": 14,
            "completed": 10,
            "cancelled": 2,
            "rejected": 4,
        }

        result = asyncio.get_event_loop().run_until_complete(
            get_conversion_funnel_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["submitted"] == 20
        assert result["completed"] == 10
        assert result["conversion_rate"] == 50.0

    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_funnel_empty(self, mock_pool):
        from app.services.process_insights import get_conversion_funnel_metrics

        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.return_value = {
            "submitted": 0,
            "approved": 0,
            "completed": 0,
            "cancelled": 0,
            "rejected": 0,
        }

        result = asyncio.get_event_loop().run_until_complete(
            get_conversion_funnel_metrics(date(2026, 1, 1), date(2026, 4, 1))
        )

        assert result["submitted"] == 0
        assert result["conversion_rate"] == 0.0


# ============================================================
# Unit tests for generate_recommendations
# ============================================================


class TestGenerateRecommendations:
    @patch("app.services.process_insights._invoke_with_retry")
    def test_recommendations_with_data(self, mock_invoke):
        mock_invoke.return_value = '{"recommendations": ["Reduce email turnaround by 20%", "Add auto-reminders for TDX deadlines", "Streamline quote process for repeat clients"]}'

        metrics = {
            "email": {"total_drafts": 20, "rejection_rate": 15.0},
            "conversion": {"submitted": 10, "completed": 7},
            "compliance": {"on_time_rate": 85.0},
        }

        result = generate_recommendations(metrics)

        assert len(result) == 3
        assert "turnaround" in result[0].lower()

    def test_recommendations_empty_data(self):
        metrics = {
            "email": {"total_drafts": 0},
            "conversion": {"submitted": 0},
            "compliance": {"on_time_rate": 0},
        }

        result = generate_recommendations(metrics)

        assert len(result) == 3
        assert "insufficient" in result[0].lower() or "data" in result[0].lower()

    @patch("app.services.process_insights._invoke_with_retry")
    def test_recommendations_llm_failure(self, mock_invoke):
        mock_invoke.side_effect = ConnectionError("LLM down")

        metrics = {
            "email": {"total_drafts": 20, "rejection_rate": 15.0},
            "conversion": {"submitted": 10},
            "compliance": {"on_time_rate": 85.0},
        }

        result = generate_recommendations(metrics)

        assert len(result) == 3
        assert isinstance(result[0], str)


# ============================================================
# Unit tests for build_quarterly_report
# ============================================================


class TestBuildQuarterlyReport:
    @patch("app.services.process_insights.generate_recommendations")
    @patch("app.services.process_insights.get_top_organizations", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_revenue_report", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_conversion_funnel_metrics", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_compliance_metrics", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_turnaround_metrics", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_quote_metrics", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_email_metrics", new_callable=AsyncMock)
    def test_full_report(
        self, mock_email, mock_quote, mock_turnaround, mock_compliance,
        mock_conversion, mock_revenue, mock_orgs, mock_recs,
    ):
        mock_email.return_value = {"total_drafts": 20, "rejection_rate": 10.0}
        mock_quote.return_value = {"total_quotes": 5, "avg_revisions_per_quote": 1.8}
        mock_turnaround.return_value = {"avg_intake_to_response_hours": 3.0}
        mock_compliance.return_value = {"on_time_rate": 90.0}
        mock_conversion.return_value = {"submitted": 15, "completed": 10}
        mock_revenue.return_value = {"total_revenue": 5000.0}
        mock_orgs.return_value = [{"organization": "Texas DOE"}]
        mock_recs.return_value = ["Improve email drafts", "Add reminders"]

        result = asyncio.get_event_loop().run_until_complete(
            build_quarterly_report(date(2026, 1, 1))
        )

        assert result["period"] == "quarter"
        assert result["start"] == "2026-01-01"
        assert result["end"] == "2026-04-01"
        assert result["email"]["total_drafts"] == 20
        assert result["quotes"]["total_quotes"] == 5
        assert result["turnaround"]["avg_intake_to_response_hours"] == 3.0
        assert result["compliance"]["on_time_rate"] == 90.0
        assert result["conversion"]["submitted"] == 15
        assert result["revenue"]["total_revenue"] == 5000.0
        assert len(result["top_organizations"]) == 1
        assert len(result["recommendations"]) == 2

    @patch("app.services.process_insights.generate_recommendations")
    @patch("app.services.process_insights.get_top_organizations", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_revenue_report", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_conversion_funnel_metrics", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_compliance_metrics", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_turnaround_metrics", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_quote_metrics", new_callable=AsyncMock)
    @patch("app.services.process_insights.get_email_metrics", new_callable=AsyncMock)
    def test_partial_failure(
        self, mock_email, mock_quote, mock_turnaround, mock_compliance,
        mock_conversion, mock_revenue, mock_orgs, mock_recs,
    ):
        mock_email.side_effect = ConnectionError("DB down")
        mock_quote.return_value = {"total_quotes": 3}
        mock_turnaround.side_effect = ConnectionError("DB down")
        mock_compliance.return_value = {"on_time_rate": 75.0}
        mock_conversion.return_value = {"submitted": 5}
        mock_revenue.side_effect = ConnectionError("DB down")
        mock_orgs.return_value = []
        mock_recs.return_value = ["Generic recommendation"]

        result = asyncio.get_event_loop().run_until_complete(
            build_quarterly_report(date(2026, 1, 1))
        )

        # Partial data should still work
        assert result["email"] == {}  # Failed
        assert result["quotes"]["total_quotes"] == 3  # Succeeded
        assert result["turnaround"] == {}  # Failed
        assert result["compliance"]["on_time_rate"] == 75.0
        assert result["revenue"] == {}  # Failed
        assert len(result["recommendations"]) == 1


# ============================================================
# Endpoint tests for GET /api/v1/reports/process-insights
# ============================================================


class TestProcessInsightsEndpoint:
    @patch("app.main.build_quarterly_report", new_callable=AsyncMock)
    def test_process_insights_default(self, mock_report):
        mock_report.return_value = {
            "period": "quarter",
            "start": "2026-01-01",
            "end": "2026-04-01",
            "email": {"total_drafts": 20, "rejection_rate": 10.0},
            "quotes": {"total_quotes": 5},
            "turnaround": {"avg_intake_to_response_hours": 3.0},
            "compliance": {"on_time_rate": 90.0},
            "conversion": {"submitted": 15},
            "revenue": {"total_revenue": 5000.0},
            "top_organizations": [],
            "recommendations": ["Improve email drafts"],
        }

        response = client.get(
            "/api/v1/reports/process-insights?period=quarter&start=2026-01-01",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "quarter"
        assert data["email"]["total_drafts"] == 20
        assert len(data["recommendations"]) == 1

    @patch("app.main.build_quarterly_report", new_callable=AsyncMock)
    def test_process_insights_explicit_params(self, mock_report):
        mock_report.return_value = {
            "period": "month",
            "start": "2026-03-01",
            "end": "2026-04-01",
            "email": {},
            "quotes": {},
            "turnaround": {},
            "compliance": {},
            "conversion": {},
            "revenue": {},
            "top_organizations": [],
            "recommendations": [],
        }

        response = client.get(
            "/api/v1/reports/process-insights?period=month&start=2026-03-01",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200

    def test_process_insights_invalid_period(self):
        response = client.get(
            "/api/v1/reports/process-insights?period=decade&start=2026-01-01",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 400


# ============================================================
# Endpoint tests for POST /api/v1/reports/generate-quarterly
# ============================================================


class TestGenerateQuarterlyEndpoint:
    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    @patch("app.main.build_quarterly_report", new_callable=AsyncMock)
    def test_generate_no_email(self, mock_report, mock_audit):
        mock_report.return_value = {
            "period": "quarter",
            "start": "2026-01-01",
            "end": "2026-04-01",
            "email": {},
            "quotes": {},
            "turnaround": {},
            "compliance": {},
            "conversion": {},
            "revenue": {},
            "top_organizations": [],
            "recommendations": ["Recommendation 1"],
        }

        response = client.post(
            "/api/v1/reports/generate-quarterly",
            headers=AUTH_HEADERS,
            json={"quarter_start": "2026-01-01", "send_email": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email_sent"] is False
        assert data["report"]["period"] == "quarter"
        assert data["generated_at"] != ""

    @patch("app.main.add_audit_entry", new_callable=AsyncMock)
    @patch("app.main.build_quarterly_report", new_callable=AsyncMock)
    def test_generate_with_email(self, mock_report, mock_audit):
        mock_report.return_value = {
            "period": "quarter",
            "start": "2026-01-01",
            "end": "2026-04-01",
            "email": {},
            "quotes": {},
            "turnaround": {},
            "compliance": {},
            "conversion": {},
            "revenue": {},
            "top_organizations": [],
            "recommendations": [],
        }

        response = client.post(
            "/api/v1/reports/generate-quarterly",
            headers=AUTH_HEADERS,
            json={"quarter_start": "2026-01-01", "send_email": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email_sent"] is True
        mock_audit.assert_called_once()

    def test_generate_invalid_date(self):
        response = client.post(
            "/api/v1/reports/generate-quarterly",
            headers=AUTH_HEADERS,
            json={"quarter_start": "bad-date", "send_email": False},
        )

        assert response.status_code == 422  # Pydantic validation (regex pattern)


# ============================================================
# Daily digest with monthly stats
# ============================================================


class TestDailyDigestWithStats:
    @patch("app.main.compiled_graph")
    @patch("app.main.get_monthly_quick_stats", new_callable=AsyncMock)
    def test_stats_injected_into_digest(self, mock_stats, mock_graph):
        mock_stats.return_value = {
            "events_this_month": 12,
            "revenue_this_month": 3500.00,
            "pending_approvals": 3,
            "on_time_checklist_rate": 92.0,
        }
        mock_graph.invoke.return_value = {
            "draft_response": "Digest content here",
            "decision": "approve",
            "errors": [],
        }

        webhook_headers = (
            {"X-Webhook-Secret": settings.webhook_secret}
            if settings.webhook_secret
            else {}
        )

        response = client.post("/api/v1/daily-digest", headers=webhook_headers)

        assert response.status_code == 200

        # Verify stats were passed into state
        call_args = mock_graph.invoke.call_args
        state = call_args[0][0]
        assert state["digest_monthly_stats"]["events_this_month"] == 12
        assert state["digest_monthly_stats"]["revenue_this_month"] == 3500.00

    @patch("app.main.compiled_graph")
    @patch("app.main.get_monthly_quick_stats", new_callable=AsyncMock)
    def test_stats_failure_doesnt_block_digest(self, mock_stats, mock_graph):
        mock_stats.side_effect = ConnectionError("DB down")
        mock_graph.invoke.return_value = {
            "draft_response": "Digest content here",
            "decision": "approve",
            "errors": [],
        }

        webhook_headers = (
            {"X-Webhook-Secret": settings.webhook_secret}
            if settings.webhook_secret
            else {}
        )

        response = client.post("/api/v1/daily-digest", headers=webhook_headers)

        assert response.status_code == 200

        # Stats should be empty but digest still works
        call_args = mock_graph.invoke.call_args
        state = call_args[0][0]
        assert state["digest_monthly_stats"] == {}


# ============================================================
# Unit test for daily digest node (Section 9)
# ============================================================


class TestDailyDigestNode:
    def test_digest_includes_monthly_stats(self):
        from app.graph.nodes.daily_digest import build_daily_digest

        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_monthly_stats": {
                "events_this_month": 8,
                "revenue_this_month": 2500.00,
                "pending_approvals": 2,
                "on_time_checklist_rate": 88.5,
            },
        }

        result = build_daily_digest(state)
        body = result["draft_response"]

        assert "QUICK STATS" in body
        assert "Events this month: 8" in body
        assert "$2,500.00" in body
        assert "Pending approvals: 2" in body
        assert "88.5%" in body

    def test_digest_handles_missing_stats(self):
        from app.graph.nodes.daily_digest import build_daily_digest

        state = {
            "digest_pending_approvals": [],
            "digest_new_intakes": [],
            "digest_upcoming_events": [],
            "reminders_due": [],
            "digest_pending_agreements": [],
            "digest_overdue_deadlines": [],
            "digest_checklist_items_due": [],
            "digest_monthly_stats": {},
        }

        result = build_daily_digest(state)
        body = result["draft_response"]

        assert "QUICK STATS" in body
        assert "Stats unavailable" in body


# ============================================================
# Unit test for monthly quick stats
# ============================================================


class TestMonthlyQuickStats:
    @patch("app.services.process_insights.get_pool", new_callable=AsyncMock)
    def test_monthly_stats(self, mock_pool):
        pool = AsyncMock()
        mock_pool.return_value = pool

        pool.fetchrow.side_effect = [
            {
                "events_this_month": 15,
                "revenue_this_month": 4200.00,
                "pending_approvals": 4,
            },
            {"total_items": 40, "on_time_items": 35},
        ]

        result = asyncio.get_event_loop().run_until_complete(
            get_monthly_quick_stats(date(2026, 3, 1))
        )

        assert result["events_this_month"] == 15
        assert result["revenue_this_month"] == 4200.00
        assert result["pending_approvals"] == 4
        assert result["on_time_checklist_rate"] == 87.5
