"""Fail-closed fairness forecast input readiness from safe diagnostic summaries.

No personal data, API requests, persistence, ranking or live predictions.
Evidence-only readouts can guide integration development but cannot certify
full-station candidate availability or a distinct physical seat model.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _id(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        n = int(value)
        return str(n) if n > 0 else None
    return None


def summarize_forecast_readiness(
    *,
    station_id: int | str,
    task_id: int | str,
    historical_advisory: Mapping[str, Any] | None,
    candidate_schedule_probe: Mapping[str, Any] | None,
    aggregate_coverage_probe: Mapping[str, Any] | None,
    roster_scope_diagnostic: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return safe missing-input categories without exposing persons.

    This only accepts the existing *sanitized* probe results. It cannot
    upgrade a successful one-person read to a verified whole-station roster.
    Nor does an aggregate requirement create distinct physical seat slots.
    """
    station, task = _id(station_id), _id(task_id)
    if station is None or task is None:
        raise ValueError("station_id and task_id must be positive numeric IDs")
    evidence = {
        "historical": historical_advisory,
        "one_candidate": candidate_schedule_probe,
        "aggregate": aggregate_coverage_probe,
    }
    valid: dict[str, Mapping[str, Any]] = {}
    discarded = []
    for name, item in evidence.items():
        if not isinstance(item, Mapping):
            discarded.append(name + "_absent")
        elif _id(item.get("station_id")) != station or _id(item.get("task_id")) != task:
            discarded.append(name + "_scope_mismatch")
        else:
            valid[name] = item

    # Station-scope evidence has no task_id by design. It describes only
    # cached grouping and MUST NOT certify a complete current candidate pool.
    roster_reach: str = "not_observed"
    if roster_scope_diagnostic is not None:
        if not isinstance(roster_scope_diagnostic, Mapping):
            discarded.append("roster_scope_invalid")
        elif _id(roster_scope_diagnostic.get("station_id")) != station:
            discarded.append("roster_scope_station_mismatch")
        elif (
            roster_scope_diagnostic.get("can_build_operational_prediction") is not False
            or roster_scope_diagnostic.get("current_station_full_roster_verified") is not False
            or roster_scope_diagnostic.get("current_station_all_member_availability_verified") is not False
            or roster_scope_diagnostic.get("current_station_all_member_skills_verified") is not False
            or roster_scope_diagnostic.get("predicted_lineup") is not None
        ):
            discarded.append("roster_scope_unsafe_claim")
        elif roster_scope_diagnostic.get("diagnostic_status") == "cached_partial_scope_only":
            roster_reach = (
                "station_group_seen_but_not_certified"
                if roster_scope_diagnostic.get("station_discovered") is True
                else "station_group_not_found_in_cache"
            )
        else:
            roster_reach = "cache_input_unusable"

    history = valid.get("historical", {})
    sample = history.get("historical_sample")
    sample = sample if isinstance(sample, Mapping) else {}
    complete = sample.get("usable_complete_proposal_incidents", 0)
    history_present = type(complete) is int and complete > 0
    one = valid.get("one_candidate", {})
    shape = one.get("current_interval_field_presence")
    unique_interval = (
        one.get("probe_status") == "readable_schedule_current_interval"
        and one.get("api_get_attempted") is True
        and one.get("schedule_response_structure_readable") is True
        and one.get("current_interval_present") is True
        and type(one.get("current_interval_matches")) is int
        and one.get("current_interval_matches") == 1
        and type(one.get("invalid_timestamped_interval_count")) is int
        and one.get("invalid_timestamped_interval_count") == 0
        and isinstance(shape, Mapping)
        and one.get("current_candidate_available") is None
        and one.get("current_station_crew_eligibility_verified") is False
        and one.get("full_station_availability_verified") is False
    )
    aggregate = valid.get("aggregate", {})
    # Actual output schema from fairness_requirement_probe: a shared
    # same-station requirement has current_api_task_ids_match=False because
    # the API reports TWO task IDs. That is valid shared aggregate evidence,
    # but never task-exclusive coverage or individual availability.
    scope = aggregate.get("current_aggregate_scope")
    one_task = (
        scope == "single_task_requirement"
        and aggregate.get("current_api_task_ids_match") is True
        and aggregate.get("current_api_requested_task_included") is True
        and aggregate.get("current_api_task_mapping_status") == "single_requested_task"
        and aggregate.get("current_api_requirement_id_matches") is True
        and aggregate.get("probe_status")
        == "readable_current_task_aggregate_skill_statuses"
    )
    shared = (
        scope == "shared_requirement_same_station_not_task_specific"
        and aggregate.get("current_api_task_ids_match") is False
        and aggregate.get("current_api_requested_task_included") is True
        and aggregate.get("current_api_task_mapping_status")
        == "shared_same_station_tasks_verified"
        and aggregate.get("shared_task_station_scope_verified") is True
        and aggregate.get("current_api_requirement_id_matches") is True
        and aggregate.get("probe_status")
        == "readable_current_shared_requirement_skill_statuses"
    )
    # Scope is diagnostic only; even a valid current aggregate says nothing
    # about which individual can occupy each seat.
    aggregate_observed = (
        aggregate.get("api_get_attempted") is True
        and aggregate.get("current_aggregate_skill_coverage_checked") is True
        and type(aggregate.get("current_interval_matches")) is int
        and aggregate.get("current_interval_matches") == 1
        and type(aggregate.get("invalid_timestamped_interval_count")) is int
        and aggregate.get("invalid_timestamped_interval_count") == 0
        and isinstance(aggregate.get("current_aggregate_skills"), list)
        and bool(aggregate.get("current_aggregate_skills"))
        and aggregate.get("current_personnel_eligibility_verified") is False
        and aggregate.get("actual_vehicle_crew_verified") is False
        and aggregate.get("predicted_lineup") is None
        and (one_task or shared)
    )
    blockers = [
        "complete_live_station_candidate_pool_unverified",
        "individual_current_availability_unverified",
        "individual_task_qualifications_unverified",
        "distinct_current_required_seats_unverified",
        "held_out_prediction_backtest_missing",
    ]
    if not history_present:
        blockers.append("complete_task_specific_historical_evidence_missing")
    if not unique_interval:
        blockers.append("single_candidate_schedule_shape_unconfirmed")
    if not aggregate_observed:
        blockers.append("current_aggregate_coverage_unconfirmed")
    return {
        "station_id": station,
        "task_id": task,
        "readiness_status": "forecast_not_ready",
        "historical_evidence_observed": history_present,
        "one_candidate_schedule_format_observed": unique_interval,
        "task_aggregate_coverage_observed": aggregate_observed,
        "cached_roster_source_reach": roster_reach,
        "scope_or_input_rejections": discarded,
        "blocking_requirements": blockers,
        "full_station_candidate_pool_verified": False,
        "individual_current_availability_verified": False,
        "individual_task_eligibility_verified": False,
        "distinct_seat_model_verified": False,
        "can_predict_next_lineup": False,
        "predicted_lineup": None,
        "personal_data_included": False,
        "interpretation": (
            "History, one candidate schedule, and current aggregate task status "
            "are three different kinds of evidence. No combination of these "
            "sanitized diagnostics proves a complete eligible and available "
            "station roster or a predictive fairness algorithm."
        ),
    }
