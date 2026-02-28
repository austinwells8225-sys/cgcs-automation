import pytest


@pytest.fixture
def sample_request():
    """A valid event space reservation request."""
    return {
        "request_id": "form-test123",
        "requester_name": "Jane Doe",
        "requester_email": "jane.doe@txgov.gov",
        "requester_organization": "Texas Department of Education",
        "event_name": "Quarterly Staff Meeting",
        "event_description": "Regular quarterly planning session for department leadership",
        "requested_date": "2026-04-15",
        "requested_start_time": "09:00",
        "requested_end_time": "12:00",
        "room_requested": "large_conference",
        "estimated_attendees": 35,
        "setup_requirements_raw": "Need projector, 40 chairs theater style, water pitchers",
        "calendar_available": True,
        "errors": [],
    }


@pytest.fixture
def invalid_request():
    """A request with validation errors."""
    return {
        "request_id": "",
        "requester_name": "",
        "requester_email": "not-an-email",
        "event_name": "",
        "requested_date": "bad-date",
        "requested_start_time": "14:00",
        "requested_end_time": "10:00",
        "errors": [],
    }


@pytest.fixture
def ineligible_request():
    """A request that should be rejected on eligibility."""
    return {
        "request_id": "form-commercial1",
        "requester_name": "Sales Manager",
        "requester_email": "sales@company.com",
        "requester_organization": "Acme Product Co",
        "event_name": "Product Launch Party",
        "event_description": "Launch event for our new commercial product line with demos and sales pitches",
        "requested_date": "2026-05-20",
        "requested_start_time": "10:00",
        "requested_end_time": "16:00",
        "room_requested": "event_hall",
        "estimated_attendees": 150,
        "setup_requirements_raw": "Stage, projector, 150 chairs theater, catering",
        "calendar_available": True,
        "errors": [],
    }
