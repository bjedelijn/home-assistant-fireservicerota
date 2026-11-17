"""Synthetic privacy-preserving readiness diagnostics."""

import pytest

from custom_components.fireservicerota.fairness_readiness import (
    summarize_forecast_readiness,
)


def inputs():
    return {
        "historical_advisory": {
            "station_id": "194", "task_id": "7674",
            "historical_sample": {"usable_complete_proposal_incidents": 14},
            "historical_roles": [{"historical_candidates": [
                {"name": "PRIVATE SAMPLE", "membership_id": "987654321"}
            ]}],
        },
        "candidate_schedule_probe": {
            "station_id": "194", "task_id": "7674",
            "probe_status": "readable_schedule_current_interval",
            "api_get_attempted": True,
            "schedule_response_structure_readable": True,
            "current_interval_present": True,
            "current_interval_matches": 1,
            "invalid_timestamped_interval_count": 0,
            "current_interval_field_presence": {"available_is_boolean": True},
            "current_candidate_available": None,
            "current_station_crew_eligibility_verified": False,
            "full_station_availability_verified": False,
        },
        "aggregate_coverage_probe": {
            "station_id": "194", "task_id": "7674",
            "api_get_attempted": True,
            "current_api_requirement_id_matches": True,
            "current_api_task_ids_match": False,
            "current_api_requested_task_included": True,
            "current_api_task_mapping_status": "shared_same_station_tasks_verified",
            "shared_task_station_scope_verified": True,
            "current_aggregate_scope": "shared_requirement_same_station_not_task_specific",
            "current_aggregate_skill_coverage_checked": True,
            "current_interval_matches": 1,
            "invalid_timestamped_interval_count": 0,
            "current_aggregate_skills": [{"skill_id": "7", "reported_assigned_count": 1}],
            "current_personnel_eligibility_verified": False,
            "actual_vehicle_crew_verified": False,
            "predicted_lineup": None,
            "probe_status": "readable_current_shared_requirement_skill_statuses",
            "private": {"membership_id": "123456789", "name": "SECRET"},
        },
    }


def evaluate(**kwargs):
    return summarize_forecast_readiness(station_id=194, task_id=7674, **kwargs)


def test_three_positive_diagnostics_still_do_not_prove_forecast():
    result = evaluate(**inputs())
    assert result["historical_evidence_observed"] is True
    assert result["one_candidate_schedule_format_observed"] is True
    assert result["task_aggregate_coverage_observed"] is True
    assert result["can_predict_next_lineup"] is False
    assert result["predicted_lineup"] is None
    assert len(result["blocking_requirements"]) == 5
    assert "PRIVATE" not in str(result)
    assert "987654321" not in str(result)
    assert "123456789" not in str(result)


def test_foreign_station_probe_never_counts_as_evidence():
    data = inputs()
    data["candidate_schedule_probe"]["station_id"] = "3853"
    result = evaluate(**data)
    assert not result["one_candidate_schedule_format_observed"]
    assert "one_candidate_scope_mismatch" in result["scope_or_input_rejections"]
    assert "single_candidate_schedule_shape_unconfirmed" in result["blocking_requirements"]


def test_foreign_task_history_never_counts_as_evidence():
    data = inputs()
    data["historical_advisory"]["task_id"] = 7001
    result = evaluate(**data)
    assert result["historical_evidence_observed"] is False
    assert "complete_task_specific_historical_evidence_missing" in result["blocking_requirements"]


def test_overlapping_intervals_do_not_count_as_single_read():
    data = inputs()
    data["candidate_schedule_probe"]["probe_status"] = "ambiguous_overlapping_current_intervals"
    data["candidate_schedule_probe"]["current_interval_matches"] = 2
    assert evaluate(**data)["one_candidate_schedule_format_observed"] is False


def test_aggregate_without_verified_same_station_scope_is_not_evidence():
    data = inputs()
    data["aggregate_coverage_probe"]["current_aggregate_scope"] = "not_verified"
    assert evaluate(**data)["task_aggregate_coverage_observed"] is False


def test_empty_inputs_fail_closed_without_personal_information():
    result = evaluate(
        historical_advisory=None,
        candidate_schedule_probe=None,
        aggregate_coverage_probe=None,
    )
    assert result["readiness_status"] == "forecast_not_ready"
    assert result["predicted_lineup"] is None
    assert len(result["scope_or_input_rejections"]) == 3


def test_invalid_ids_rejected():
    import pytest

    with pytest.raises(ValueError):
        summarize_forecast_readiness(
            station_id=True, task_id=7674,
            historical_advisory=None,
            candidate_schedule_probe=None,
            aggregate_coverage_probe=None,
        )


def test_valid_single_task_requirement_is_diagnostic_evidence():
    data = inputs()
    agg = data["aggregate_coverage_probe"]
    agg.update({
        "current_aggregate_scope": "single_task_requirement",
        "current_api_task_ids_match": True,
        "current_api_requested_task_included": True,
        "current_api_task_mapping_status": "single_requested_task",
        "shared_task_station_scope_verified": False,
        "probe_status": "readable_current_task_aggregate_skill_statuses",
    })
    result = evaluate(**data)
    assert result["task_aggregate_coverage_observed"] is True
    assert result["can_predict_next_lineup"] is False


def test_shared_task_requirement_without_station_confirmation_is_rejected():
    data = inputs()
    data["aggregate_coverage_probe"]["shared_task_station_scope_verified"] = False
    assert evaluate(**data)["task_aggregate_coverage_observed"] is False


