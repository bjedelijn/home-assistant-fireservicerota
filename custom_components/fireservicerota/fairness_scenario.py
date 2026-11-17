"""Pure read-only seat-cover feasibility for future fairness advisory.

The caller must supply an explicitly verified and complete snapshot of *current*
memberships, unambiguous user identities, skills and verified distinct seats. This
module never reads APIs, changes roster state or ranks people by fairness.
A feasible combination is not a predicted dispatch or verified vehicle crew.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

_MAX_MEMBERS = 100
_MAX_SLOTS = 32
_MAX_SNAPSHOT_AGE = timedelta(minutes=5)
_MAX_FUTURE_SKEW = timedelta(seconds=30)


def _numeric(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        number = int(value)
        return str(number) if number > 0 else None
    return None


def _reject(reason: str, station: str | None = None, task: str | None = None) -> dict:
    return {
        "station_id": station,
        "task_id": task,
        "scenario_status": reason,
        "is_operational_prediction": False,
        "predicted_lineup": None,
        "illustrative_assignment": None,
        "staffing_feasible": None,
        "fairness_ranking_performed": False,
    }


def evaluate_verified_seat_scenario(
    *,
    station_id: int | str,
    task_id: int | str,
    current_snapshot: Mapping[str, Any] | None,
    task_requirements: Mapping[str, Any] | None,
    include_membership_ids: bool = False,
    evaluated_at: datetime | None = None,
) -> dict:
    """Evaluate feasibility using unique people and repeated required skill slots.

    Required snapshot structure:
      station_id, observed_at, complete=True, current=True,
      availability_verified=True, eligibility_verified=True,
      members=[{membership_id, user_id, available=True/False, skill_ids=[...]}]
    Required task structure:
      station_id, task_id, observed_at, current=True, verified=True,
      coverage_model='explicit_distinct_seat_slots', slot_model_verified=True,
      slots=[{skill_id, count}]  (regular distinct seats only).

    An API per-skill aggregate required count is NOT proof of distinct seats:
    overlapping skill requirements must never be summed into a seat total.

    The caller must provide an aware evaluated_at timestamp. Observed_at must
    be timezone aware, at most five minutes old and no more than thirty seconds
    in the future. The caller must separately validate source authorization,
    data provenance and its own clock; boolean flags are not independent proof.
    """
    station, task = _numeric(station_id), _numeric(task_id)
    if station is None or task is None:
        return _reject("invalid_station_or_task")
    if not isinstance(include_membership_ids, bool):
        return _reject("invalid_output_option", station, task)
    if not isinstance(current_snapshot, Mapping) or not isinstance(task_requirements, Mapping):
        return _reject("missing_verified_inputs", station, task)
    if (
        _numeric(current_snapshot.get("station_id")) != station
        or _numeric(task_requirements.get("station_id")) != station
        or _numeric(task_requirements.get("task_id")) != task
    ):
        return _reject("station_or_task_scope_mismatch", station, task)
    if not (
        current_snapshot.get("complete") is True
        and current_snapshot.get("current") is True
        and current_snapshot.get("availability_verified") is True
        and current_snapshot.get("eligibility_verified") is True
        and task_requirements.get("verified") is True
        and task_requirements.get("current") is True
        and isinstance(current_snapshot.get("observed_at"), str)
        and current_snapshot.get("observed_at")
    ):
        return _reject("current_availability_or_eligibility_not_verified", station, task)

    if not isinstance(evaluated_at, datetime) or evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        return _reject("evaluation_time_not_verified", station, task)
    try:
        observed_at = datetime.fromisoformat(current_snapshot["observed_at"].replace("Z", "+00:00"))
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            return _reject("invalid_observation_timestamp", station, task)
        age = evaluated_at - observed_at
    except (ValueError, TypeError, OverflowError):
        return _reject("invalid_observation_timestamp", station, task)
    if age < -_MAX_FUTURE_SKEW:
        return _reject("snapshot_from_unverified_future", station, task)
    if age > _MAX_SNAPSHOT_AGE:
        return _reject("stale_current_snapshot", station, task)

    # A fresh personnel snapshot must not be combined with a stale/unknown
    # task configuration. Require independently timestamped task requirements.
    task_observed_raw = task_requirements.get("observed_at")
    if not isinstance(task_observed_raw, str) or not task_observed_raw:
        return _reject("task_requirement_timestamp_missing", station, task)
    try:
        task_observed = datetime.fromisoformat(task_observed_raw.replace("Z", "+00:00"))
        if task_observed.tzinfo is None or task_observed.utcoffset() is None:
            return _reject("task_requirement_timestamp_invalid", station, task)
        task_age = evaluated_at - task_observed
    except (TypeError, ValueError, OverflowError):
        return _reject("task_requirement_timestamp_invalid", station, task)
    if task_age < -_MAX_FUTURE_SKEW:
        return _reject("task_requirement_from_unverified_future", station, task)
    if task_age > _MAX_SNAPSHOT_AGE:
        return _reject("stale_task_requirement_configuration", station, task)

    # API crew_requirements[].skills[].required may encode overlapping skill
    # coverage. Requiring explicit verified seats prevents quietly summing
    # those aggregates into fictitious distinct crew positions.
    if (
        task_requirements.get("coverage_model") != "explicit_distinct_seat_slots"
        or task_requirements.get("slot_model_verified") is not True
    ):
        return _reject("distinct_seat_model_not_verified", station, task)

    raw_slots = task_requirements.get("slots")
    raw_members = current_snapshot.get("members")
    if (
        not isinstance(raw_slots, list) or not 1 <= len(raw_slots) <= _MAX_SLOTS
        or not isinstance(raw_members, list) or len(raw_members) > _MAX_MEMBERS
    ):
        return _reject("invalid_or_unbounded_inputs", station, task)

    slots: list[str] = []
    for row in raw_slots:
        if not isinstance(row, Mapping):
            return _reject("invalid_task_slots", station, task)
        skill = _numeric(row.get("skill_id"))
        count = row.get("count")
        if skill is None or type(count) is not int or not 1 <= count <= _MAX_SLOTS:
            return _reject("invalid_task_slots", station, task)
        if len(slots) + count > _MAX_SLOTS:
            return _reject("too_many_task_slots", station, task)
        slots.extend([skill] * count)

    members: dict[str, set[str]] = {}
    user_ids: set[str] = set()
    for row in raw_members:
        if not isinstance(row, Mapping):
            return _reject("invalid_membership_data", station, task)
        member_id = _numeric(row.get("membership_id"))
        user_id = _numeric(row.get("user_id"))
        raw_skills = row.get("skill_ids")
        if (
            member_id is None or member_id in members
            or type(row.get("available")) is not bool
            or not isinstance(raw_skills, list) or len(raw_skills) > 64
        ):
            return _reject("invalid_or_duplicate_membership", station, task)
        if user_id is None:
            return _reject("user_identity_not_verified", station, task)
        # The same firefighter can have multiple memberships (teams/groups).
        # Until membership-to-user aggregation is explicitly validated, do
        # not silently count those memberships as two separate firefighters.
        if user_id in user_ids:
            return _reject("ambiguous_duplicate_person_memberships", station, task)
        user_ids.add(user_id)
        skills = [_numeric(value) for value in raw_skills]
        if None in skills:
            return _reject("invalid_skill_evidence", station, task)
        if row["available"]:
            members[member_id] = set(skills)
        else:
            members[member_id] = set()

    # The most constrained slot first. A member may only fill a single slot,
    # even when they hold several required qualifications.
    options = [
        sorted(member_id for member_id, skills in members.items() if skill in skills)
        for skill in slots
    ]
    ordering = sorted(range(len(slots)), key=lambda i: (len(options[i]), slots[i], i))
    # Deterministic bipartite maximum matching (augmenting paths), rather
    # than enumerating possible lineups with exponential backtracking.
    # A member is matched to no more than one slot, regardless of skills.
    matched_member_slot: dict[str, int] = {}

    def augment(slot_index: int, visited_members: set[str]) -> bool:
        for member_id in options[slot_index]:
            if member_id in visited_members:
                continue
            visited_members.add(member_id)
            previous_slot = matched_member_slot.get(member_id)
            if previous_slot is None or augment(previous_slot, visited_members):
                matched_member_slot[member_id] = slot_index
                return True
        return False

    feasible = all(augment(slot_index, set()) for slot_index in ordering)
    assigned = {slot_index: member_id for member_id, slot_index in matched_member_slot.items()}
    summary: dict[str, dict[str, int]] = {}
    for i, skill in enumerate(slots):
        group = summary.setdefault(skill, {"required_slots": 0, "eligible_available_members": 0})
        group["required_slots"] += 1
    for skill, group in summary.items():
        group["eligible_available_members"] = sum(skill in values for values in members.values())

    return {
        "station_id": station,
        "task_id": task,
        "scenario_status": "illustrative_feasible" if feasible else "not_feasible_with_supplied_snapshot",
        "is_operational_prediction": False,
        "predicted_lineup": None,
        "staffing_feasible": feasible,
        "required_slot_count": len(slots),
        "available_candidate_count": sum(bool(skills) for skills in members.values()),
        "skill_coverage": [
            {"skill_id": skill, **summary[skill]} for skill in sorted(summary, key=int)
        ],
        "illustrative_assignment": (
            [{"slot": i + 1, "skill_id": skill, "membership_id": assigned[i]}
             for i, skill in enumerate(slots)] if feasible and include_membership_ids else None
        ),
        "member_identifiers_included": bool(feasible and include_membership_ids),
        "fairness_ranking_performed": False,
        "warning": (
            "Feasibility only; input and user-identity verification flags are caller attestations. "
            "A bounded timestamp freshness check is performed, but not source "
            "provenance, clock trust, fairness ordering or physical turnout."
        ),
    }
