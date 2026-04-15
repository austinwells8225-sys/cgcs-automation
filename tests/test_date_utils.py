"""Tests for date utility functions and calendar alternative date finding."""

from datetime import date
from unittest.mock import MagicMock, patch

from app.services.date_utils import (
    business_days_until,
    is_within_minimum_lead_time,
    is_weekend_or_evening,
    _normalize_time,
)
from app.cgcs_constants import (
    MINIMUM_LEAD_TIME_BD,
    POLICE_CONTACT,
    MOVING_TEAM,
    MOVING_TEAM_CC,
    ESCALATION_RECIPIENTS,
    INTERN_EMAILS,
)


# ============================================================
# business_days_until
# ============================================================

class TestBusinessDaysUntil:
    def test_same_day_returns_zero(self):
        d = date(2026, 4, 15)  # Wednesday
        assert business_days_until(d, from_date=d) == 0

    def test_next_weekday(self):
        # Wed -> Thu = 1 business day
        assert business_days_until(date(2026, 4, 16), from_date=date(2026, 4, 15)) == 1

    def test_friday_to_monday(self):
        # Fri -> Mon = 1 business day (skips Sat+Sun)
        assert business_days_until(date(2026, 4, 20), from_date=date(2026, 4, 17)) == 1

    def test_one_full_week(self):
        # Mon -> next Mon = 5 business days
        assert business_days_until(date(2026, 4, 20), from_date=date(2026, 4, 13)) == 5

    def test_two_full_weeks(self):
        # Mon -> Mon two weeks later = 10 business days
        assert business_days_until(date(2026, 4, 27), from_date=date(2026, 4, 13)) == 10

    def test_14_business_days(self):
        # Mon Apr 13 + 14 BD = Mon May 4 (skipping 4 weekends = 8 days)
        # Apr 13 (Mon) -> Apr 27 (Mon) = 10 BD, -> May 1 (Fri) = 14 BD
        assert business_days_until(date(2026, 5, 1), from_date=date(2026, 4, 13)) == 14

    def test_past_date_returns_negative(self):
        # Thu -> Wed = -1
        assert business_days_until(date(2026, 4, 15), from_date=date(2026, 4, 16)) == -1

    def test_past_date_across_weekend(self):
        # Mon -> previous Fri = -1
        assert business_days_until(date(2026, 4, 17), from_date=date(2026, 4, 20)) == -1

    def test_saturday_target(self):
        # Fri -> Sat = 0 business days (Sat is not a business day)
        # Actually: walking from Fri to Sat, Sat is not weekday so count stays 0
        assert business_days_until(date(2026, 4, 18), from_date=date(2026, 4, 17)) == 0

    def test_across_multiple_weeks(self):
        # Mon Apr 13 to Fri May 8 = 19 business days (3 full weeks + 4 days)
        assert business_days_until(date(2026, 5, 8), from_date=date(2026, 4, 13)) == 19

    def test_defaults_to_today(self):
        # Just ensure it doesn't crash when from_date is not provided
        result = business_days_until(date(2099, 1, 1))
        assert isinstance(result, int)
        assert result > 0


# ============================================================
# is_within_minimum_lead_time
# ============================================================

class TestIsWithinMinimumLeadTime:
    def test_exactly_14_bd_returns_true(self):
        # Mon Apr 13 + 14 BD = Fri May 1
        assert is_within_minimum_lead_time(
            date(2026, 5, 1), min_days=14, from_date=date(2026, 4, 13)
        ) is True

    def test_13_bd_returns_false(self):
        # One business day short
        assert is_within_minimum_lead_time(
            date(2026, 4, 30), min_days=14, from_date=date(2026, 4, 13)
        ) is False

    def test_well_over_14_bd(self):
        assert is_within_minimum_lead_time(
            date(2026, 6, 1), min_days=14, from_date=date(2026, 4, 13)
        ) is True

    def test_same_day_fails(self):
        d = date(2026, 4, 15)
        assert is_within_minimum_lead_time(d, min_days=14, from_date=d) is False

    def test_past_date_fails(self):
        assert is_within_minimum_lead_time(
            date(2026, 4, 1), min_days=14, from_date=date(2026, 4, 15)
        ) is False

    def test_custom_min_days(self):
        # 3 BD: Wed -> Mon (Fri = 1, no weekend, Mon = 2... Wed->Thu=1, Fri=2, Mon=3)
        assert is_within_minimum_lead_time(
            date(2026, 4, 20), min_days=3, from_date=date(2026, 4, 15)
        ) is True

    def test_zero_min_days(self):
        d = date(2026, 4, 15)
        assert is_within_minimum_lead_time(d, min_days=0, from_date=d) is True


# ============================================================
# is_weekend_or_evening
# ============================================================