def test_shared_task_requirement_without_requested_task_is_rejected():
    data = inputs()
    data["aggregate_coverage_probe"]["current_api_requested_task_included"] = False
    assert evaluate(**data)["task_aggregate_coverage_observed"] is False


def test_mismatch_requirement_id_is_not_usable():
    data = inputs()
    data["aggregate_coverage_probe"]["current_api_requirement_id_matches"] = False
    assert evaluate(**data)["task_aggregate_coverage_observed"] is False


def test_missing_required_success_status_is_not_evidence():
    data = inputs()
    data["aggregate_coverage_probe"]["probe_status"] = "no_current_interval"
    assert evaluate(**data)["task_aggregate_coverage_observed"] is False


def test_shared_requirements_are_not_exclusive_ts_coverage():
    result = evaluate(**inputs())
    assert result["task_aggregate_coverage_observed"] is True
    assert result["full_station_candidate_pool_verified"] is False
    assert result["distinct_seat_model_verified"] is False
    assert result["predicted_lineup"] is None


@pytest.mark.parametrize("field,value", [
    ("api_get_attempted", False),
    ("schedule_response_structure_readable", False),
    ("current_interval_present", False),
    ("current_interval_matches", True),
    ("current_interval_matches", 2),
    ("invalid_timestamped_interval_count", True),
    ("invalid_timestamped_interval_count", 1),
    ("current_candidate_available", True),
    ("current_station_crew_eligibility_verified", True),
    ("full_station_availability_verified", True),
])
def test_one_candidate_false_success_signals_fail_closed(field, value):
    data = inputs()
    data["candidate_schedule_probe"][field] = value
    result = evaluate(**data)
    assert result["one_candidate_schedule_format_observed"] is False
    assert result["can_predict_next_lineup"] is False
    assert result["predicted_lineup"] is None


@pytest.mark.parametrize("field,value", [
    ("current_interval_matches", True),
    ("current_interval_matches", 2),
    ("invalid_timestamped_interval_count", True),
    ("invalid_timestamped_interval_count", 1),
    ("current_aggregate_skills", []),
    ("current_aggregate_skills", None),
    ("current_aggregate_skills", {}),
    ("current_personnel_eligibility_verified", True),
    ("actual_vehicle_crew_verified", True),
    ("predicted_lineup", ["PRIVATE"]),
])
def test_aggregate_false_success_signals_fail_closed(field, value):
    data = inputs()
    data["aggregate_coverage_probe"][field] = value
    result = evaluate(**data)
    assert result["task_aggregate_coverage_observed"] is False
    assert result["can_predict_next_lineup"] is False
    assert "PRIVATE" not in str(result)


def test_cached_roster_scope_is_visible_but_never_forecast_ready():
    data = inputs()
    result = evaluate(**data, roster_scope_diagnostic={
        "station_id": 194,
        "diagnostic_status": "cached_partial_scope_only",
        "station_discovered": True,
        "cached_distinct_user_count_if_fully_linked": 25,
        "current_station_full_roster_verified": False,
        "current_station_all_member_availability_verified": False,
        "current_station_all_member_skills_verified": False,
        "can_build_operational_prediction": False,
        "predicted_lineup": None,
        "name": "PRIVATE PERSON",
    })
    assert result["cached_roster_source_reach"] == "station_group_seen_but_not_certified"
    assert result["full_station_candidate_pool_verified"] is False
    assert result["can_predict_next_lineup"] is False
    assert "PRIVATE" not in str(result)
    assert "25" not in str(result)


def test_roster_scope_wrong_station_is_rejected():
    result = evaluate(**inputs(), roster_scope_diagnostic={
        "station_id": 3853,
        "diagnostic_status": "cached_partial_scope_only",
    })
    assert result["cached_roster_source_reach"] == "not_observed"
    assert "roster_scope_station_mismatch" in result["scope_or_input_rejections"]


@pytest.mark.parametrize("unsafe_claim", [
    ("can_build_operational_prediction", True),
    ("current_station_full_roster_verified", True),
    ("current_station_all_member_availability_verified", True),
    ("current_station_all_member_skills_verified", True),
    ("predicted_lineup", ["PRIVATE PERSON"]),
])
def test_roster_scope_rejects_unsupported_operational_claim(unsafe_claim):
    key, value = unsafe_claim
    scope = {
        "station_id": 194,
        "diagnostic_status": "cached_partial_scope_only",
        "station_discovered": True,
        "current_station_full_roster_verified": False,
        "current_station_all_member_availability_verified": False,
        "current_station_all_member_skills_verified": False,
        "can_build_operational_prediction": False,
        "predicted_lineup": None,
    }
    scope[key] = value
    result = evaluate(**inputs(), roster_scope_diagnostic=scope)
    assert result["cached_roster_source_reach"] == "not_observed"
    assert "roster_scope_unsafe_claim" in result["scope_or_input_rejections"]
    assert result["predicted_lineup"] is None


def test_roster_scope_rejected_input_does_not_get_partial_success():
    result = evaluate(**inputs(), roster_scope_diagnostic={
        "station_id": 194,
        "diagnostic_status": "groups_structure_invalid",
        "station_discovered": False,
        "current_station_full_roster_verified": False,
        "current_station_all_member_availability_verified": False,
        "current_station_all_member_skills_verified": False,
        "can_build_operational_prediction": False,
        "predicted_lineup": None,
    })
    assert result["cached_roster_source_reach"] == "cache_input_unusable"
    assert result["can_predict_next_lineup"] is False
