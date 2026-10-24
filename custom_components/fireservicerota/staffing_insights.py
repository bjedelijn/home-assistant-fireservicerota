"""Build read-only staffing insights grouped by organization membership.

A group is not automatically a station or a vehicle. Resolve stations only
when the group hierarchy clearly identifies a single station; avoid inferring
vehicle seats from skill IDs alone.
"""

from __future__ import annotations

from typing import Any


def _identifier(value: Any) -> str | None:
    """Match numeric or string identifiers without hard-coding local IDs."""
    return str(value) if value is not None else None


def _resolve_station(group_id: Any, known_groups: dict[str, dict]) -> dict | None:
    """Resolve a station only if the group has one unambiguous station ancestor."""
    group = known_groups.get(_identifier(group_id) or "", {})
    possible_ids = [_identifier(group.get("id"))]
    possible_ids.extend(_identifier(value) for value in group.get("ancestor_ids") or [])
    possible_ids.append(_identifier(group.get("parent_group_id")))

    stations = {
        key: known_groups[key]
        for key in possible_ids
        if key in known_groups and known_groups[key].get("type") == "station"
    }
    if len(stations) != 1:
        return None
    station = next(iter(stations.values()))
    return {
        "station_id": station.get("id"),
        "station_name": station.get("name"),
        "station_short_code": station.get("short_code"),
    }


