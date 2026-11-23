"""Annual and monthly incident count aggregation from *validated* local event keys.

Input rows are normalized by a future verified BWR/P2000 ingestion layer.
This module never assumes that an alerted unit physically departed.
No raw incident, member, station, or vehicle identifiers leave the output.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

PRIORITIES = frozenset({1, 2})
EVIDENCE = frozenset({"alerted", "reported_departure", "verified_departure"})
SPECIALISMS = frozenset({
    "TS", "RV", "HV", "WO", "WTS", "DA", "HA", "AB", "OV", "other"
})


def _month(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str) or len(value) > 50:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.year, parsed.month


def aggregate_yearly_dispatch_counts(
    events: list[dict[str, Any]], *, station_key: str | None = None,
) -> dict[str, Any]:
    """Deduplicate station incidents and vehicle evidence before counting.

    Every input event requires a validated unique incident key and a station
    key. A unit event has an optional vehicle key and source-coded speciality.
    A station incident is counted once per incident/station/priority/evidence,
    regardless of how many units were attached. A vehicle count represents
    distinct incident/unit combinations, never people.
    """
    buckets: dict[tuple[int, str, str, str, int, str], list[int]] = defaultdict(
        lambda: [0] * 12
    )
    seen_stations: set[tuple] = set()
    seen_vehicles: set[tuple] = set()
    rejected = 0
    for event in events:
        if not isinstance(event, dict):
            rejected += 1
            continue
        incident = event.get("incident_key")
        station = event.get("station_key")
        vehicle = event.get("vehicle_key")
        priority = event.get("priority")
        evidence = event.get("evidence")
        specialization = event.get("specialism")
        date = _month(event.get("occurred_at"))
        if (
            not isinstance(incident, str) or not incident or len(incident) > 100
            or not isinstance(station, str) or not station or len(station) > 100
            or (station_key is not None and station != station_key)
            or type(priority) is not int or priority not in PRIORITIES
            or evidence not in EVIDENCE or date is None
        ):
            rejected += 1
            continue
        if station_key is not None and station != station_key:
            continue
        year, month = date
        station_dedup = (incident, station, priority, evidence)
        if station_dedup not in seen_stations:
            seen_stations.add(station_dedup)
            buckets[(year, station, "station_total", "", priority, evidence)][month - 1] += 1
        if vehicle is None:
            continue
        if (
            not isinstance(vehicle, str) or not vehicle or len(vehicle) > 60
            or specialization not in SPECIALISMS
        ):
            rejected += 1
            continue
        vehicle_dedup = (incident, station, vehicle, priority, evidence)
        if vehicle_dedup not in seen_vehicles:
            seen_vehicles.add(vehicle_dedup)
            buckets[(year, station, "vehicle", vehicle, priority, evidence)][month - 1] += 1
            buckets[(year, station, "specialism", specialization, priority, evidence)][month - 1] += 1
    # This API is intended for locally authorized HA use only. Keys are not
    # automatically safe to expose via public GitHub, logs or dashboards.
    return {
        "status": "normalized_evidence_counts",
        "series": [
            {
                "year": year,
                "station_key": station,
                "dimension": dimension,
                "dimension_key": dimension_key,
                "priority": priority,
                "evidence": evidence,
                "months": months,
                "year_total": sum(months),
            }
            for (year, station, dimension, dimension_key, priority, evidence), months
            in sorted(buckets.items())
        ],
        "rejected_rows": rejected,
        "interpretation": (
            "Alerted, reported and verified departure evidence remain separate. "
            "Station totals and vehicle/specialism totals cannot be added together."
        ),
    }
