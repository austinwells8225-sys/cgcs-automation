"""Tests for LABOR_RATES constants and get_labor_rate helper."""

from app.cgcs_constants import (
    DEFAULT_BREAKDOWN_HOURS,
    DEFAULT_PREP_TIME_HOURS,
    LABOR_RATES,
    get_labor_rate,
)


class TestGetLaborRate:
    def test_director_rate(self):
        assert get_labor_rate("Bryan Port") == 66.00

    def test_intern_lead_rate(self):
        assert get_labor_rate("Stefano Casafranca Laos") == 25.00

    def test_intake_processing_rate(self):
        assert get_labor_rate("Austin Wells") == 25.00

    def test_unknown_person_returns_zero(self):
        assert get_labor_rate("Unknown Person") == 0.0


class TestLaborRatesConstants:
    def test_all_roster_staff_have_rates(self):
        all_staff = []
        for role_data in LABOR_RATES.values():
            all_staff.extend(role_data["staff"])
        assert "Bryan Port" in all_staff
        assert "Brenden Fogg" in all_staff
        assert "Austin Wells" in all_staff

    def test_default_prep_time(self):
        assert DEFAULT_PREP_TIME_HOURS == 1.0

    def test_default_breakdown_hours(self):
        assert DEFAULT_BREAKDOWN_HOURS == 0.5
