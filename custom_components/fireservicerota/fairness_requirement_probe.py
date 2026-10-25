"""Bounded, read-only, anonymized appliance requirement schedule diagnostics.

One user-authorized station/task; exactly one historical requirement ID; at
most one authenticated GET to the officially documented requirement schedule.
Never expose individual available_memberships, user IDs, candidate records,
location/attendance, or any raw response. Not a lineup prediction.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from .historical_fairness import _id, _label, _optional_nonnegative_int

_MAX_INTERVALS = 500
_MAX_SKILLS = 30
_SERVICE_LEVELS = frozenset({"in_service", "out_of_service"})
_WARNING_LEVELS = frozenset({
    "below_required", "on_required", "below_buffer",
    "on_buffer", "above_buffer",
})


def choose_historical_task_requirement(
    crew_overview: dict[str, Any],
    station_id: int | str,
    task_id: int | str,
    task_index: dict[Any, Any],
) -> tuple[str | None, dict[str, Any]]:
    """Require a unique previously observed requirement for the single task."""
    station = _id(station_id)
    task = _id(task_id)
    if station is None or task is None:
        raise ValueError("station and task IDs must be numeric")

    base = {
        "station_id": station,
        "task_id": task,
        "source": "single_station_task_historical_crew_requirements",
        "request_scope": "one_availability_requirement_one_authenticated_GET",
        "api_get_attempted": False,
        "brandweerrooster_modified": False,
        "local_storage_modified": False,
        "individual_membership_data_returned": False,
        "predicted_lineup": None,
        "current_personnel_eligibility_verified": False,
        "historical_requirement_ids_seen": 0,
        "matching_historical_incidents": 0,
    }
    task_matches = [
        item
        for candidate_id, entries in (task_index or {}).items()
        if _id(candidate_id) == task and isinstance(entries, list)
        for item in entries
        if isinstance(item, dict)
        and _id(item.get("id")) == task
        and _id(item.get("station_id")) == station
    ]
    if not task_matches:
        return None, {**base, "probe_status": "task_not_indexed_for_station"}

    if (
        not isinstance(crew_overview, dict)
        or _id(crew_overview.get("station_id")) != station
    ):
        return None, {**base, "probe_status": "history_station_mismatch"}

    requirement_ids: set[str] = set()
    skill_labels: dict[str, set[str]] = {}
    skill_positions: dict[str, set[str]] = {}
    skill_required: dict[str, set[int]] = {}
    matching_incidents: set[str] = set()
    for row in crew_overview.get("incident_evidence_overview") or []:
        if not isinstance(row, dict):
            continue
        incident = _id(row.get("incident_id"))
        incident_tasks = {
            parsed
            for value in row.get("incident_task_ids") or []
            if (parsed := _id(value)) is not None
        }
        if incident is None or incident_tasks != {task}:
            continue
        if row.get("crew_coverage_status") != "recorded_skill_requirements_found":
            continue
        for requirement in row.get("crew_requirement_evidence") or []:
            if not isinstance(requirement, dict):
                continue
            requirement_tasks = {
                parsed
                for value in requirement.get("task_ids") or []
                if (parsed := _id(value)) is not None
            }
            if requirement_tasks != {task}:
                continue
            req_id = _id(requirement.get("availability_requirement_id"))
            if req_id is None:
                continue
            requirement_ids.add(req_id)
            matching_incidents.add(incident)
            for skill in requirement.get("skills") or []:
                if not isinstance(skill, dict):
                    continue
                skill_id = _id(skill.get("skill_id"))
                if skill_id is None:
                    continue
                name = _label(skill.get("short_code"))
                if name:
                    skill_labels.setdefault(skill_id, set()).add(name.casefold())
                kind = skill.get("position_type")
                if kind in {"regular", "supplemental"}:
                    skill_positions.setdefault(skill_id, set()).add(kind)
                required = _optional_nonnegative_int(skill.get("required"))
                if required is not None:
                    skill_required.setdefault(skill_id, set()).add(required)

    base["matching_historical_incidents"] = len(matching_incidents)
    base["historical_requirement_ids_seen"] = len(requirement_ids)
    if len(requirement_ids) != 1:
        return None, {
            **base,
            "probe_status": (
                "ambiguous_historical_requirement_ids"
                if requirement_ids else "no_historical_requirement_id"
            ),
        }

    req_id = next(iter(requirement_ids))
    historical_skills = []
    for skill_id in sorted(
        set(skill_required) | set(skill_labels) | set(skill_positions),
        key=int,
    ):
        labels = skill_labels.get(skill_id, set())
        types = skill_positions.get(skill_id, set())
        counts = skill_required.get(skill_id, set())
        historical_skills.append({
            "skill_id": skill_id,
            "historical_short_code": next(iter(labels)) if len(labels) == 1 else None,
            "historical_position_type": next(iter(types)) if len(types) == 1 else "unknown",
            "historical_required_min": min(counts) if counts else None,
            "historical_required_max": max(counts) if counts else None,
        })
    return req_id, {
        **base,
        "probe_status": "ready_for_single_read_only_GET",
        "historical_availability_requirement_id": req_id,
        "historical_skill_context": historical_skills,
        "historical_skill_context_not_current_config": True,
    }


def _int_count(raw: Any) -> int | None:
    value = _optional_nonnegative_int(raw)
    return value if value is not None and value <= 10000 else None


def _enum(raw: Any, choices: frozenset[str]) -> str | None:
    value = _label(raw).casefold()
    return value if value in choices else None


def _skill_config(raw: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list) or len(raw) > _MAX_SKILLS:
        return None
    result = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            return None
        skill = _id(item.get("skill_id"))
        if skill is None or skill in seen:
            return None
        seen.add(skill)
        result.append({
            "skill_id": skill,
            "configured_assigned_required": _int_count(item.get("assigned")),
            "configured_standby_required": _int_count(item.get("standby")),
        })
    return sorted(result, key=lambda item: int(item["skill_id"]))


def _skill_statuses(raw: Any, expected_ids: set[str]) -> tuple[
    list[dict[str, Any]] | None, int | None,
]:
    if not isinstance(raw, list) or len(raw) > _MAX_SKILLS:
        return None, None
    result = []
    unknown = 0
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            return None, None
        skill = _id(item.get("skill_id"))
        if skill is None or skill in seen:
            return None, None
        seen.add(skill)
        if skill not in expected_ids:
            unknown += 1
            continue
        result.append({
            "skill_id": skill,
            "reported_level": _enum(item.get("level"), _WARNING_LEVELS),
            "reported_minimum": _int_count(item.get("minimum")),
            "reported_buffer": _int_count(item.get("buffer")),
            "reported_assigned_count": _int_count(item.get("assigned_count")),
            # In particular, DO NOT copy available_memberships or other users.
        })
    return sorted(result, key=lambda item: int(item["skill_id"])), unknown


_SAFE_TASK_NAME = re.compile(r"[A-Za-z][A-Za-z0-9 ._()/\\-]{0,39}\\Z")


def _resolve_shared_task_station_scope(
    task_ids: set[str],
    station_id: str | None,
    task_index: dict[Any, Any] | None,
) -> list[dict[str, str]] | None:
    """Match *every* shared task to one distinct, station-scoped task entry.

    An ambiguous, cross-station, missing or person-like task label fails closed.
    These group-discovery records are cached, not independently live data.
    """
    if (
        station_id is None or not isinstance(task_index, dict)
        or not 2 <= len(task_ids) <= 8
    ):
        return None
    resolved = []
    for task_id in sorted(task_ids, key=int):
        matches = [
            entry
            for key, entries in task_index.items()
            if _id(key) == task_id
            and isinstance(entries, list)
            for entry in entries
        ]
        if len(matches) != 1:
            return None
        entry = matches[0]
        if (
            not isinstance(entry, dict)
            or _id(entry.get("id")) != task_id
            or _id(entry.get("station_id")) != station_id
        ):
            return None
        name = _label(entry.get("name"))
        if not _SAFE_TASK_NAME.fullmatch(name):
            return None
        resolved.append({"id": task_id, "name": name})
    return resolved


def summarize_task_requirement_schedule(
    selection: dict[str, Any],
    schedule: Any,
    checked_at: datetime,
    *,
    task_index: dict[Any, Any] | None = None,
) -> dict[str, Any]:
    """Extract scoped current aggregate task/skill coverage, never crew names."""
    expected_requirement = _id(
        selection.get("historical_availability_requirement_id")
    )
    task = _id(selection.get("task_id"))
    if expected_requirement is None or task is None:
        raise ValueError("No validated historical task requirement selected")
    base = {
        **selection,
        "api_get_attempted": True,
        "api_endpoint": "availability_requirements/<selected>/schedule",
        "api_checked_at": checked_at.isoformat(),
        "current_api_requirement_id_matches": None,
        "current_api_task_ids_match": None,
        "api_reported_task_ids": [],
        "api_reported_task_ids_count": None,
        "current_api_requested_task_included": None,
        "current_api_task_mapping_status": "unverified",
        "shared_task_station_scope_verified": False,
        "shared_task_station_scope_source": (
            "cached_authenticated_station_task_index_not_live"
        ),
        "resolved_requirement_tasks": [],
        "current_aggregate_scope": "not_verified",
        "current_aggregate_service_level": None,
        "current_aggregate_warning_level": None,
        "current_aggregate_skills": [],
        "current_requirement_configuration": [],
        "current_aggregate_skill_coverage_checked": False,
        "current_personnel_eligibility_verified": False,
        "individual_membership_data_returned": False,
        "predicted_lineup": None,
        "actual_vehicle_crew_verified": False,
        "brandweerrooster_modified": False,
        "local_storage_modified": False,
        "prediction_status": "current_task_aggregate_not_lineup_prediction",
    }
    if not isinstance(schedule, dict):
        return {
            **base,
            "probe_status": "api_schedule_unavailable_or_permission_denied",
        }
    meta = schedule.get("availability_requirement")
    if not isinstance(meta, dict):
        return {**base, "probe_status": "api_requirement_metadata_missing"}

    if _id(meta.get("id")) != expected_requirement:
        return {
            **base,
            "current_api_requirement_id_matches": False,
            "probe_status": "api_requirement_id_mismatch",
        }
    base["current_api_requirement_id_matches"] = True

    # The official appliance endpoint can list multiple task IDs for one
    # availability requirement. Inspect only tightly bounded numeric task IDs;
    # NEVER treat membership IDs, names or raw API objects as safe diagnostics.
    raw_task_ids = meta.get("task_ids")
    if raw_task_ids is None or raw_task_ids == []:
        base["current_api_task_mapping_status"] = "task_ids_missing"
        return {**base, "probe_status": "api_task_ids_missing"}
    if (
        not isinstance(raw_task_ids, list)
        or len(raw_task_ids) > 50
        or any(
            (value := _id(item)) is None
            or len(value) > 18
            or int(value) < 1
            for item in raw_task_ids
        )
    ):
        base["current_api_task_mapping_status"] = "task_ids_invalid"
        return {**base, "probe_status": "api_task_ids_invalid"}

    response_tasks = {str(int(_id(item))) for item in raw_task_ids}
    if len(response_tasks) != len(raw_task_ids):
        base["current_api_task_mapping_status"] = "task_ids_invalid"
        return {**base, "probe_status": "api_task_ids_invalid"}

    ordered_tasks = sorted(response_tasks, key=int)
    base["api_reported_task_ids"] = ordered_tasks
    base["api_reported_task_ids_count"] = len(ordered_tasks)
    base["current_api_requested_task_included"] = task in response_tasks
    base["current_api_task_ids_match"] = response_tasks == {task}

    if task not in response_tasks:
        base["current_api_task_mapping_status"] = "different_tasks"
        return {**base, "probe_status": "api_task_ids_do_not_match"}
    shared = len(response_tasks) != 1
    if shared:
        base["current_api_task_mapping_status"] = "shared_across_tasks"
        resolved = _resolve_shared_task_station_scope(
            response_tasks, _id(selection.get("station_id")), task_index
        )
        if resolved is None:
            return {
                **base,
                "probe_status": "api_requirement_shared_across_tasks",
            }
        # The *requirement* is usable as a station-level aggregate, but its
        # skill counts are not exclusive to either named task/vehicle.
        base["current_api_task_mapping_status"] = (
            "shared_same_station_tasks_verified"
        )
        base["shared_task_station_scope_verified"] = True
        base["resolved_requirement_tasks"] = resolved
        base["current_aggregate_scope"] = (
            "shared_requirement_same_station_not_task_specific"
        )
    else:
        base["current_api_task_mapping_status"] = "single_requested_task"
        base["current_aggregate_scope"] = "single_task_requirement"
    current_config = _skill_config(
        meta.get("single_skill_availability_requirements")
    )
    if current_config is not None:
        base["current_requirement_configuration"] = current_config

    intervals = schedule.get("intervals")
    if not isinstance(intervals, list) or len(intervals) > _MAX_INTERVALS:
        return {**base, "probe_status": "invalid_or_unbounded_intervals"}

    matches = []
    for interval in intervals:
        if not isinstance(interval, dict):
            continue
        start = interval.get("start_time")
        end = interval.get("end_time")
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        try:
            a = datetime.fromisoformat(start)
            b = datetime.fromisoformat(end)
            if a.tzinfo is None or b.tzinfo is None or b <= a:
                continue
            if a <= checked_at < b:
                matches.append(interval)
        except (TypeError, ValueError):
            continue
    base["current_interval_matches"] = len(matches)
    if len(matches) != 1:
        return {
            **base,
            "probe_status": (
                "no_current_interval" if not matches
                else "ambiguous_overlapping_current_intervals"
            ),
        }

    interval = matches[0]
    base["current_aggregate_service_level"] = _enum(
        interval.get("service_level"), _SERVICE_LEVELS
    )
    base["current_aggregate_warning_level"] = _enum(
        interval.get("warning_level"), _WARNING_LEVELS
    )

    expected = {
        _id(item.get("skill_id"))
        for item in selection.get("historical_skill_context") or []
        if isinstance(item, dict) and _id(item.get("skill_id")) is not None
    }
    expected.discard(None)
    config_ids = (
        {item["skill_id"] for item in current_config}
        if current_config is not None else None
    )
    base["current_configuration_matches_historical_skill_ids"] = (
        config_ids == expected if config_ids is not None and expected else None
    )
    statuses, unknown_skill_count = _skill_statuses(
        interval.get("skill_statuses"), expected
    )
    if statuses is None or not statuses:
        return {
            **base,
            "probe_status": "aggregate_skill_statuses_missing_or_ambiguous",
        }
    base["current_aggregate_skills"] = statuses
    base["current_unmatched_skill_status_count"] = unknown_skill_count
    base["current_aggregate_skill_coverage_checked"] = True
    base["probe_status"] = (
        "readable_current_shared_requirement_skill_statuses"
        if shared else "readable_current_task_aggregate_skill_statuses"
    )
    base["interpretation"] = (
        "This is aggregate current availability-requirement evidence shared "
        "by multiple named tasks at the same station, as resolved from cached "
        "task metadata. It is NOT a separate vehicle count or exclusive "
        "coverage for either task. "
        if shared else
        "This is aggregate current evidence for one task requirement. "
    ) + (
        "'reported_assigned_count' is an API skill status count, NOT "
        "an individually verified vehicle crew. The API requirement ID and "
        "task scope were checked; cached task-index membership is not an "
        "independent live staffing or eligibility check. The live skill "
        "configuration may differ from historical requirements. All individual "
        "available_memberships are discarded. No predicted lineup, person "
        "eligibility judgement or operational availability decision is made."
    )
    return base
