"""Synthetic historical BWR archive import boundary checks."""
import pytest
from custom_components.fireservicerota.dispatch_history_import import normalize_listing_page


def test_listing_conversion_never_retains_personnel_or_unverified_context():
    result = normalize_listing_page([{
        "id": 123, "created_at": "2024-03-15T15:00:00+01:00",
        "title": "SYNTHETIC_PRIVATE_TITLE", "station": "SYNTHETIC_PRIVATE_STATION",
        "responding": [{"name": "SYNTHETIC_PRIVATE_PERSON"}],
    }])
    assert result == [{
        "incident_id": "123", "occurred_at": "2024-03-15T15:00:00+01:00"
    }]
    assert "SYNTHETIC_PRIVATE" not in str(result)


def test_listing_accepts_empty_terminal_page():
    assert normalize_listing_page([]) == []


@pytest.mark.parametrize("payload", [
    {"error": "SYNTHETIC_PRIVATE_ERROR"},
    [None],
    [{"id": True, "created_at": "2024-01-01T12:00:00+01:00"}],
    [{"id": 123, "created_at": "2024-01-01T12:00:00"}],
    [{"id": 123, "created_at": "2024-01-01T12:00:00+01:00"}] * 2,
    [{"id": 123, "created_at": "2024-01-01T12:00:00+01:00"}] * 26,
])
def test_bad_page_fails_closed(payload):
    with pytest.raises(ValueError):
        normalize_listing_page(payload)