class TestIsWeekendOrEvening:
    def test_saturday(self):
        assert is_weekend_or_evening(date(2026, 4, 18), "12:00") is True

    def test_sunday(self):
        assert is_weekend_or_evening(date(2026, 4, 19), "10:00") is True

    def test_weekday_afternoon(self):
        # Wednesday, ends at 3 PM
        assert is_weekend_or_evening(date(2026, 4, 15), "15:00") is False

    def test_weekday_exactly_5pm(self):
        # Exactly 17:00 is NOT after 5 PM
        assert is_weekend_or_evening(date(2026, 4, 15), "17:00") is False

    def test_weekday_after_5pm(self):
        assert is_weekend_or_evening(date(2026, 4, 15), "17:01") is True

    def test_weekday_9pm(self):
        assert is_weekend_or_evening(date(2026, 4, 15), "21:00") is True

    def test_12h_format_pm(self):
        assert is_weekend_or_evening(date(2026, 4, 15), "9:00 PM") is True

    def test_12h_format_am(self):
        assert is_weekend_or_evening(date(2026, 4, 15), "9:00 AM") is False

    def test_12h_format_5pm(self):
        assert is_weekend_or_evening(date(2026, 4, 15), "5:00 PM") is False

    def test_12h_format_530pm(self):
        assert is_weekend_or_evening(date(2026, 4, 15), "5:30 PM") is True

    def test_saturday_with_evening_time(self):
        # Both weekend AND evening — still True
        assert is_weekend_or_evening(date(2026, 4, 18), "9:00 PM") is True

    def test_empty_time_weekday(self):
        # No end time, weekday — defaults to not evening
        assert is_weekend_or_evening(date(2026, 4, 15), "") is False

    def test_empty_time_weekend(self):
        # No end time, weekend — still True
        assert is_weekend_or_evening(date(2026, 4, 18), "") is True


# ============================================================
# _normalize_time
# ============================================================

class TestNormalizeTime:
    def test_24h_format(self):
        assert _normalize_time("17:00") == "17:00"

    def test_24h_format_midnight(self):
        assert _normalize_time("00:00") == "00:00"

    def test_12h_pm(self):
        assert _normalize_time("5:00 PM") == "17:00"

    def test_12h_am(self):
        assert _normalize_time("9:00 AM") == "09:00"

    def test_12h_noon(self):
        assert _normalize_time("12:00 PM") == "12:00"

    def test_12h_midnight(self):
        assert _normalize_time("12:00 AM") == "00:00"

    def test_12h_lowercase(self):
        assert _normalize_time("5:30 pm") == "17:30"

    def test_empty_string(self):
        assert _normalize_time("") is None

    def test_garbage(self):
        assert _normalize_time("not a time") is None


# ============================================================
# get_alternative_dates (mocked calendar API)
# ============================================================

