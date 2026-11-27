"""Synthetic archive tests: no real incidents, posts, people or vehicles."""
from datetime import datetime, timezone

from custom_components.fireservicerota.dispatch_archive_store import (
    normalize_archive_record, prune_archive_records, retention_cutoff,
)


def _incident(identifier, date, **data):
    return {"incident_id": identifier, "occurred_at": date, **data}


def test_archive_allowlist_excludes_person_and_raw_payload():
    raw = _incident(
        12345, "2026-02-01T10:00:00+01:00",
        title="Synthetic fire", station_key="TEST_STATION", priority=1,
        vehicle_keys=["TEST_UNIT"], specialisms=["TS"],
        people=["SYNTHETIC_PRIVATE_NAME"],
        response_people=[{"name": "SYNTHETIC_PRIVATE_NAME"}],
        raw_api={"token": "SYNTHETIC_SECRET_TOKEN"},
        evidence=["unexpected", "array"],
    )
    result = normalize_archive_record(raw, include_details=True)
    assert result["title"] == "Synthetic fire"
    assert result["incident_id"] == "12345"
    assert "evidence" not in result
    assert "SYNTHETIC_PRIVATE_NAME" not in str(result)
    assert "SYNTHETIC_SECRET_TOKEN" not in str(result)


def test_details_opt_out_removes_extra_fields():
    row = _incident(123, "2026-02-01T10:00:00+01:00",
                    title="Synthetic title", station_key="TEST_STATION")
    assert set(normalize_archive_record(row, include_details=False)) == {
        "incident_id", "occurred_at",
    }


def test_retention_prunes_only_old_incidents_and_deduplicates():
    now = datetime(2026, 11, 23, tzinfo=timezone.utc)
    records = [
        _incident(1, "2023-01-01T00:00:00+00:00"),
        _incident(2, "2025-01-01T00:00:00+00:00"),
        _incident(2, "2025-01-01T00:00:00+00:00", title="Synthetic updated"),
        _incident(3, "2026-01-01T00:00:00+00:00"),
    ]
    kept = prune_archive_records(records, now=now, retention="2", include_details=True)
    assert [v["incident_id"] for v in kept] == ["3", "2"]
    assert kept[1]["title"] == "Synthetic updated"
    assert len(prune_archive_records(records, now=now, retention="all",
                                     include_details=True)) == 3


def test_retention_leap_day_and_invalid_dates():
    now = datetime(2024, 2, 29, tzinfo=timezone.utc)
    assert retention_cutoff(now, "2").date().isoformat() == "2022-02-28"
    assert normalize_archive_record(_incident(5, "not-a-date"),
                                    include_details=True) is None
