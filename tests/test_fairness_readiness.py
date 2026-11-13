"""Synthetic privacy-preserving readiness diagnostics."""

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
            "current_interval_matches": 1,
            "current_interval_field_presence": {"available_is_boolean": True},
            "current_candidate_available": None,
        },
        "aggregate_coverage_probe": {
            "station_id": "194", "task_id": "7674",
            "api_get_attempted": True,
            "current_api_task_ids_match": True,
            "current_aggregate_scope": "shared_requirement_same_station_not_task_specific",
            "current_aggregate_skill_coverage_checked": True,
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
