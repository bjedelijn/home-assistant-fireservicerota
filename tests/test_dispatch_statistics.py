"""Only synthetic yearly dispatch statistics; no actual operational records."""
from custom_components.fireservicerota.dispatch_statistics import aggregate_yearly_dispatch_counts


def _event(incident, station, date, priority, evidence="alerted", vehicle=None, specialism=None):
    return {
        "incident_key": incident,
        "station_key": station,
        "occurred_at": date,
        "priority": priority,
        "evidence": evidence,
        "vehicle_key": vehicle,
        "specialism": specialism,
    }


def _item(result, *, dimension, key, evidence, priority):
    return next(
        row for row in result["series"]
        if row["dimension"] == dimension and row["dimension_key"] == key
        and row["evidence"] == evidence and row["priority"] == priority
    )


def test_month_and_year_counts_deduplicate_per_station_and_vehicle():
    rows = [
        _event("synthetic-1", "synthetic-station", "2025-01-10T10:00:00+01:00", 1,
               vehicle="synthetic-unit-a", specialism="TS"),
        _event("synthetic-1", "synthetic-station", "2025-01-10T10:00:00+01:00", 1,
               vehicle="synthetic-unit-a", specialism="TS"),
        _event("synthetic-1", "synthetic-station", "2025-01-10T10:00:00+01:00", 1,
               vehicle="synthetic-unit-b", specialism="RV"),
        _event("synthetic-2", "synthetic-station", "2025-02-10T10:00:00+01:00", 1,
               vehicle="synthetic-unit-a", specialism="TS"),
        _event("synthetic-3", "synthetic-station", "2025-02-10T10:00:00+01:00", 2,
               vehicle="synthetic-unit-a", specialism="TS"),
    ]
    result = aggregate_yearly_dispatch_counts(rows)
    total = _item(result, dimension="station_total", key="", evidence="alerted", priority=1)
    assert total["months"][:3] == [1, 1, 0]
    assert total["year_total"] == 2
    unit = _item(result, dimension="vehicle", key="synthetic-unit-a",
                 evidence="alerted", priority=1)
    assert unit["months"][:3] == [1, 1, 0]
    assert _item(result, dimension="specialism", key="TS",
                 evidence="alerted", priority=1)["year_total"] == 2
    assert _item(result, dimension="station_total", key="",
                 evidence="alerted", priority=2)["year_total"] == 1


def test_alerted_is_not_verified_departure():
    rows = [
        _event("synthetic-4", "synthetic-station", "2025-04-01T10:00:00+01:00", 2,
               "alerted", "synthetic-unit", "TS"),
        _event("synthetic-4", "synthetic-station", "2025-04-01T10:00:00+01:00", 2,
               "verified_departure", "synthetic-unit", "TS"),
    ]
    result = aggregate_yearly_dispatch_counts(rows)
    assert _item(result, dimension="vehicle", key="synthetic-unit",
                 evidence="alerted", priority=2)["year_total"] == 1
    assert _item(result, dimension="vehicle", key="synthetic-unit",
                 evidence="verified_departure", priority=2)["year_total"] == 1


def test_separate_year_and_station():
    rows = [
        _event("synthetic-5", "station-a", "2024-12-31T23:30:00+01:00", 1),
        _event("synthetic-6", "station-a", "2025-01-01T00:30:00+01:00", 1),
        _event("synthetic-7", "station-b", "2025-01-01T00:30:00+01:00", 1),
    ]
    result = aggregate_yearly_dispatch_counts(rows)
    assert sorted((row["year"], row["station_key"])
                  for row in result["series"]) == [
        (2024, "station-a"), (2025, "station-a"), (2025, "station-b")
    ]


def test_reject_unknown_priority_source_and_specialism():
    rows = [
        _event("synthetic-8", "station-a", "2025-01-01T12:00:00+01:00", 3),
        _event("synthetic-9", "station-a", "2025-01-01T12:00:00+01:00", 1, "unknown"),
        _event("synthetic-10", "station-a", "2025-01-01T12:00:00+01:00", 1,
               vehicle="unit", specialism="SYNTHETIC_PRIVATE_ROLE"),
    ]
    result = aggregate_yearly_dispatch_counts(rows)
    assert not any(row["dimension"] == "vehicle" for row in result["series"])
    assert "SYNTHETIC_PRIVATE_ROLE" not in str(result)
