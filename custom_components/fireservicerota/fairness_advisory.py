"""Experimental read-only, task-scoped fairness evidence for review.

This does not predict a dispatch, reconstruct BrandweerRooster's fairness
algorithm, infer an eligible roster, or validate physical crew attendance.
No new API requests and no private records are written by these helpers.
"""

from __future__ import annotations

import re
from typing import Any

from .historical_fairness import _cached_status_for_preview, _id, _label

_ALLOWED_KEY = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{0,59}\Z")
_SUPPLEMENTAL_TS_ROLES = frozenset({"aspirant manschap", "aspirant", "asp"})


def _task_metadata(
    task_index: dict[Any, Any], station_id: str, task_id: str,
) -> dict[str, Any]:
    """Resolve only an unambiguous task explicitly indexed for one station."""
    matches = []
    for index_id, items in (task_index or {}).items():
        if _id(index_id) != task_id or not isinstance(items, list):
            continue
        for item in items:
            if (
                isinstance(item, dict)
                and _id(item.get("id")) == task_id
                and _id(item.get("station_id")) == station_id
            ):
                matches.append(item)
    names = {_label(item.get("name")) for item in matches if _label(item.get("name"))}
    if len(names) == 1:
        return {
            "task_name": next(iter(names)),
            "task_name_resolution": "current_station_task_index",
            "task_index_station_match": True,
        }
    return {
        "task_name": None,
        "task_name_resolution": (
            "conflicting_current_station_task_names" if len(names) > 1
            else "no_unambiguous_current_station_task_name"
        ),
        "task_index_station_match": bool(matches),
    }


def summarize_cached_station_roster_shape(
    groups: list[dict[str, Any]], station_id: int | str,
) -> dict[str, Any]:
    """Describe safe cached group field names, not live persons or availability.

    Discovery data may be stale or exclude some team/group memberships. Active
    membership rows are only a structural clue, not verified duty or ability.
    """
    station = _id(station_id)
    if station is None:
        raise ValueError("station_id must be numeric")

    matched = []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        group_id = _id(group.get("id"))
        ancestors = {
            value
            for item in (group.get("ancestor_ids") or [])
            if (value := _id(item)) is not None
        }
        if (
            group_id == station
            or station in ancestors
            or _id(group.get("parent_group_id")) == station
        ):
            matched.append(group)

    statuses: dict[str, int] = {}
    member_keys: set[str] = set()
    station_group_found = False
    membership_rows = 0
    distinct_memberships: set[str] = set()
    for group in matched:
        if (
            _id(group.get("id")) == station
            and group.get("type") == "station"
        ):
            station_group_found = True
        for membership in group.get("memberships") or []:
            if not isinstance(membership, dict):
                continue
            membership_rows += 1
            member_keys.update(
                str(key) for key in membership
                if isinstance(key, str) and _ALLOWED_KEY.fullmatch(key)
            )
            membership_id = _id(membership.get("id"))
            if membership_id:
                distinct_memberships.add(membership_id)
            raw_status = _label(membership.get("status")).casefold()
            status = raw_status if raw_status in {"active", "inactive"} else "other_or_missing"
            statuses[status] = statuses.get(status, 0) + 1

    potential_field_names = sorted(
        key for key in member_keys
        if any(hint in key.casefold() for hint in (
            "skill", "availab", "duty", "schedule", "qualif", "position",
        ))
    )
    return {
        "source": "groups_cached_from_authenticated_discovery_not_live_roster",
        "snapshot_freshness_verified": False,
        "station_group_found": station_group_found,
        "station_or_related_groups_observed": len(matched),
        "membership_rows_observed": membership_rows,
        "distinct_membership_ids_observed": len(distinct_memberships),
        "membership_row_status_counts": dict(sorted(statuses.items())),
        "membership_field_names": sorted(member_keys)[:60],
        "possible_roster_field_names": potential_field_names[:30],
        "current_duty_verified": False,
        "current_availability_verified": False,
        "task_skill_eligibility_verified": False,
        "warning": (
            "Cached membership discovery is not a live complete eligibility "
            "or availability list. Absence or inactive status here does not "
            "establish who can or cannot attend an incident."
        ),
    }


