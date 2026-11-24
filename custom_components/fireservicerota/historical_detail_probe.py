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


def summarize_detail_relationships(payloads, groups, station_id, task_index):
    """Count local reference matches; never emit identifiers or raw statuses."""
    from .staffing_insights import _resolve_station

    def identifier(value):
        return str(value) if type(value) in (int, str) and str(value).isascii() and str(value).isdigit() else None

    def rows(value):
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    known = {identifier(g.get("id")): g for g in rows(groups) if identifier(g.get("id"))}
    tasks = {identifier(k) for k in task_index} if isinstance(task_index, dict) else set()
    counts = dict.fromkeys((
        "response_rows", "requested_station", "other_resolved_station",
        "unresolved_station", "task_references", "known_task_references",
        "assignment_rows", "unique_membership_match", "ambiguous_membership_match",
        "missing_membership_match", "arrival_true", "arrival_false",
        "arrival_missing_or_null", "arrival_other_type",
        "status_equal", "status_different", "status_missing_or_invalid",
    ), 0)
    for payload in rows(payloads):
        responses = rows(payload.get("incident_responses"))
        memberships = {}
        for response in responses:
            counts["response_rows"] += 1
            group = identifier(response.get("group_id"))
            station = _resolve_station(group, known) if group else None
            resolved = identifier(station.get("station_id")) if station else None
            key = ("unresolved_station" if resolved is None else
                   "requested_station" if resolved == identifier(station_id) else
                   "other_resolved_station")
            counts[key] += 1
            member = identifier(response.get("membership_id"))
            if member:
                memberships[member] = memberships.get(member, 0) + 1
            arrival = response.get("arrived_at_station")
            key = ("arrival_true" if arrival is True else "arrival_false" if arrival is False
                   else "arrival_missing_or_null" if arrival is None else "arrival_other_type")
            counts[key] += 1
            status, reported = response.get("status"), response.get("reported_status")
            valid = all(type(v) in (str, int, bool) and v != "" for v in (status, reported))
            key = ("status_missing_or_invalid" if not valid else
                   "status_equal" if type(status) is type(reported) and status == reported
                   else "status_different")
            counts[key] += 1
        task_ids = payload.get("task_ids")
        if isinstance(task_ids, list):
            for task in task_ids:
                counts["task_references"] += 1
                counts["known_task_references"] += int(identifier(task) in tasks and identifier(task) is not None)
        for assignment in rows(payload.get("incident_skill_assignments")):
            counts["assignment_rows"] += 1
            matches = memberships.get(identifier(assignment.get("membership_id")), 0)
            counts["unique_membership_match" if matches == 1 else
                   "ambiguous_membership_match" if matches > 1 else "missing_membership_match"] += 1
    return {
        "status_profile": summarize_status_profile(payloads),
        "counts": counts,
        "task_index_available": bool(tasks),
        "group_index_available": bool(known),
        "interpretation": "Local reference matches and value shapes only; no verified attendance, task affiliation or fairness.",
    }


# Fixed candidate vocabulary, not a verified provider enum.
_STATUS_CANDIDATES = frozenset(("available", "unavailable", "unknown",
    "responding", "not_responding", "accepted", "declined", "pending",
    "present", "absent", "arrived", "not_arrived", "yes", "no",
    "dispatched", "shown_up", "no_show", "rejected", "expired",
    "cancelled", "canceled", "acknowledged", "at_station"))


def summarize_status_profile(payloads):
    """Aggregate candidate status labels and types; never echo unknown values."""
    def bucket(value):
        if value is None:
            return "null"
        if type(value) is bool:
            return "boolean_true" if value else "boolean_false"
        if type(value) is int:
            return "integer_other"
        if type(value) is str:
            normalized = value.strip().casefold()
            if not normalized:
                return "string_empty"
            return "string_" + normalized if normalized in _STATUS_CANDIDATES else "string_other"
        return "other_type"

    def rows(value):
        return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []

    def member(value):
        return str(value) if type(value) in (str, int) and str(value).isascii() and str(value).isdigit() else None

    result = {"status_counts": {}, "reported_status_counts": {},
              "cross_counts": {}, "uniquely_assigned_response_cross_counts": {},
              "status_semantics_verified": False}
    def increment(target, key):
        target[key] = target.get(key, 0) + 1

    for payload in rows(payloads):
        responses = rows(payload.get("incident_responses"))
        assignments = rows(payload.get("incident_skill_assignments"))
        members = [member(r.get("membership_id")) for r in responses]
        assigned = {member(a.get("membership_id")) for a in assignments} - {None}
        for response, key in zip(responses, members):
            status = bucket(response.get("status"))
            reported = bucket(response.get("reported_status"))
            pair = status + "__" + reported
            increment(result["status_counts"], status)
            increment(result["reported_status_counts"], reported)
            increment(result["cross_counts"], pair)
            if key in assigned and members.count(key) == 1:
                increment(result["uniquely_assigned_response_cross_counts"], pair)
    return result
