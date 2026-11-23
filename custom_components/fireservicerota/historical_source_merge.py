"""Conservative BWR-first incident merge for historical statistics.

Inputs MUST be prevalidated, privacy-minimized records produced by their
respective source adapters. This module never accepts raw BWR/P2000 payloads.
A P2000 event can supplement BWR only with an explicit validated link;
time/text proximity alone is NOT sufficient. Fairness eligibility is never
inferred from P2000.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

FIELDS = ("title", "priority", "station_key", "vehicle_keys", "specialisms")
SCALARS = frozenset({"title", "priority", "station_key"})
LIST_FIELDS = frozenset({"vehicle_keys", "specialisms"})
ALLOWED_SPECIALISMS = frozenset({
    "TS", "RV", "HV", "WO", "WTS", "DA", "HA", "AB", "OV", "other"
})


def _identifier(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    result = str(value).strip()
    return result if result.isdecimal() and 0 < len(result) <= 24 else None


def _validated_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Re-allowlist adapter input; never propagate unexpected personal fields."""
    result: dict[str, Any] = {}
    title = data.get("title")
    if isinstance(title, str) and 0 < len(title.strip()) <= 200:
        result["title"] = title.strip()
    priority = data.get("priority")
    if type(priority) is int and priority in (1, 2):
        result["priority"] = priority
    station = data.get("station_key")
    if isinstance(station, str) and 0 < len(station) <= 100:
        result["station_key"] = station
    for field in LIST_FIELDS:
        values = data.get(field)
        if not isinstance(values, list):
            continue
        valid = {
            value.strip() for value in values
            if isinstance(value, str) and 0 < len(value.strip()) <= 50
        }
        if field == "specialisms":
            valid &= ALLOWED_SPECIALISMS
        if valid:
            result[field] = sorted(valid)[:40]
    return result


def merge_bwr_p2000(
    bwr_records: list[dict[str, Any]],
    p2000_records: list[dict[str, Any]],
    *,
    verified_links: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Make a deterministic, deduplicated incident view with provenance.

    verified_links maps p2000 *event ID* to an existing BWR *incident ID*
    and must come from independent verified correlation, not a guess. Every
    unique P2000-only event remains separate. Conflicting scalar/list
    values are preserved as BWR values and counted as conflicts; absent BWR
    fields can be filled from a linked P2000 event. Multiple P2000 events
    can enrich one BWR incident but never generate fairness eligibility.
    """
    verified_links = verified_links or {}
    incidents: dict[str, dict[str, Any]] = {}
    skipped = 0
    for row in bwr_records:
        if not isinstance(row, dict) or (ident := _identifier(row.get("incident_id"))) is None:
            skipped += 1
            continue
        key = f"bwr:{ident}"
        if key in incidents:
            skipped += 1
            continue
        fields = _validated_fields(row)
        incidents[key] = {
            "archive_key": key, "primary_source": "bwr",
            "bwr_present": True, "p2000_present": False,
            "fairness_source": "bwr_only",
            "fields": fields,
            "field_sources": {field: "bwr" for field in fields},
            "conflicting_fields": [],
            "linked_p2000_events": 0,
            "match_status": "bwr_only",
        }

    used_p2000: set[str] = set()
    matched = 0
    unmatched = 0
    rejected_links = 0
    for row in p2000_records:
        if not isinstance(row, dict) or (p_id := _identifier(row.get("event_id"))) is None:
            skipped += 1
            continue
        if p_id in used_p2000:
            skipped += 1
            continue
        used_p2000.add(p_id)
        fields = _validated_fields(row)
        bwr_id = _identifier(verified_links.get(p_id))
        destination = f"bwr:{bwr_id}" if bwr_id else None
        if destination and destination in incidents:
            target = incidents[destination]
            target["p2000_present"] = True
            target["linked_p2000_events"] += 1
            target["match_status"] = "verified_link"
            matched += 1
            for field, value in fields.items():
                current = target["fields"].get(field)
                if current is None or current == []:
                    target["fields"][field] = deepcopy(value)
                    target["field_sources"][field] = "p2000"
                elif current != value and field not in target["conflicting_fields"]:
                    target["conflicting_fields"].append(field)
        else:
            if bwr_id is not None:
                rejected_links += 1
            key = f"p2000:{p_id}"
            incidents[key] = {
                "archive_key": key, "primary_source": "p2000",
                "bwr_present": False, "p2000_present": True,
                "fairness_source": "none",
                "fields": fields,
                "field_sources": {field: "p2000" for field in fields},
                "conflicting_fields": [],
                "linked_p2000_events": 1,
                "match_status": "p2000_only",
            }
            unmatched += 1
    records = sorted(incidents.values(), key=lambda record: record["archive_key"])
    return {
        "status": "locally_merged_source_metadata",
        "records": records,
        "summary": {
            "bwr_incidents": sum(record["bwr_present"] for record in records),
            "p2000_only_incidents": unmatched,
            "verified_linked_p2000_events": matched,
            "rejected_or_unresolved_links": rejected_links,
            "skipped_duplicate_or_invalid_records": skipped,
            "records_with_conflicts": sum(bool(record["conflicting_fields"]) for record in records),
        },
        "safety_note": (
            "P2000-only events are alerts, not proven vehicle departures. "
            "Fairness requires separate valid BWR audit evidence. "
            "Unverified time/text similarity never causes merging."
        ),
    }
