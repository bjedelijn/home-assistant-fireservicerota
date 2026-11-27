"""Synthetic offline monthly archive summaries; no BWR requests."""
from custom_components.fireservicerota.dispatch_archive_analysis import (
    summarize_indexed_incident_months,
)


def test_local_timezone_month_and_year_boundary():
    result = summarize_indexed_incident_months([
        {"incident_id": "101", "occurred_at": "2025-12-31T23:50:00+00:00"},
        {"incident_id": "102", "occurred_at": "2026-01-02T10:00:00+01:00"},
        {"incident_id": "101", "occurred_at": "2025-12-31T23:50:00+00:00"},
        {"incident_id": "103", "occurred_at": "2025-11-14T10:00:00+01:00"},
    ], listing_exhausted=True)
    assert result["indexed_unique_incidents"] == 3
    assert result["historical_list_exhausted"] is True
    assert result["archive_years_verified_complete"] is False
    assert result["confirmed_dispatch_statistics"] is False
    assert result["years"][0]["year"] == 2026
    assert result["years"][0]["months"][0] == 2
    assert result["years"][1]["year"] == 2025
    assert result["years"][1]["months"][10] == 1
    assert result["years"][0]["coverage"] == "unknown"


def test_unknown_dates_and_personnel_are_never_returned():
    result = summarize_indexed_incident_months([
        {
            "incident_id": "900",
            "occurred_at": "2026-05-01T10:00:00+02:00",
            "title": "SYNTHETIC_SECRET_EVENT",
            "crew": ["SYNTHETIC_SECRET_PERSON"],
        },
        {"incident_id": "bad-1", "occurred_at": "2026-05-01T10:00:00+02:00"},
        {"incident_id": "901", "occurred_at": "date-is-not-valid"},
        {"incident_id": "902", "occurred_at": "2026-05-01T10:00:00"},
    ])
    assert result["indexed_unique_incidents"] == 1
    assert result["rejected_archive_rows"] == 3
    assert result["years"][0]["months"][4] == 1
    assert "SYNTHETIC_SECRET" not in str(result)
    assert result["historical_fairness_evidence_available"] is False
