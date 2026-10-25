"""Single-GET, private, read-only probe for a historical candidate schedule.

Never query a bulk roster, save data, return a membership identifier/name,
or claim that a readable schedule makes the entire station roster available.
This is strictly to validate API access and interval structure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .historical_fairness import _id, _label


def _station_group_memberships(
    groups: list[dict[str, Any]], station_id: str,
) -> tuple[set[str], dict[str, int | None]]:
    """Find only cached station/descendant group memberships marked active."""
    matching: set[str] = set()
    ids_to_users: dict[str, int | None] = {}
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        group_id = _id(group.get("id"))
        ancestors = {
            item
            for raw in group.get("ancestor_ids") or []
            if (item := _id(raw)) is not None
        }
        if not (
            group_id == station_id
            or station_id in ancestors
            or _id(group.get("parent_group_id")) == station_id
        ):
            continue
        for member in group.get("memberships") or []:
            if not isinstance(member, dict):
                continue
            if _label(member.get("status")).casefold() != "active":
                continue
            membership_id = _id(member.get("id"))
            if membership_id is None:
                continue
            matching.add(membership_id)
            user_id = _id(member.get("user_id"))
            ids_to_users[membership_id] = int(user_id) if user_id else None
    return matching, ids_to_users


def choose_one_candidate_schedule_probe(
    records: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    task_index: dict[Any, Any],
    station_id: int | str,
    task_id: int | str,
) -> tuple[int | None, dict[str, Any]]:
    """Select one previously proposed membership in this station/task only.

    Selection is deterministic and NOT a ranking or likelihood estimate.
    The returned candidate ID is internal to the service; the safe response
    has no identifiers. No network request is performed by this function.
    """
    station = _id(station_id)
    task = _id(task_id)
    if station is None or task is None:
        raise ValueError("station_id and task_id must be numeric")

    indexed = any(
        _id(key) == task
        and isinstance(tasks, list)
        and any(
            isinstance(item, dict)
            and _id(item.get("id")) == task
            and _id(item.get("station_id")) == station
            for item in tasks
        )
        for key, tasks in (task_index or {}).items()
    )
    base = {
        "station_id": station,
        "task_id": task,
        "probe_scope": "one_historical_candidate_one_authenticated_GET",
        "source": "cached_fairness_proposals_and_group_memberships",
        "historical_proposal_candidate_count": 0,
        "active_related_group_membership_match_count": 0,
        "active_related_group_distinct_user_ids": 0,
        "api_get_attempted": False,
        "remote_schedule_data_persisted": False,
        "candidate_identifiers_returned": False,
        "current_station_crew_eligibility_verified": False,
        "full_station_availability_verified": False,
        "selected_candidate_represents_predicted_lineup": False,
    }
    if not indexed:
        return None, {
            **base,
            "probe_status": "task_not_indexed_for_this_station",
        }

    candidate_ids: set[str] = set()
    recent_records = []
    for record in records:
        if (
            not isinstance(record, dict)
            or record.get("source")
            != "complete_audit_latest_fairness_proposal"
            or _id(record.get("station_id")) != station
            or (record.get("unmatched_proposal_seats") or 0) > 0
            or (record.get("ambiguous_name_seats") or 0) > 0
        ):
            continue
        tasks = {
            item
            for raw in record.get("incident_task_ids") or []
            if (item := _id(raw)) is not None
        }
        if tasks != {task}:
            continue
        people = record.get("people") or []
        if not isinstance(people, list):
            continue
        memberships = {
            member
            for person in people
            if isinstance(person, dict)
            if (member := _id(person.get("membership_id"))) is not None
        }
        if memberships:
            candidate_ids.update(memberships)
            recent_records.append((
                str(record.get("latest_proposal_at") or ""),
                _id(record.get("incident_id")) or "",
                memberships,
            ))

    current_memberships, users = _station_group_memberships(groups, station)
    matched = candidate_ids.intersection(current_memberships)
    base["historical_proposal_candidate_count"] = len(candidate_ids)
    base["active_related_group_membership_match_count"] = len(matched)
    base["active_related_group_distinct_user_ids"] = len({
        value for value in users.values() if value is not None
    })
    if not matched:
        return None, {
            **base,
            "probe_status": "no_history_member_match_in_active_cached_groups",
        }

    # Latest proposal merely provides a reproducible sample. No rank, role
    # preference or probability is inferred. Sort numeric IDs, not names.
    for _at, _incident, memberships in sorted(
        recent_records, key=lambda row: (row[0], row[1]), reverse=True
    ):
        choices = matched.intersection(memberships)
        if choices:
            selected = min(choices, key=int)
            return int(selected), {
                **base,
                "probe_status": "ready_for_single_read_only_GET",
                "sampling_rule": "first_numeric_member_in_latest_matching_proposal",
                "membership_selection_is_a_forecast": False,
            }

    return None, {
        **base,
        "probe_status": "no_history_member_match_in_active_cached_groups",
    }


def _current_interval_field_presence(
    interval: dict[str, Any],
) -> dict[str, Any]:
    """Inspect a narrow allowlist of field *types*, never the values."""
    details = interval.get("detailed_availability")
    kinds = (
        ("standby_duty", "standby_duty"),
        ("exception", "exception"),
        ("recurring", "recurring"),
    )
    nested = [
        details.get(key)
        for key, _label in kinds
        if isinstance(details, dict)
        and isinstance(details.get(key), dict)
    ]
    return {
        "available_is_boolean": isinstance(interval.get("available"), bool),
        "active_is_boolean": isinstance(interval.get("active"), bool),
        "skill_ids_is_list": isinstance(interval.get("skill_ids"), list),
        "assigned_function_ids_is_list": isinstance(
            interval.get("assigned_function_ids"), list
        ),
        "detailed_availability_is_object": isinstance(details, dict),
        "detail_kinds_present": [
            label for key, label in kinds
            if isinstance(details, dict) and key in details
        ],
        "nested_skill_ids_is_list": any(
            isinstance(obj.get("skill_ids"), list) for obj in nested
        ),
        "nested_assigned_function_ids_is_list": any(
            isinstance(obj.get("assigned_function_ids"), list)
            for obj in nested
        ),
    }


def summarize_one_candidate_schedule_probe(
    safe_selection: dict[str, Any],
    schedule: Any,
    checked_at: datetime,
) -> dict[str, Any]:
    """Return only the API-readability result, never an individual's schedule."""
    base = {
        **safe_selection,
        "api_get_attempted": True,
        "api_endpoint": "memberships/<selected>/combined_schedule",
        "schedule_checked_at": checked_at.isoformat(),
        "current_candidate_available": None,
        "current_candidate_duty_type": None,
        "current_station_crew_eligibility_verified": False,
        "full_station_availability_verified": False,
        "remote_schedule_data_persisted": False,
    }
    if not isinstance(schedule, dict):
        return {
            **base,
            "probe_status": "api_schedule_unavailable_or_permission_denied",
            "schedule_response_structure_readable": False,
            "schedule_interval_count": None,
            "current_interval_present": None,
        }

    intervals = schedule.get("intervals")
    if not isinstance(intervals, list):
        return {
            **base,
            "probe_status": "unexpected_schedule_response_structure",
            "schedule_response_structure_readable": False,
            "schedule_interval_count": None,
            "current_interval_present": None,
        }

    current_intervals: list[dict[str, Any]] = []
    valid_interval_count = 0
    for interval in intervals[:500]:
        if not isinstance(interval, dict):
            continue
        start_raw = interval.get("start_time")
        end_raw = interval.get("end_time")
        if not isinstance(start_raw, str) or not isinstance(end_raw, str):
            continue
        try:
            start = datetime.fromisoformat(start_raw)
            end = datetime.fromisoformat(end_raw)
            if start.tzinfo is None or end.tzinfo is None:
                continue
            if end <= start:
                continue
            valid_interval_count += 1
            if start <= checked_at < end:
                current_intervals.append(interval)
        except (TypeError, ValueError):
            continue

    # Ambiguous overlapping current intervals are never merged or guessed.
    # Only a *unique* matching interval is eligible for field-shape testing.
    field_presence = (
        _current_interval_field_presence(current_intervals[0])
        if len(current_intervals) == 1 else None
    )
    return {
        **base,
        "probe_status": (
            "readable_schedule_current_interval"
            if current_intervals
            else "readable_schedule_but_no_current_interval"
        ),
        "schedule_response_structure_readable": True,
        "schedule_interval_count": len(intervals),
        "valid_timestamped_interval_count": valid_interval_count,
        "current_interval_present": bool(current_intervals),
        "current_interval_matches": len(current_intervals),
        "current_interval_field_presence": field_presence,
        "interpretation": (
            "The API response format was inspected for one historically "
            "proposed membership only. Field presence checks report schema "
            "types, not the person's available/unavailable status, role or "
            "skill IDs. No individual schedule times, names, IDs, duty types "
            "or predictions are returned. A confirmed different-user match "
            "validates only that one API GET, not full station roster access."
        ),
    }