class TestGetAlternativeDates:
    @patch("app.services.google_calendar._get_credentials")
    @patch("app.services.google_calendar._http_with_retry")
    def test_finds_available_dates(self, mock_http, mock_creds):
        from app.services.google_calendar import get_alternative_dates

        mock_creds.return_value = MagicMock()
        mock_creds.return_value.token = "fake-token"

        # All dates are free (no events)
        mock_response = MagicMock()
        mock_response.json.return_value = {"items": []}
        mock_http.return_value = mock_response

        result = get_alternative_dates(
            calendar_id="test-cal",
            preferred_date=date(2026, 4, 15),  # Wednesday
            start_time="09:00",
            end_time="12:00",
            num_alternatives=5,
        )

        assert len(result) == 5
        # All should be weekdays
        for d in result:
            assert d.weekday() < 5
        # First result should be Thu Apr 16 (day after preferred)
        assert result[0] == date(2026, 4, 16)

    @patch("app.services.google_calendar._get_credentials")
    @patch("app.services.google_calendar._http_with_retry")
    def test_skips_weekends(self, mock_http, mock_creds):
        from app.services.google_calendar import get_alternative_dates

        mock_creds.return_value = MagicMock()
        mock_creds.return_value.token = "fake-token"

        mock_response = MagicMock()
        mock_response.json.return_value = {"items": []}
        mock_http.return_value = mock_response

        # Start from Friday — next should skip Sat/Sun
        result = get_alternative_dates(
            calendar_id="test-cal",
            preferred_date=date(2026, 4, 17),  # Friday
            start_time="09:00",
            end_time="12:00",
            num_alternatives=3,
        )

        assert result[0] == date(2026, 4, 20)  # Monday
        for d in result:
            assert d.weekday() < 5

    @patch("app.services.google_calendar._get_credentials")
    @patch("app.services.google_calendar._http_with_retry")
    def test_skips_busy_dates(self, mock_http, mock_creds):
        from app.services.google_calendar import get_alternative_dates

        mock_creds.return_value = MagicMock()
        mock_creds.return_value.token = "fake-token"

        # First call: busy, second: free, third: busy, fourth: free
        responses = []
        for busy in [True, False, True, False, False]:
            r = MagicMock()
            if busy:
                r.json.return_value = {"items": [{"summary": "Existing event"}]}
            else:
                r.json.return_value = {"items": []}
            responses.append(r)
        mock_http.side_effect = responses

        result = get_alternative_dates(
            calendar_id="test-cal",
            preferred_date=date(2026, 4, 13),  # Monday
            start_time="09:00",
            end_time="17:00",
            num_alternatives=2,
        )

        assert len(result) == 2
        # Should have skipped the busy dates
        assert result[0] == date(2026, 4, 15)  # Wednesday (Tue busy)
        assert result[1] == date(2026, 4, 17)  # Friday (Thu busy)

    @patch("app.services.google_calendar._get_credentials")
    @patch("app.services.google_calendar._http_with_retry")
    def test_returns_empty_when_all_busy(self, mock_http, mock_creds):
        from app.services.google_calendar import get_alternative_dates

        mock_creds.return_value = MagicMock()
        mock_creds.return_value.token = "fake-token"

        mock_response = MagicMock()
        mock_response.json.return_value = {"items": [{"summary": "Booked"}]}
        mock_http.return_value = mock_response

        result = get_alternative_dates(
            calendar_id="test-cal",
            preferred_date=date(2026, 4, 15),
            start_time="09:00",
            end_time="12:00",
            num_alternatives=5,
            max_scan_days=10,
        )

        assert result == []

    @patch("app.services.google_calendar._get_credentials")
    @patch("app.services.google_calendar._http_with_retry")
    def test_respects_max_scan_days(self, mock_http, mock_creds):
        from app.services.google_calendar import get_alternative_dates

        mock_creds.return_value = MagicMock()
        mock_creds.return_value.token = "fake-token"

        mock_response = MagicMock()
        mock_response.json.return_value = {"items": []}
        mock_http.return_value = mock_response

        result = get_alternative_dates(
            calendar_id="test-cal",
            preferred_date=date(2026, 4, 15),
            start_time="09:00",
            end_time="12:00",
            num_alternatives=100,
            max_scan_days=7,
        )

        # Only 7 days scanned, some are weekends, so fewer than 100
        assert len(result) <= 7
        assert len(result) > 0

    @patch("app.services.google_calendar._get_credentials")
    @patch("app.services.google_calendar._http_with_retry")
    def test_handles_api_errors_gracefully(self, mock_http, mock_creds):
        from app.services.google_calendar import get_alternative_dates

        mock_creds.return_value = MagicMock()
        mock_creds.return_value.token = "fake-token"

        # First call errors, second succeeds
        error_resp = MagicMock()
        error_resp.json.side_effect = Exception("API error")
        ok_resp = MagicMock()
        ok_resp.json.return_value = {"items": []}
        mock_http.side_effect = [Exception("timeout"), ok_resp, ok_resp, ok_resp]

        result = get_alternative_dates(
            calendar_id="test-cal",
            preferred_date=date(2026, 4, 14),  # Monday
            start_time="09:00",
            end_time="12:00",
            num_alternatives=2,
            max_scan_days=5,
        )

        # Should have skipped the error date and found 2 from the rest
        assert len(result) == 2


# ============================================================
# Constants verification
# ============================================================

class TestNewConstants:
    def test_minimum_lead_time(self):
        assert MINIMUM_LEAD_TIME_BD == 14

    def test_police_contact(self):
        assert "@" in POLICE_CONTACT

    def test_moving_team_has_members(self):
        assert len(MOVING_TEAM) == 2
        for email in MOVING_TEAM:
            assert "@" in email

    def test_moving_team_cc(self):
        assert "@" in MOVING_TEAM_CC

    def test_escalation_recipients(self):
        assert len(ESCALATION_RECIPIENTS) == 3
        assert "admin@cgcs-acc.org" in ESCALATION_RECIPIENTS
        assert "austin.wells@austincc.edu" in ESCALATION_RECIPIENTS

    def test_intern_emails_count(self):
        assert len(INTERN_EMAILS) == 7

    def test_intern_emails_all_valid(self):
        for name, email in INTERN_EMAILS.items():
            assert "@" in email
            assert name  # non-empty

    def test_intern_names_match_roster(self):
        from app.cgcs_constants import STAFF_ROSTER
        roster_names = {s["name"] for s in STAFF_ROSTER}
        for name in INTERN_EMAILS:
            assert name in roster_names, f"{name} not in STAFF_ROSTER"
