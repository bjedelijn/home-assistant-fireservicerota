"""Synthetic listing capability tests; no live incident or station records."""
from custom_components.fireservicerota.historical_listing_probe import summarize_history_listing


def test_list_metadata_never_exposes_private_data():
    result = summarize_history_listing([
        {
            "id": "SYNTHETIC_SECRET_INCIDENT",
            "created_at": "2024-02-01T12:00:00+01:00",
            "description": "SYNTHETIC_SECRET_PERSON",
            "station": "SYNTHETIC_SECRET_STATION",
        },
        {
            "id": "SYNTHETIC_SECRET_INCIDENT_2",
            "created_at": "2023-02-01T12:00:00+01:00",
        },
    ])
    assert result["status"] == "listing_shape_observed"
    assert result["items_inspected"] == 2
    assert result["earliest_visible_at"] == "2023-02-01T12:00:00+01:00"
    assert result["date_filter_supported"] is None
    assert result["history_complete"] is False
    assert "SYNTHETIC_SECRET" not in str(result)


def test_rejects_unrecognized_and_large_payloads():
    assert summarize_history_listing({"other": []})["status"] == "unrecognized_listing_shape"
    assert summarize_history_listing([{}] * 51)["status"] == "response_exceeded_probe_limit"


def test_data_envelope_and_invalid_source_date():
    result = summarize_history_listing({"data": [
        {"created_at": "SYNTHETIC_PRIVATE_DATE"},
    ]})
    assert result["items_inspected"] == 1
    assert result["earliest_visible_at"] is None
    assert "SYNTHETIC_PRIVATE_DATE" not in str(result)