def build_staffing_by_group(
    incident: Any,
    groups: list[dict] | None = None,
    *,
    suggestions: list[dict[str, Any]] | None = None,
    station_staffing_modes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Group recorded responses and assignments by membership/group ID.

    Results are incident API records, *not* independently verified turnout.
    Fairness proposals may not contain station IDs and are not mapped here.
    """
    if not isinstance(incident, dict):
        return {
            "available": False,
            "incident_task_ids": [],
            "groups": [],
            "unmatched_assignment_count": 0,
        }

    known_groups = {
        key: item
        for item in (groups or [])
        if isinstance(item, dict)
        if (key := _identifier(item.get("id"))) is not None
    }
    responses = [
        value
        for value in incident.get("incident_responses") or []
        if isinstance(value, dict)
    ]
    assignments = [
        value
        for value in incident.get("incident_skill_assignments") or []
        if isinstance(value, dict)
    ]

    skill_codes: dict[str, str] = {}
    for warning in incident.get("warning_statuses") or []:
        if not isinstance(warning, dict):
            continue
        for status in warning.get("skill_statuses") or []:
            if isinstance(status, dict) and status.get("skill_id") is not None:
                label = status.get("short_code")
                if isinstance(label, str) and label:
                    skill_codes[_identifier(status["skill_id"])] = label

    buckets: dict[str, dict[str, Any]] = {}
    responses_by_membership: dict[str, list[dict]] = {}
    responses_by_user: dict[str, list[dict]] = {}

    def ensure_bucket(group_id: Any) -> dict[str, Any]:
        key = _identifier(group_id) or "unmapped"
        if key not in buckets:
            group = known_groups.get(key, {})
            buckets[key] = {
                "group_id": group_id,
                "group_name": group.get("name"),
                "group_type": group.get("type"),
                "station": _resolve_station(group_id, known_groups),
                "response_count": 0,
                "reported_status_counts": {},
                "response_people": [],
                "skill_assignments": [],
            }
        return buckets[key]

    for response in responses:
        group_id = response.get("group_id")
        bucket = ensure_bucket(group_id)
        bucket["response_count"] += 1
        reported = response.get("reported_status") or "unknown"
        counts = bucket["reported_status_counts"]
        counts[reported] = counts.get(reported, 0) + 1
        bucket["response_people"].append(
            {
                "user_id": response.get("user_id"),
                "user_name": response.get("user_name"),
                "membership_id": response.get("membership_id"),
                "status": response.get("status"),
                "reported_status": response.get("reported_status"),
                "arrived_at_station": response.get("arrived_at_station"),
            }
        )
        membership_key = _identifier(response.get("membership_id"))
        user_key = _identifier(response.get("user_id"))
        if membership_key is not None:
            responses_by_membership.setdefault(membership_key, []).append(response)
        if user_key is not None:
            responses_by_user.setdefault(user_key, []).append(response)

    unmatched = 0
    for assignment in assignments:
        membership_key = _identifier(assignment.get("membership_id"))
        user_key = _identifier(assignment.get("user_id"))
        matching = (
            responses_by_membership.get(membership_key, [])
            if membership_key is not None
            else []
        )
        if not matching and user_key is not None:
            matching = responses_by_user.get(user_key, [])

        # Ambiguous user membership: do not guess which station was assigned.
        matched_response = matching[0] if len(matching) == 1 else None
        group_id = matched_response.get("group_id") if matched_response else None
        if matched_response is None:
            unmatched += 1
        bucket = ensure_bucket(group_id)
        skill_ids = list(assignment.get("skill_ids") or [])
        bucket["skill_assignments"].append(
            {
                "user_id": assignment.get("user_id"),
                "user_name": (
                    matched_response.get("user_name")
                    if matched_response is not None else None
                ),
                "membership_id": assignment.get("membership_id"),
                "skill_ids": skill_ids,
                "skill_short_codes": [
                    skill_codes.get(_identifier(skill_id))
                    for skill_id in skill_ids
                ],
                "reported_status": (
                    matched_response.get("reported_status")
                    if matched_response is not None else None
                ),
            }
        )

    result_groups = sorted(
        buckets.values(),
        key=lambda group: (
            group["group_id"] is None,
            str(group.get("group_name") or group.get("group_id") or ""),
        ),
    )
    # A response affiliation is not itself a permanent staffing-policy setting.
    # In particular, no observed proposal is never evidence of 'disabled':
    # the feature can be scoped to particular vehicles or incident types.
    confirmed_modes = {
        _identifier(station_id): mode
        for station_id, mode in (station_staffing_modes or {}).items()
    }
    responding_stations = {
        _identifier(bucket["station"]["station_id"])
        for bucket in result_groups
        if bucket["response_count"] > 0 and bucket["station"] is not None
    }
    has_unresolved_responders = any(
        bucket["response_count"] > 0 and bucket["station"] is None
        for bucket in result_groups
    )
    single_station = (
        next(iter(responding_stations))
        if len(responding_stations) == 1 and not has_unresolved_responders
        else None
    )
    matched_confirmations: set[str] = set()
    for bucket in result_groups:
        station = bucket["station"]
        station_id = _identifier(station["station_id"]) if station else None

        # The audit proposal contains only names/roles. Attribute evidence to
        # the sole resolved station in *this incident record*, never to a
        # particular task/vehicle or one of multiple stations.
        if suggestions is None:
            proposal_evidence = "not_evaluated"
        elif not suggestions:
            proposal_evidence = "not_observed_in_retrieved_audit"
        elif station_id is not None and station_id == single_station:
            proposal_evidence = "observed_single_station_incident"
        else:
            proposal_evidence = "observed_but_station_unattributed"

        confirmation = confirmed_modes.get(station_id)
        if confirmation in ("enabled", "disabled"):
            mode = confirmation
            source = "user_confirmed_for_incident"
            matched_confirmations.add(station_id)
        elif proposal_evidence == "observed_single_station_incident":
            mode = "enabled"
            source = "fairness_proposal_observed_for_incident"
        else:
            mode = "unknown"
            source = "insufficient_evidence"

        conflicts = (
            confirmation == "disabled"
            and proposal_evidence == "observed_single_station_incident"
        )
        bucket["automatic_staffing"] = {
            "status": mode,
            "source": source,
            "scope": "this_incident_only",
            "fairness_proposal_evidence": proposal_evidence,
            "skill_assignment_count": len(bucket["skill_assignments"]),
            "warning": (
                "User-confirmed disabled, but audit proposals were observed; "
                "verify vehicle/task scope and incident configuration."
                if conflicts else None
            ),
        }

    return {
        "available": True,
        "incident_task_ids": list(incident.get("task_ids") or []),
        "groups": result_groups,
        "unmatched_assignment_count": unmatched,
        "unused_confirmed_station_ids": sorted(
            key for key in confirmed_modes if key not in matched_confirmations
        ),
        "interpretation": (
            "Groups are response affiliations, not necessarily vehicles. "
            "Automatic staffing status applies to this incident only: "
            "no observed fairness proposals does not mean disabled. "
            "User-confirmed modes are supplied per action, not stored. "
            "Skill assignments are API records, not independently verified seats."
        ),
    }
