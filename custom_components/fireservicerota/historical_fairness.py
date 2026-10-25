"""Compact, identity-safe historical fairness evidence and role profiles.

Only the latest fairness proposal per distinct incident counts once. Proposal
labels must resolve uniquely to an API membership at one unambiguous station;
otherwise no person-level evidence is imported. Nothing is a proven turnout or
an estimate of the BrandweerRooster scheduling algorithm.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

MAX_HISTORY_RECORDS = 100


def _id(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    result = str(value).strip()
    return result if result and result.isdecimal() else None


def _label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _name_key(value: Any) -> str:
    return _label(value).casefold()


def select_retained_history_ids(
    history: list[dict[str, Any]], *, offset: int, limit: int,
) -> dict[str, Any]:
    """Select one bounded chronological page of Home Assistant's closed history."""
    if not isinstance(offset, int) or not 0 <= offset <= 24:
        raise ValueError("offset must be between 0 and 24")
    if not isinstance(limit, int) or not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    ids = [
        str(incident["id"])
        for incident in history
        if isinstance(incident, dict) and _id(incident.get("id")) is not None
    ]
    stop = offset + limit
    return {
        "ids": ids[offset:stop],
        "offset": offset,
        "available_retained_incidents": len(ids),
        "next_offset": min(stop, len(ids)) if stop < len(ids) else None,
    }


# These are API-reported states at the time of a historical GET. They must
# not be represented as independent confirmation of physical vehicle occupancy.
_REPORTED_STATUS_LABELS = frozenset({
    "dispatched", "shown_up", "no_show", "rejected", "expired",
    "cancelled", "canceled", "acknowledged", "accepted",
    "responding", "arrived", "at_station", "unknown",
})


def _reported_status_code(raw: Any) -> str:
    """Retain safe unknown API enum tokens without guessing their meaning.

    Some valid BrandweerRooster response codes do not belong to our known
    enum. Previously they were all collapsed to 'other', losing evidence.
    Literal API 'unknown' remains 'unknown', while a missing or blank
    status becomes 'missing'. Prefix otherwise unrecognized enum tokens
    with 'unmapped:'; never store unbounded/free-form private text.
    """
    if raw is None:
        return "missing"
    if not isinstance(raw, str):
        return "other"
    value = raw.strip().casefold()
    if not value:
        return "missing"
    if value in _REPORTED_STATUS_LABELS:
        return value
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", value):
        return f"unmapped:{value}"
    return "other"


def _task_context(staffing: dict[str, Any]) -> dict[str, Any]:
    """Record incident-level task IDs, without assigning the proposal to a task."""
    task_ids = sorted(
        {
            value
            for item in (staffing.get("incident_task_ids") or [])
            if (value := _id(item)) is not None
        },
        key=int,
    )
    context = (
        "single_incident_task"
        if len(task_ids) == 1
        else "multiple_incident_tasks" if task_ids else "no_task_ids"
    )
    return {"incident_task_ids": task_ids, "task_context": context}


