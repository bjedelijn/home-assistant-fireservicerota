"""Privacy-safe capability inspection of historical BWR incident details.

Never return API field values, unknown field names, incident IDs, station
names, people, free text, or response payloads. Only fixed booleans/counts.
The presence of a key does NOT validate its meaning for dispatch/fairness.
"""
from __future__ import annotations

from typing import Any

# Explicit reviewed BWR candidates and known app-normalized keys. Do not
# enumerate arbitrary API keys: some can contain operational/private data.
_CANDIDATES: dict[str, tuple[str, ...]] = {
    "incident_title": ("title", "name", "description", "message", "text"),
    "priority": ("priority", "prio", "urgency"),
    "station_reference": ("station_id", "station_ids", "stations", "group_id", "group_ids"),
    "vehicle_reference": ("vehicle_id", "vehicle_ids", "vehicles", "appliances", "units"),
    "task_reference": ("task_ids", "incident_tasks", "tasks"),
    "response_information": ("incident_responses", "responding", "responses"),
    "fairness_assignment": ("fairness_proposals", "crew_assignments", "assignments"),
    "skill_assignment_information": ("incident_skill_assignments",),
    "audit_information": ("audits", "audit_logs", "revisions"),
    "created_timestamp": ("created_at",),
    "start_timestamp": ("start_time", "started_at", "incident_time"),
}
_VALID_VALUE_TYPES = (str, int, float, bool, list, dict)
# Reviewed structural keys only. Never emit arbitrary keys or values.
_NESTED_CANDIDATES: dict[str, tuple[str, ...]] = {
    "incident_tasks": ("task_id", "id", "station_id", "name", "type"),
    "tasks": ("task_id", "id", "station_id", "name", "type"),
    "incident_responses": (
        "membership_id", "station_id", "status", "reported_status",
        "incident_task_id", "created_at", "group_id", "arrived_at_station",
    ),
    "responding": ("station_id", "task_id", "response_people", "skill_assignments"),
    "incident_skill_assignments": ("membership_id", "skill_ids"),
}


def _nested_shapes(record: dict[str, Any]) -> dict[str, dict[str, bool]]:
    output = {}
    for parent, keys in _NESTED_CANDIDATES.items():
        raw = record.get(parent)
        if not isinstance(raw, list):
            continue
        examples = [item for item in raw[:10] if isinstance(item, dict)]
        output[parent] = {
            key: any(_present(item, (key,)) for item in examples)
            for key in keys
        }
    return output



def _present(record: dict[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        value = record.get(key)
        if isinstance(value, _VALID_VALUE_TYPES) and value not in (None, "", [], {}):
            return True
    return False


def summarize_incident_detail_capabilities(payloads: list[Any]) -> dict[str, Any]:
    """Aggregate available field *shapes*, without emitting identifying data."""
    counts = {key: 0 for key in _CANDIDATES}
    by_key = {
        category: {key: 0 for key in keys}
        for category, keys in _CANDIDATES.items()
    }
    nested = {
        parent: {key: 0 for key in keys}
        for parent, keys in _NESTED_CANDIDATES.items()
    }
    valid = 0
    unexpected = 0
    for payload in payloads:
        if not isinstance(payload, dict):
            unexpected += 1
            continue
        # Incident detail has historically been returned as the direct object.
        # Unrecognized wrappers are intentionally not guessed.
        valid += 1
        for name, keys in _CANDIDATES.items():
            counts[name] += int(_present(payload, keys))
            for key in keys:
                by_key[name][key] += int(_present(payload, (key,)))
        for parent, flags in _nested_shapes(payload).items():
            for key, present in flags.items():
                nested[parent][key] += int(present)
    return {
        "status": "detail_capability_shape_only",
        "samples_inspected": len(payloads),
        "dict_responses": valid,
        "unexpected_response_shapes": unexpected,
        "fields_present_count": counts,
        "reviewed_keys_present_count": by_key,
        "reviewed_nested_keys_present_count": nested,
        "values_returned": False,
        "incident_identifiers_returned": False,
        "station_or_person_details_returned": False,
        "field_semantics_verified": False,
        "physical_departure_verified": False,
        "fairness_evidence_verified": False,
        "note": (
            "Only known candidate field presence was inspected. Missing fields may "
            "use different API names. Presence does not prove historic turnout "
            "or fairness semantics, completeness or station affiliation."
        ),
    }
