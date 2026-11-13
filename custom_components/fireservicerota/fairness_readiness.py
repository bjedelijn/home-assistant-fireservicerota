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

    history = valid.get("historical", {})
    sample = history.get("historical_sample")
    sample = sample if isinstance(sample, Mapping) else {}
    complete = sample.get("usable_complete_proposal_incidents", 0)
    history_present = type(complete) is int and complete > 0
    one = valid.get("one_candidate", {})
    shape = one.get("current_interval_field_presence")
    unique_interval = (
        one.get("probe_status") == "readable_schedule_current_interval"
        and one.get("current_interval_matches") == 1
        and isinstance(shape, Mapping)
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