def _annotate_member_api_records(
    identified: list[dict[str, str | None]],
    responding: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach retrospective API-recorded status to an exact membership.

    The API incident snapshot is retrieved *now*, not necessarily at the
    time of the historical fairness proposal. A skill-assignment record
    does not prove the suggested role or actual vehicle occupancy.
    """
    statuses: dict[str, set[str]] = {}
    assigned_memberships: set[str] = set()
    for group in responding:
        for person in group.get("response_people") or []:
            if not isinstance(person, dict):
                continue
            membership = _id(person.get("membership_id"))
            if membership is None:
                continue
            normalized = _reported_status_code(person.get("reported_status"))
            statuses.setdefault(membership, set()).add(normalized)

        for assignment in group.get("skill_assignments") or []:
            if not isinstance(assignment, dict):
                continue
            membership = _id(assignment.get("membership_id"))
            if membership is not None:
                assigned_memberships.add(membership)

    annotated: list[dict[str, Any]] = []
    for person in identified:
        membership = person["membership_id"]
        possible = statuses.get(membership, set())
        status = (
            "ambiguous" if len(possible) > 1
            else next(iter(possible)) if possible else "unknown"
        )
        annotated.append({
            **person,
            "api_reported_status": status,
            "api_skill_assignment_recorded": membership in assigned_memberships,
        })
    return annotated


def _role_api_observations(
    annotated_people: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate per-role API records without counting verified attendance."""
    roles: dict[str, dict[str, Any]] = {}
    for person in annotated_people:
        role = _label(person["role"])
        bucket = roles.setdefault(
            role,
            {
                "role": role,
                "proposed_member_appearances": 0,
                "reported_status_counts": {},
                "ambiguous_reported_status_count": 0,
                "api_skill_assignment_member_appearances": 0,
            },
        )
        bucket["proposed_member_appearances"] += 1
        status = person["api_reported_status"]
        if status == "ambiguous":
            bucket["ambiguous_reported_status_count"] += 1
        else:
            counts = bucket["reported_status_counts"]
            counts[status] = counts.get(status, 0) + 1
        if person["api_skill_assignment_recorded"]:
            bucket["api_skill_assignment_member_appearances"] += 1
    return [roles[role] for role in sorted(roles)]


def summarize_incident_for_history(
    analysis: dict[str, Any], station_id: int | str,
) -> dict[str, Any]:
    """Convert one full audit response into minimal membership-linked evidence.

    A proposal without a station reference may only be attributed when every
    responding group belongs unambiguously to exactly the requested station.
    Matching by a display name is acceptable *only within that incident* when
    there is exactly one membership corresponding to that display name.
    """
    incident_id = _id(analysis.get("incident_id"))
    requested = _id(station_id)
    if not incident_id or not requested:
        raise ValueError("incident_id and station_id must be numeric")

    def skip(reason: str) -> dict[str, Any]:
        return {"incident_id": incident_id, "status": "skipped", "reason": reason}

    if analysis.get("audit_complete") is not True:
        return skip("audit_incomplete")
    if not analysis.get("fairness_suggestion_count"):
        return skip("no_fairness_proposals")
    latest = analysis.get("latest_fairness_suggestion")
    if not isinstance(latest, dict) or not isinstance(latest.get("members"), list):
        return skip("no_latest_suggestion")

    by_group = analysis.get("staffing_by_group") or {}
    responding = [
        group for group in by_group.get("groups") or []
        if isinstance(group, dict) and (group.get("response_count") or 0) > 0
    ]
    if not responding:
        return skip("no_response_station")
    station_ids = set()
    for group in responding:
        station = group.get("station") or {}
        candidate = _id(station.get("station_id"))
        if candidate is None:
            return skip("station_unresolved")
        station_ids.add(candidate)
    if station_ids != {requested}:
        return skip("multi_station_or_other_station")

    people: dict[str, set[tuple[str, str | None, str]]] = {}
    for group in responding:
        for person in group.get("response_people") or []:
            if not isinstance(person, dict):
                continue
            membership = _id(person.get("membership_id"))
            name = _label(person.get("user_name"))
            if membership is None or not name:
                continue
            key = _name_key(name)
            people.setdefault(key, set()).add(
                (membership, _id(person.get("user_id")), name)
            )

    identified: list[dict[str, str | None]] = []
    unmatched = 0
    ambiguous = 0
    seen: set[tuple[str, str]] = set()
    for suggested in latest["members"]:
        if not isinstance(suggested, dict):
            unmatched += 1
            continue
        name_key = _name_key(suggested.get("name"))
        role = _label(suggested.get("role"))
        matches = people.get(name_key, set())
        if not name_key or not role:
            unmatched += 1
        elif len(matches) > 1:
            ambiguous += 1
        elif len(matches) == 0:
            unmatched += 1
        else:
            membership, user_id, display_name = next(iter(matches))
            match_key = (membership, role)
            if match_key not in seen:
                identified.append(
                    {
                        "membership_id": membership,
                        "user_id": user_id,
                        "name": display_name,
                        "role": role,
                    }
                )
                seen.add(match_key)

    if not identified:
        return skip("no_unambiguous_membership_matches")

    annotated_people = _annotate_member_api_records(identified, responding)

    return {
        "incident_id": incident_id,
        "status": "imported",
        "record": {
            "incident_id": incident_id,
            "station_id": requested,
            "latest_proposal_at": latest.get("at"),
            "proposal_snapshots_seen": analysis["fairness_suggestion_count"],
            "api_record_checked_at": datetime.now(timezone.utc).isoformat(),
            **_task_context(by_group),
            "people": annotated_people,
            "role_api_observations": _role_api_observations(annotated_people),
            "unmatched_proposal_seats": unmatched,
            "ambiguous_name_seats": ambiguous,
            "source": "complete_audit_latest_fairness_proposal",
        },
    }


def _cached_status_for_preview(status: Any) -> Any:
    """Repair the exact old label for the *literal* API code 'unknown'.

    This is presentation-only: no network requests, storage writes or
    guesses about old generic 'other' counts.
    """
    return "unknown" if status == "unmapped:unknown" else status


def _incident_evidence_overview(record: dict[str, Any]) -> dict[str, Any]:
    """Private, identity-free per-incident diagnostic for recorded proposals.

    Roles are the exact proposal labels, not validated vehicle seats.
    Counts match one distinct (membership_id, role) per incident.
    """
    roles: dict[str, int] = {}
    member_roles: dict[str, set[str]] = {}
    statuses: dict[str, int] = {}
    comparison_seats = 0
    assigned_seats = 0
    counted: set[tuple[str, str]] = set()

    for item in record.get("people") or []:
        if not isinstance(item, dict):
            continue
        membership = _id(item.get("membership_id"))
        role = _label(item.get("role"))
        if not membership or not role or (membership, role) in counted:
            continue
        counted.add((membership, role))
        roles[role] = roles.get(role, 0) + 1
        member_roles.setdefault(membership, set()).add(role)
        if "api_reported_status" in item:
            status = _cached_status_for_preview(item["api_reported_status"])
            statuses[status] = statuses.get(status, 0) + 1
            comparison_seats += 1
            if item.get("api_skill_assignment_recorded") is True:
                assigned_seats += 1

    role_seats = len(counted)
    return {
        "incident_id": _id(record.get("incident_id")),
        "latest_proposal_at": record.get("latest_proposal_at"),
        "task_context": record.get("task_context") or "legacy_not_imported",
        "incident_task_ids": list(record.get("incident_task_ids") or []),
        "proposal_snapshots_seen": record.get("proposal_snapshots_seen"),
        "role_seats": [
            {"role": role, "proposed_seats": count}
            for role, count in sorted(roles.items())
        ],
        "total_proposed_role_seats": role_seats,
        "distinct_proposed_memberships": len(member_roles),
        "members_in_multiple_proposed_roles": sum(
            len(member_roles[key]) > 1 for key in member_roles
        ),
        "api_comparison_role_seats": comparison_seats,
        "api_reported_status_counts": dict(sorted(statuses.items())),
        "api_skill_assignment_member_role_seats": assigned_seats,
        "interpretation": "source_proposal_and_retrospective_api_records_only",
    }


def build_historical_role_preview(
    records: list[dict[str, Any]], station_id: int | str,
) -> dict[str, Any]:
    """Summarize historical candidates, with no fabricated probability/ranking."""
    requested = _id(station_id)
    if not requested:
        raise ValueError("station_id must be numeric")
    distinct: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or _id(record.get("station_id")) != requested:
            continue
        incident_id = _id(record.get("incident_id"))
        if incident_id is not None:
            distinct[incident_id] = record

    observed = sorted(
        distinct.values(), key=lambda r: str(r.get("latest_proposal_at") or ""),
        reverse=True,
    )
    roles: dict[str, dict[str, dict]] = {}
    skipped_unmatched = 0
    skipped_ambiguous = 0
    context_counts: dict[str, int] = {
        "single_incident_task": 0,
        "multiple_incident_tasks": 0,
        "no_task_ids": 0,
        "legacy_not_imported": 0,
    }
    role_evidence: dict[str, dict[str, Any]] = {}
    role_evidence_incidents = 0
    for record in observed:
        context = record.get("task_context")
        context_counts[
            context if context in context_counts else "legacy_not_imported"
        ] += 1
        observations = record.get("role_api_observations")
        if isinstance(observations, list):
            role_evidence_incidents += 1
            for item in observations:
                if not isinstance(item, dict):
                    continue
                role = _label(item.get("role"))
                if not role:
                    continue
                bucket = role_evidence.setdefault(
                    role,
                    {
                        "role": role,
                        "incidents_with_observations": 0,
                        "proposed_member_appearances": 0,
                        "reported_status_counts": {},
                        "ambiguous_reported_status_count": 0,
                        "api_skill_assignment_member_appearances": 0,
                    },
                )
                bucket["incidents_with_observations"] += 1
                bucket["proposed_member_appearances"] += int(
                    item.get("proposed_member_appearances") or 0
                )
                bucket["ambiguous_reported_status_count"] += int(
                    item.get("ambiguous_reported_status_count") or 0
                )
                bucket["api_skill_assignment_member_appearances"] += int(
                    item.get("api_skill_assignment_member_appearances") or 0
                )
                for status, count in (item.get("reported_status_counts") or {}).items():
                    statuses = bucket["reported_status_counts"]
                    status = _cached_status_for_preview(status)
                    statuses[status] = statuses.get(status, 0) + int(count)
        
        skipped_unmatched += int(record.get("unmatched_proposal_seats") or 0)
        skipped_ambiguous += int(record.get("ambiguous_name_seats") or 0)
        incident_roles: set[tuple[str, str]] = set()
        for item in record.get("people") or []:
            if not isinstance(item, dict):
                continue
            membership = _id(item.get("membership_id"))
            role = _label(item.get("role"))
            if not membership or not role:
                continue
            role_key = (role, membership)
            if role_key in incident_roles:
                continue
            incident_roles.add(role_key)
            group = roles.setdefault(role, {})
            candidate = group.setdefault(
                membership,
                {
                    "membership_id": membership,
                    "user_id": _id(item.get("user_id")),
                    "name": _label(item.get("name")),
                    "incidents_in_latest_proposal": 0,
                    "last_observed_at": None,
                    "incidents_with_person_api_comparison": 0,
                    "api_reported_status_counts": {},
                    "api_skill_assignment_recorded_incidents": 0,
                },
            )
            candidate["incidents_in_latest_proposal"] += 1
            # Legacy cached rows intentionally do not claim a status.
            if "api_reported_status" in item:
                candidate["incidents_with_person_api_comparison"] += 1
                status = _cached_status_for_preview(item["api_reported_status"])
                counts = candidate["api_reported_status_counts"]
                counts[status] = counts.get(status, 0) + 1
                if item.get("api_skill_assignment_recorded") is True:
                    candidate["api_skill_assignment_recorded_incidents"] += 1
            timestamp = record.get("latest_proposal_at")
            if timestamp and (
                candidate["last_observed_at"] is None
                or timestamp > candidate["last_observed_at"]
            ):
                candidate["last_observed_at"] = timestamp

    return {
        "station_id": requested,
        "distinct_incidents_with_complete_matched_audit": len(observed),
        "historical_roles": [
            {
                "role": role,
                # Descriptive frequency only; a repeatedly suggested member is
                # not necessarily more likely to be proposed *next time*.
                "candidates": sorted(
                    candidates.values(),
                    key=lambda c: (
                        str(c.get("last_observed_at") or ""),
                        str(c.get("name") or ""),
                    ),
                    reverse=True,
                ),
            }
            for role, candidates in sorted(roles.items())
        ],
        "task_context_incident_counts": context_counts,
        "incident_evidence_overview": [
            _incident_evidence_overview(record) for record in observed
        ],
        "person_api_comparison_status": "retrospective_api_records_not_verified_turnout",
        "proposal_to_api_record_comparison": {
            "incidents_with_comparison_data": role_evidence_incidents,
            "role_observations": [
                role_evidence[role] for role in sorted(role_evidence)
            ],
            "interpretation": (
                "These are on-demand API-recorded statuses/skill assignments "
                "for members present in each latest historical fairness proposal. "
                "API records do not verify physical crew or identify a vehicle. "
                "Legacy cached incidents have no comparison data until explicitly "
                "refreshed. Missing or conflicting API statuses are not inferred."
            ),
        },
        "historical_unmatched_proposal_seats": skipped_unmatched,
        "historical_ambiguous_name_seats": skipped_ambiguous,
        "prediction_status": "history_only_not_a_lineup_prediction",
        "current_duty_or_availability_checked": False,
        "actual_vehicle_crew_verified": False,
        "fairness_percentage_calculated": False,
        "interpretation": (
            "One latest fairness suggestion per unique incident was counted. "
            "Only uniquely matched membership IDs within a single-station "
            "incident contribute to each role. Historical proposal frequency "
            "is not a fairness percentage or a probability of being selected "
            "next. Current availability, vehicle requirements and scheduling "
            "policy have not been validated, so no crew is predicted."
        ),
    }

def build_compact_history_evidence(preview: dict[str, Any]) -> dict[str, Any]:
    """Return only per-incident and aggregate analysis, not candidate rows."""
    keys = (
        "station_id",
        "distinct_incidents_with_complete_matched_audit",
        "task_context_incident_counts",
        "incident_evidence_overview",
        "proposal_to_api_record_comparison",
        "historical_unmatched_proposal_seats",
        "historical_ambiguous_name_seats",
        "prediction_status",
        "current_duty_or_availability_checked",
        "actual_vehicle_crew_verified",
        "fairness_percentage_calculated",
    )
    return {key: preview[key] for key in keys if key in preview}


def enrich_compact_history_task_names(
    compact: dict[str, Any],
    task_index: dict[Any, list[dict[str, Any]]],
    station_id: int | str,
) -> dict[str, Any]:
    """Resolve task names from current authorized station metadata.

    The incident's historical task IDs are not enough to establish its vehicle
    name. This does a station-scoped read-only join to the integration's
    already-discovered task index, never assuming names from numeric IDs.
    """
    requested_station = _id(station_id)
    result = dict(compact)
    result["task_name_source"] = (
        "current_station_task_index_not_historical_task_snapshot"
    )
    resolved_rows = []
    for row in compact.get("incident_evidence_overview") or []:
        if not isinstance(row, dict):
            continue
        enriched = dict(row)
        tasks = []
        for raw_id in row.get("incident_task_ids") or []:
            task_id = _id(raw_id)
            if task_id is None:
                continue
            candidates = []
            if isinstance(task_index, dict):
                for key in (int(task_id), task_id):
                    for candidate in task_index.get(key, []) or []:
                        if not isinstance(candidate, dict):
                            continue
                        if (
                            _id(candidate.get("id")) != task_id
                            or _id(candidate.get("station_id")) != requested_station
                        ):
                            continue
                        candidates.append(candidate)
            names = {
                _label(candidate.get("name"))
                for candidate in candidates
                if _label(candidate.get("name"))
            }
            entry: dict[str, Any] = {"id": task_id}
            if len(names) == 1:
                entry["name"] = next(iter(names))
                entry["resolution"] = "current_station_task_index"
            elif len(names) > 1:
                entry["resolution"] = "conflicting_current_task_names"
            else:
                entry["resolution"] = "name_not_available_in_current_station_index"
            tasks.append(entry)
        enriched["resolved_tasks"] = tasks
        resolved_rows.append(enriched)
    result["incident_evidence_overview"] = resolved_rows
    return result

def _optional_nonnegative_int(value: Any) -> int | None:
    """Return a known nonnegative API count, never coerce missing to zero."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.strip().isdecimal():
        return int(value.strip())
    return None


def enrich_compact_history_crew_coverage(
    compact: dict[str, Any],
    retained_history: list[dict[str, Any]],
    station_id: int | str,
) -> dict[str, Any]:
    """Join separately recorded skill coverage from retained HA incident history.

    Never convert fairness proposal roles into assigned vehicle positions.
    Requirements may overlap; shortfalls remain per skill, not unique people.
    No API request, cache mutation, incident change or personally identifying
    data is needed for this optional compact read-only diagnostic.
    """
    requested = _id(station_id)
    if requested is None:
        raise ValueError("station_id must be numeric")

    snapshots = {
        incident_id: snapshot
        for snapshot in retained_history
        if isinstance(snapshot, dict)
        if (incident_id := _id(snapshot.get("id"))) is not None
    }
    # Short codes may be absent in one incident's warning_statuses. Resolve
    # only from other retained requirements with the *same station and task*.
    # Never assume a numeric skill ID universally represents one role.
    known_task_skill_codes: dict[tuple[str, str], set[str]] = {}
    for historical in snapshots.values():
        for requirement in historical.get("crew_requirements") or []:
            if not isinstance(requirement, dict):
                continue
            stations = {
                station
                for value in requirement.get("station_ids") or []
                if (station := _id(value)) is not None
            }
            task_ids = {
                task
                for value in requirement.get("task_ids") or []
                if (task := _id(value)) is not None
            }
            if stations != {requested} or len(task_ids) != 1:
                continue
            task = next(iter(task_ids))
            for skill in requirement.get("skills") or []:
                if not isinstance(skill, dict):
                    continue
                skill_id = _id(skill.get("skill_id"))
                code = _label(skill.get("short_code"))
                if skill_id and code:
                    known_task_skill_codes.setdefault(
                        (task, skill_id), set()
                    ).add(code.casefold())

    result = dict(compact)
    rows = []
    for row in compact.get("incident_evidence_overview") or []:
        if not isinstance(row, dict):
            continue
        enriched = dict(row)
        enriched["crew_requirement_evidence"] = []
        snapshot = snapshots.get(_id(row.get("incident_id")))
        if not isinstance(snapshot, dict) or not isinstance(
            snapshot.get("crew_requirements"), list
        ):
            enriched["crew_coverage_status"] = "no_retained_staffing_snapshot"
            rows.append(enriched)
            continue

        incident_task_ids = {
            task_id
            for task in (row.get("incident_task_ids") or [])
            if (task_id := _id(task)) is not None
        }
        if not incident_task_ids:
            enriched["crew_coverage_status"] = "incident_task_ids_unavailable"
            rows.append(enriched)
            continue

        resolved_tasks = row.get("resolved_tasks") or []
        # A confirmed TS-specific rule: 'Asp' is an additional position
        # rather than a required position in the normal TS crew. Current
        # task metadata is used for this interpretation, not proof of a
        # historical vehicle configuration.
        ts_task_id = None
        if len(incident_task_ids) == 1 and len(resolved_tasks) == 1:
            task = resolved_tasks[0]
            if (
                isinstance(task, dict)
                and _id(task.get("id")) in incident_task_ids
                and _label(task.get("name")).casefold() == "ts"
            ):
                ts_task_id = next(iter(incident_task_ids))

        crew_summary = snapshot.get("crew_summary")
        individual_assignments_available = (
            isinstance(crew_summary, dict)
            and crew_summary.get("individual_assignments_available") is True
        )
        for requirement in snapshot["crew_requirements"]:
            if not isinstance(requirement, dict):
                continue
            station_ids = {
                station
                for value in (requirement.get("station_ids") or [])
                if (station := _id(value)) is not None
            }
            requirement_task_ids = {
                task_id
                for value in (requirement.get("task_ids") or [])
                if (task_id := _id(value)) is not None
            }
            # A requirement must be explicitly scoped to this single station
            # and its tasks; never borrow one from another station or vehicle.
            if station_ids != {requested} or not requirement_task_ids:
                continue
            if not requirement_task_ids.issubset(incident_task_ids):
                continue

            skills = []
            for skill in requirement.get("skills") or []:
                if not isinstance(skill, dict):
                    continue
                skill_id = _id(skill.get("skill_id"))
                required = _optional_nonnegative_int(skill.get("required"))
                if skill_id is None or required is None:
                    continue

                source = skill.get("coverage_source")
                assignment_count_source = (
                    source == "warning_statuses"
                    or (
                        source == "incident_skill_assignments"
                        and individual_assignments_available
                    )
                )
                # 'available_memberships' is availability, not assignments.
                assigned = (
                    _optional_nonnegative_int(skill.get("assigned"))
                    if assignment_count_source
                    else None
                )
                current_code = _label(skill.get("short_code"))
                observed_codes = (
                    known_task_skill_codes.get((ts_task_id, skill_id), set())
                    if ts_task_id else set()
                )
                # A unique historical code can restore a missing label, but
                # conflicting labels must never be guessed away.
                resolved_code = (
                    current_code if current_code
                    else next(iter(observed_codes)) if len(observed_codes) == 1
                    else None
                )
                unambiguous_asp = (
                    resolved_code is not None
                    and resolved_code.casefold() in {"asp", "aspirant"}
                    and observed_codes.issubset({"asp", "aspirant"})
                )
                supplementary = bool(ts_task_id and unambiguous_asp)

                # The warning status count may be larger than the number of
                # explicit role assignments. Keep both evidence types separate.
                individual_count = (
                    _optional_nonnegative_int(
                        skill.get("individual_assignment_count")
                    )
                    if individual_assignments_available
                    and len(incident_task_ids) == 1
                    else None
                )
                skills.append({
                    "skill_id": skill_id,
                    "short_code": resolved_code,
                    "short_code_source": (
                        "retained_incident_requirement" if current_code
                        else "same_station_task_retained_history"
                        if resolved_code else "unresolved"
                    ),
                    "required": required,
                    "assigned": assigned,
                    "shortfall": max(0, required - assigned)
                    if assigned is not None else None,
                    "coverage_source": source,
                    "individual_assignment_count": individual_count,
                    "individual_assignment_shortfall": (
                        max(0, required - individual_count)
                        if individual_count is not None else None
                    ),
                    "position_type": (
                        "supplemental" if supplementary else "regular"
                    ),
                    "position_type_source": (
                        "ts_asp_confirmed_additional_position"
                        if supplementary else "not_identified_as_supplemental"
                    ),
                })

            if not skills:
                continue
            any_shortfall = any(
                skill["shortfall"] is not None and skill["shortfall"] > 0
                for skill in skills
            )
            all_known = all(skill["shortfall"] is not None for skill in skills)

            def assignment_sufficient(items: list[dict]) -> bool | None:
                if not items:
                    return None
                shortages = [
                    item["individual_assignment_shortfall"] for item in items
                ]
                if any(n is not None and n > 0 for n in shortages):
                    return False
                if any(n is None for n in shortages):
                    return None
                return True

            regular = [
                item for item in skills if item["position_type"] == "regular"
            ]
            supplementary = [
                item for item in skills if item["position_type"] == "supplemental"
            ]
            enriched["crew_requirement_evidence"].append({
                "availability_requirement_id": _id(
                    requirement.get("availability_requirement_id")
                ),
                "task_ids": sorted(requirement_task_ids, key=int),
                "skills": skills,
                "sufficient": (
                    False if any_shortfall else True if all_known else None
                ),
                "regular_crew_sufficient": assignment_sufficient(regular),
                "supplemental_positions_sufficient": (
                    assignment_sufficient(supplementary)
                ),
                "regular_coverage_source": (
                    "individual_incident_skill_assignment_records"
                    if individual_assignments_available
                    and len(incident_task_ids) == 1
                    else "no_task_scoped_individual_assignment_evidence"
                ),
            })

        enriched["crew_coverage_status"] = (
            "recorded_skill_requirements_found"
            if enriched["crew_requirement_evidence"]
            else "no_unambiguous_station_task_requirements"
        )
        rows.append(enriched)

    result["incident_evidence_overview"] = rows
    result["crew_coverage_source"] = (
        "retained_ha_incident_snapshot_not_fairness_audit_time"
    )
    result["crew_coverage_interpretation"] = (
        "The original sufficient field compares all API-configured skill "
        "requirements and warning counts. It includes any additional Asp "
        "position. For a singly identified TS, Asp is supplementary, and "
        "regular_crew_sufficient uses explicit individual skill-assignment "
        "records while supplemental_positions_sufficient is separate. "
        "Some warning_statuses counts exceed individual assignment counts "
        "and must not be presented as actual vehicle crew. All evidence is "
        "retrospective, not verified physical turnout. Overlapping skills "
        "must not be summed into unique personnel positions; missing "
        "individual records or ambiguous task/skill labels stay unknown."
    )
    return result

def build_one_time_incident_staffing_evidence(
    *,
    station_id: int | str,
    cached_fairness_record: dict[str, Any],
    api_incident: dict[str, Any] | None,
    normalized_staffing: dict[str, Any] | None,
    task_index: dict[Any, list[dict[str, Any]]],
    retained_history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Safely inspect a cached fairness incident no longer retained by HA.

    This uses exactly one explicitly requested incident API snapshot and the
    existing dynamic staffing normalizer. It does NOT fetch the fairness audit,
    persist data, restore old HA history, or expose personal information.
    """
    requested_station = _id(station_id)
    incident_id = _id(cached_fairness_record.get("incident_id"))
    if (
        requested_station is None
        or incident_id is None
        or _id(cached_fairness_record.get("station_id")) != requested_station
    ):
        raise ValueError("Historical fairness record is not for this station")

    expected_tasks = {
        task_id
        for value in cached_fairness_record.get("incident_task_ids") or []
        if (task_id := _id(value)) is not None
    }
    base = {
        "incident_id": incident_id,
        "station_id": requested_station,
        "request_scope": "single_cached_historical_incident",
        "source": "one_time_authenticated_incident_api_get",
        "historical_audit_refetched": False,
        "fairness_cache_modified": False,
        "local_incident_history_modified": False,
        "api_record_checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if not expected_tasks:
        return {
            **base,
            "crew_coverage_status": "cached_incident_task_ids_unavailable",
            "crew_requirement_evidence": [],
        }

    if not isinstance(api_incident, dict) or _id(api_incident.get("id")) != incident_id:
        return {
            **base,
            "crew_coverage_status": "api_incident_missing_or_id_mismatch",
            "crew_requirement_evidence": [],
        }

    fetched_tasks = {
        task_id
        for value in api_incident.get("task_ids") or []
        if (task_id := _id(value)) is not None
    }
    if fetched_tasks != expected_tasks:
        return {
            **base,
            "crew_coverage_status": "api_task_ids_differ_from_cached_fairness",
            "cached_task_ids": sorted(expected_tasks, key=int),
            "api_task_ids": sorted(fetched_tasks, key=int),
            "crew_requirement_evidence": [],
        }

    if not isinstance(normalized_staffing, dict) or not isinstance(
        normalized_staffing.get("crew_requirements"), list
    ):
        return {
            **base,
            "crew_coverage_status": "api_staffing_requirements_unavailable",
            "crew_requirement_evidence": [],
        }

    compact = enrich_compact_history_task_names(
        {
            "incident_evidence_overview": [{
                "incident_id": incident_id,
                "incident_task_ids": sorted(expected_tasks, key=int),
            }],
        },
        task_index,
        requested_station,
    )

    # Append the just-fetched staffing *last* so its ID takes precedence.
    # The other locally retained snapshots are used only to resolve missing
    # role short codes for this station, task and skill.
    current = {
        "id": incident_id,
        "crew_requirements": normalized_staffing["crew_requirements"],
        "crew_summary": normalized_staffing.get("crew_summary"),
    }
    preview = enrich_compact_history_crew_coverage(
        compact, [*retained_history, current], requested_station
    )
    evidence = preview["incident_evidence_overview"][0]
    return {
        **base,
        "incident_task_ids": sorted(expected_tasks, key=int),
        "resolved_tasks": evidence.get("resolved_tasks", []),
        "crew_coverage_status": evidence.get("crew_coverage_status"),
        "crew_requirement_evidence": evidence.get("crew_requirement_evidence", []),
        "interpretation": (
            "On-demand retrospective API staffing evidence for this incident. "
            "Not a snapshot at fairness proposal time or proof of physical "
            "vehicle turnout. Function counts can overlap; supplemental "
            "positions are evaluated separately where identifiable."
        ),
    }