def build_task_fairness_advisory(
    records: list[dict[str, Any]],
    station_id: int | str,
    task_id: int | str,
    *,
    task_index: dict[Any, Any],
    groups: list[dict[str, Any]],
    crew_overview: dict[str, Any] | None = None,
    include_people: bool = False,
) -> dict[str, Any]:
    """Describe unique historical proposals for exactly one station/task.

    Counts indicate exposure in *available selected audit incidents*. They do
    not measure eligibility, fairness, dispatch probability or physical turnout.
    No named person or membership ID leaves this function unless include_people
    is explicitly enabled.
    """
    station = _id(station_id)
    task = _id(task_id)
    if station is None or task is None:
        raise ValueError("station_id and task_id must be numeric")
    if not isinstance(include_people, bool):
        raise ValueError("include_people must be boolean")

    by_incident: dict[str, dict[str, Any]] = {}
    for record in records:
        if (
            not isinstance(record, dict)
            or _id(record.get("station_id")) != station
            or record.get("source") != "complete_audit_latest_fairness_proposal"
        ):
            continue
        incident = _id(record.get("incident_id"))
        if not incident:
            continue
        current = by_incident.get(incident)
        if (
            current is None
            or str(record.get("latest_proposal_at") or "")
            > str(current.get("latest_proposal_at") or "")
        ):
            by_incident[incident] = record

    matching = []
    missing_or_multi_task = 0
    for record in by_incident.values():
        tasks = {
            value
            for raw in (record.get("incident_task_ids") or [])
            if (value := _id(raw)) is not None
        }
        if len(tasks) == 1 and task in tasks:
            matching.append(record)
        elif task in tasks:
            missing_or_multi_task += 1

    matching.sort(
        key=lambda row: (
            str(row.get("latest_proposal_at") or ""),
            str(row.get("incident_id") or ""),
        ),
        reverse=True,
    )
    excluded_partial = [
        row for row in matching
        if (row.get("unmatched_proposal_seats") or 0) > 0
        or (row.get("ambiguous_name_seats") or 0) > 0
    ]
    usable = [
        row for row in matching
        if row not in excluded_partial and isinstance(row.get("people"), list)
    ]

    metadata = _task_metadata(task_index, station, task)
    role_records: dict[str, dict[str, Any]] = {}
    for record in usable:
        incident_id = _id(record.get("incident_id"))
        timestamp = record.get("latest_proposal_at")
        seen_pairs: set[tuple[str, str]] = set()
        role_counts: dict[str, int] = {}
        for person in record.get("people") or []:
            if not isinstance(person, dict):
                continue
            membership = _id(person.get("membership_id"))
            role = _label(person.get("role"))
            if not membership or not role or (membership, role) in seen_pairs:
                continue
            seen_pairs.add((membership, role))
            role_counts[role] = role_counts.get(role, 0) + 1
            stats = role_records.setdefault(role, {
                "incidents": set(), "proposal_appearances": 0,
                "candidates": {}, "role_sizes": [],
            })
            stats["incidents"].add(incident_id)
            stats["proposal_appearances"] += 1
            member = stats["candidates"].setdefault(membership, {
                "membership_id": membership,
                "name": _label(person.get("name")),
                "historical_proposal_incidents": 0,
                "last_proposed_at": None,
                "retrospective_api_reported_status_counts": {},
                "retrospective_skill_assignment_record_incidents": 0,
                "incidents_with_status_comparison": 0,
            })
            member["historical_proposal_incidents"] += 1
            if (
                timestamp
                and (member["last_proposed_at"] is None
                     or str(timestamp) > str(member["last_proposed_at"]))
            ):
                member["last_proposed_at"] = timestamp
            if "api_reported_status" in person:
                member["incidents_with_status_comparison"] += 1
                status = _cached_status_for_preview(person["api_reported_status"])
                if isinstance(status, str) and status:
                    counts = member["retrospective_api_reported_status_counts"]
                    counts[status] = counts.get(status, 0) + 1
                if person.get("api_skill_assignment_recorded") is True:
                    member["retrospective_skill_assignment_record_incidents"] += 1
        for role, count in role_counts.items():
            role_records[role]["role_sizes"].append(count)

    profiles = []
    for role, stats in sorted(role_records.items()):
        members = sorted(
            stats["candidates"].values(),
            key=lambda item: (
                str(item.get("name") or "").casefold(),
                str(item.get("membership_id") or ""),
            ),
        )
        is_extra_asp = (
            metadata["task_name"] is not None
            and metadata["task_name"].casefold() == "ts"
            and role.casefold() in _SUPPLEMENTAL_TS_ROLES
        )
        profile = {
            "role": role,
            "role_position_interpretation": (
                "supplemental_ts_asp"
                if is_extra_asp else "proposal_role_not_equivalent_to_vehicle_seat"
            ),
            "incidents_with_role_proposal": len(stats["incidents"]),
            "proposal_appearances": stats["proposal_appearances"],
            "distinct_historical_candidates": len(members),
            "role_proposals_per_observed_incident_min": (
                min(stats["role_sizes"]) if stats["role_sizes"] else None
            ),
            "role_proposals_per_observed_incident_max": (
                max(stats["role_sizes"]) if stats["role_sizes"] else None
            ),
        }
        if include_people:
            profile["historical_candidates"] = [
                {
                    **member,
                    "current_duty_status": "not_verified",
                    "current_task_eligibility": "not_verified",
                }
                for member in members
            ]
            profile["candidate_display_order"] = (
                "alphabetical_not_prediction_order"
            )
        profiles.append(profile)

    crew_summary = {
        "source": "historical_skill_assignment_snapshots_not_current_task_rules",
        "incidents_with_coverage_evidence": 0,
        "regular_coverage_sufficient": 0,
        "regular_coverage_insufficient": 0,
        "regular_coverage_unknown": 0,
        "observed_required_skills": [],
    }
    skill_observations: dict[tuple[str, str], dict[str, Any]] = {}
    usable_ids = {_id(record.get("incident_id")) for record in usable}
    for evidence in (crew_overview or {}).get("incident_evidence_overview") or []:
        if (
            not isinstance(evidence, dict)
            or _id(evidence.get("incident_id")) not in usable_ids
        ):
            continue
        requirements = evidence.get("crew_requirement_evidence") or []
        if not requirements:
            continue
        crew_summary["incidents_with_coverage_evidence"] += 1
        states = [req.get("regular_crew_sufficient") for req in requirements]
        if False in states:
            crew_summary["regular_coverage_insufficient"] += 1
        elif states and all(state is True for state in states):
            crew_summary["regular_coverage_sufficient"] += 1
        else:
            crew_summary["regular_coverage_unknown"] += 1
        seen_skill_keys: set[tuple[str, str]] = set()
        for req in requirements:
            if not isinstance(req, dict):
                continue
            for skill in req.get("skills") or []:
                if not isinstance(skill, dict):
                    continue
                skill_id = _id(skill.get("skill_id"))
                required = skill.get("required")
                if (
                    skill_id is None or isinstance(required, bool)
                    or not isinstance(required, int) or required < 0
                ):
                    continue
                scope = str(skill.get("position_type") or "unknown")
                key = (skill_id, scope)
                if key in seen_skill_keys:
                    continue
                seen_skill_keys.add(key)
                data = skill_observations.setdefault(key, {
                    "skill_id": skill_id,
                    "role_code": _label(skill.get("short_code")) or None,
                    "position_type": scope,
                    "incidents_observed": 0,
                    "observed_required_min": required,
                    "observed_required_max": required,
                })
                data["incidents_observed"] += 1
                data["observed_required_min"] = min(
                    data["observed_required_min"], required
                )
                data["observed_required_max"] = max(
                    data["observed_required_max"], required
                )
    crew_summary["observed_required_skills"] = [
        skill_observations[key] for key in sorted(skill_observations)
    ]

    return {
        "station_id": station,
        "task_id": task,
        **metadata,
        "historical_sample": {
            "distinct_cached_incidents_for_station": len(by_incident),
            "single_task_incidents_matching": len(matching),
            "usable_complete_proposal_incidents": len(usable),
            "excluded_partial_or_ambiguous_proposal_incidents": len(excluded_partial),
            "excluded_multi_task_incidents_containing_task": missing_or_multi_task,
            "latest_proposal_at": (
                usable[0].get("latest_proposal_at") if usable else None
            ),
            "oldest_proposal_at": (
                usable[-1].get("latest_proposal_at") if usable else None
            ),
        },
        "historical_roles": profiles,
        "historical_crew_requirement_evidence": crew_summary,
        "current_station_roster_shape": summarize_cached_station_roster_shape(
            groups, station
        ),
        "personal_candidate_details_included": include_people,
        "candidate_ordering": (
            "alphabetical_not_prediction_order"
            if include_people else "candidate_details_not_requested"
        ),
        "current_duty_or_availability_checked": False,
        "current_task_skill_eligibility_checked": False,
        "actual_vehicle_crew_verified": False,
        "fairness_percentage_calculated": False,
        "selection_probability_calculated": False,
        "predicted_lineup": None,
        "prediction_status": (
            "historical_task_evidence_only_not_ready_for_lineup"
            if usable else "no_complete_historical_task_evidence"
        ),
        "interpretation": (
            "This is a neutral description of one latest uniquely linked "
            "historical fairness proposal per incident for exactly one task "
            "at one station. People appearing frequently may simply have "
            "been available more often. No negative evidence is imputed to "
            "members absent from a proposal, and API statuses are retrospective, "
            "not physical turnout. Task skills and required counts are historical, "
            "not checked against current task configuration. Active membership "
            "discovery does not verify who is on duty, available or competent "
            "for the next call. Do not use as an operational staffing plan."
        ),
    }
