"""Private, read-only tests for current aggregate appliance task coverage."""

from datetime import datetime, timezone

import pytest

from custom_components.fireservicerota.fairness_requirement_probe import (
    choose_historical_task_requirement,
    summarize_task_requirement_schedule,
)


def sample_overview():
    return {
        "station_id": "194",
        "incident_evidence_overview": [
            {
                "incident_id": "12001",
                "incident_task_ids": ["7674"],
                "crew_coverage_status": "recorded_skill_requirements_found",
                "crew_requirement_evidence": [{
                    "availability_requirement_id": "3690",
                    "task_ids": ["7674"],
                    "skills": [
                        {"skill_id": "7", "short_code": "Bev",
                         "required": 1, "position_type": "regular"},
                        {"skill_id": "1168", "short_code": "Ch",
                         "required": 1, "position_type": "regular"},
                        {"skill_id": "775", "short_code": "Ms",
                         "required": 4, "position_type": "regular"},
                        {"skill_id": "165", "short_code": "Asp",
                         "required": 1, "position_type": "supplemental"},
                    ],
                }],
            },
            {
                "incident_id": "12002",
                "incident_task_ids": ["7674"],
                "crew_coverage_status": "recorded_skill_requirements_found",
                "crew_requirement_evidence": [{
                    "availability_requirement_id": 3690,
                    "task_ids": [7674],
                    "skills": [
                        {"skill_id": "7", "short_code": "Bev",
                         "required": 1, "position_type": "regular"},
                        {"skill_id": "775", "short_code": "Ms",
                         "required": 4, "position_type": "regular"},
                    ],
                }],
            },
            {
                "incident_id": "12003",
                "incident_task_ids": ["7689"],
                "crew_coverage_status": "recorded_skill_requirements_found",
                "crew_requirement_evidence": [{
                    "availability_requirement_id": "9998",
                    "task_ids": ["7689"],
                    "skills": [
                        {"skill_id": "777", "required": 1,
                         "position_type": "regular"}
                    ],
                }],
            },
            {
                "incident_id": "12004",
                "incident_task_ids": ["7674", "7001"],
                "crew_coverage_status": "recorded_skill_requirements_found",
                "crew_requirement_evidence": [{
                    "availability_requirement_id": "9997",
                    "task_ids": ["7674", "7001"],
                    "skills": [],
                }],
            },
            {
                "incident_id": "12005",
                "incident_task_ids": ["7674"],
                "crew_coverage_status": "no_retained_staffing_snapshot",
                "crew_requirement_evidence": [{
                    "availability_requirement_id": "9996",
                    "task_ids": ["7674"],
                }],
            },
        ],
    }


def task_index():
    return {
        7674: [{"id": 7674, "name": "TS", "station_id": 194}],
        7689: [{"id": 7689, "name": "RV", "station_id": 194}],
        7001: [{"id": 7001, "name": "WTS", "station_id": 200}],
    }


def chosen():
    return choose_historical_task_requirement(
        sample_overview(), 194, 7674, task_index()
    )


def sample_schedule():
    return {
        "available_memberships": [
            {"user_name": "TOP SECRET OUTSIDE INTERVAL", "id": 10001}
        ],
        "availability_requirement": {
            "id": 3690,
            "name": "TS 194",
            "task_ids": [7674],
            "group_ids": [194],
            "single_skill_availability_requirements": [
                {"skill_id": 7, "assigned": 1, "standby": 0},
                {"skill_id": 1168, "assigned": 1, "standby": 0},
                {"skill_id": 775, "assigned": 4, "standby": 0},
                {"skill_id": 165, "assigned": 1, "standby": 0},
            ],
        },
        "intervals": [{
            "start_time": "2026-10-25T10:00:00+00:00",
            "end_time": "2026-10-25T11:00:00+00:00",
            "service_level": "in_service",
            "warning_level": "on_required",
            "available_memberships": [
                {"id": 10002, "user_name": "CONFIDENTIAL MEMBER"}
            ],
            "skill_statuses": [
                {"skill_id": 7, "level": "on_required", "minimum": 1,
                 "buffer": 0, "assigned_count": 1,
                 "available_memberships": [
                     {"name": "PRIVATE BEVELVOERDER"}]},
                {"skill_id": 1168, "level": "on_required", "minimum": 1,
                 "buffer": 0, "assigned_count": 1},
                {"skill_id": 775, "level": "on_required", "minimum": 4,
                 "buffer": 0, "assigned_count": 4},
                {"skill_id": 165, "level": "on_required", "minimum": 1,
                 "buffer": 0, "assigned_count": 1},
            ],
        }],
    }


def test_choose_requirement_from_single_task_station_history():
    requirement, selection = chosen()
    assert requirement == "3690"
    assert selection["probe_status"] == "ready_for_single_read_only_GET"
    assert selection["matching_historical_incidents"] == 2
    assert selection["historical_requirement_ids_seen"] == 1
    assert selection["api_get_attempted"] is False
    assert selection["predicted_lineup"] is None
    assert selection["individual_membership_data_returned"] is False
    ids = {
        item["skill_id"]: item
        for item in selection["historical_skill_context"]
    }
    assert set(ids) == {"7", "1168", "775", "165"}
    assert ids["165"]["historical_position_type"] == "supplemental"
    assert ids["775"]["historical_required_min"] == 4
    assert "12001" not in str(selection)


def test_ambiguous_requirements_do_not_pick_one_or_call_api():
    overview = sample_overview()
    overview["incident_evidence_overview"][1][
        "crew_requirement_evidence"
    ][0]["availability_requirement_id"] = "4444"
    requirement, selection = choose_historical_task_requirement(
        overview, 194, 7674, task_index()
    )
    assert requirement is None
    assert selection["probe_status"] == "ambiguous_historical_requirement_ids"
    assert selection["api_get_attempted"] is False


@pytest.mark.parametrize("station,task", [
    (194, 7001), (200, 7674), (194, 9999),
])
def test_no_cross_station_or_wrong_task_lookup(station, task):
    requirement, selection = choose_historical_task_requirement(
        sample_overview(), station, task, task_index()
    )
    assert requirement is None
    assert selection["api_get_attempted"] is False


def test_live_current_task_coverage_sanitizes_all_member_details():
    _, selection = chosen()
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    summary = summarize_task_requirement_schedule(
        selection, sample_schedule(), now
    )
    assert summary["probe_status"] == (
        "readable_current_task_aggregate_skill_statuses"
    )
    assert summary["current_interval_matches"] == 1
    assert summary["current_api_requirement_id_matches"] is True
    assert summary["current_api_task_ids_match"] is True
    assert summary["api_reported_task_ids"] == ["7674"]
    assert summary["current_api_requested_task_included"] is True
    assert summary["current_api_task_mapping_status"] == "single_requested_task"
    assert summary["current_configuration_matches_historical_skill_ids"] is True
    assert summary["current_aggregate_service_level"] == "in_service"
    assert summary["current_aggregate_warning_level"] == "on_required"
    assert len(summary["current_aggregate_skills"]) == 4
    ms = next(
        skill for skill in summary["current_aggregate_skills"]
        if skill["skill_id"] == "775"
    )
    assert ms["reported_minimum"] == 4
    assert ms["reported_assigned_count"] == 4
    assert summary["current_aggregate_skill_coverage_checked"] is True
    assert summary["current_personnel_eligibility_verified"] is False
    assert summary["actual_vehicle_crew_verified"] is False
    assert summary["predicted_lineup"] is None
    for private in (
        "TOP SECRET OUTSIDE INTERVAL", "CONFIDENTIAL MEMBER",
        "PRIVATE BEVELVOERDER", "user_name", "available_memberships",
        "10001", "10002",
    ):
        assert private not in str(summary)


def test_current_id_and_task_mismatch_never_return_coverage_counts():
    _, selection = chosen()
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    invalid_id = sample_schedule()
    invalid_id["availability_requirement"]["id"] = 9991
    result = summarize_task_requirement_schedule(selection, invalid_id, now)
    assert result["probe_status"] == "api_requirement_id_mismatch"
    assert result["current_aggregate_skills"] == []
    assert result["current_api_requirement_id_matches"] is False

    wrong_task = sample_schedule()
    wrong_task["availability_requirement"]["task_ids"] = [7689]
    result = summarize_task_requirement_schedule(selection, wrong_task, now)
    assert result["probe_status"] == "api_task_ids_do_not_match"
    assert result["current_aggregate_skills"] == []
    assert result["current_api_task_ids_match"] is False
    assert result["current_api_requested_task_included"] is False
    assert result["api_reported_task_ids"] == ["7689"]
    assert result["current_api_task_mapping_status"] == "different_tasks"


def test_missing_task_metadata_is_explicitly_unverified_not_silently_joined():
    _, selection = chosen()
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    response = sample_schedule()
    del response["availability_requirement"]["task_ids"]
    result = summarize_task_requirement_schedule(selection, response, now)
    assert result["current_api_requirement_id_matches"] is True
    assert result["current_api_task_ids_match"] is None
    assert result["current_api_requested_task_included"] is None
    assert result["current_api_task_mapping_status"] == "task_ids_missing"
    assert result["probe_status"] == "api_task_ids_missing"
    assert result["current_aggregate_skill_coverage_checked"] is False
    assert result["current_aggregate_skills"] == []
    assert result["current_personnel_eligibility_verified"] is False


def test_ambiguous_current_intervals_do_not_merge_skill_statuses():
    _, selection = chosen()
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    response = sample_schedule()
    response["intervals"].append(dict(response["intervals"][0]))
    result = summarize_task_requirement_schedule(selection, response, now)
    assert result["probe_status"] == "ambiguous_overlapping_current_intervals"
    assert result["current_interval_matches"] == 2
    assert result["current_aggregate_skills"] == []
    assert result["current_aggregate_skill_coverage_checked"] is False


def test_missing_or_malformed_api_response_is_not_downtime_claim():
    _, selection = chosen()
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    for response, status in [
        (None, "api_schedule_unavailable_or_permission_denied"),
        ({}, "api_requirement_metadata_missing"),
        ({"availability_requirement": {"id": 3690}},
         "invalid_or_unbounded_intervals"),
    ]:
        result = summarize_task_requirement_schedule(selection, response, now)
        assert result["probe_status"] == status
        assert result["current_aggregate_skill_coverage_checked"] is False
        assert result["current_aggregate_skills"] == []


def test_missing_live_skill_status_is_unknown_not_sufficient():
    _, selection = chosen()
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    response = sample_schedule()
    del response["intervals"][0]["skill_statuses"]
    result = summarize_task_requirement_schedule(selection, response, now)
    assert result["probe_status"] == "aggregate_skill_statuses_missing_or_ambiguous"
    assert result["current_aggregate_skill_coverage_checked"] is False
    assert result["current_aggregate_service_level"] == "in_service"
    assert result["predicted_lineup"] is None

def test_shared_current_requirement_reports_all_numeric_tasks_without_crew():
    _, selection = chosen()
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    response = sample_schedule()
    response["availability_requirement"]["task_ids"] = [7689, 7674]
    response["availability_requirement"]["user_name"] = "PRIVATE"
    response["intervals"][0]["available_memberships"] = [
        {"user_name": "DO NOT EXPOSE"}]
    result = summarize_task_requirement_schedule(selection, response, now)
    assert result["probe_status"] == "api_requirement_shared_across_tasks"
    assert result["current_api_requirement_id_matches"] is True
    assert result["current_api_task_ids_match"] is False
    assert result["current_api_requested_task_included"] is True
    assert result["api_reported_task_ids"] == ["7674", "7689"]
    assert result["api_reported_task_ids_count"] == 2
    assert result["current_api_task_mapping_status"] == "shared_across_tasks"
    assert result["current_aggregate_skills"] == []
    assert result["current_requirement_configuration"] == []
    assert result["current_aggregate_service_level"] is None
    assert result["current_aggregate_warning_level"] is None
    assert result["current_aggregate_skill_coverage_checked"] is False
    assert "PRIVATE" not in str(result)
    assert "DO NOT EXPOSE" not in str(result)
    assert "user_name" not in str(result)


@pytest.mark.parametrize("task_ids", [
    "7674",
    {"task": 7674},
    [None],
    [False],
    [7674, 7674],
    [0],
    [-2],
    ["not an id"],
    ["9" * 40],
    list(range(1, 60)),
])
def test_malformed_current_task_ids_never_return_aggregate(task_ids):
    _, selection = chosen()
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    response = sample_schedule()
    response["availability_requirement"]["task_ids"] = task_ids
    result = summarize_task_requirement_schedule(selection, response, now)
    assert result["probe_status"] == "api_task_ids_invalid"
    assert result["current_api_task_mapping_status"] == "task_ids_invalid"
    assert result["api_reported_task_ids"] == []
    assert result["current_api_requested_task_included"] is None
    assert result["current_aggregate_skill_coverage_checked"] is False
    assert result["predicted_lineup"] is None


def test_empty_current_task_ids_fail_closed_even_with_known_requirement():
    _, selection = chosen()
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    response = sample_schedule()
    response["availability_requirement"]["task_ids"] = []
    result = summarize_task_requirement_schedule(selection, response, now)
    assert result["probe_status"] == "api_task_ids_missing"
    assert result["current_api_task_mapping_status"] == "task_ids_missing"
    assert result["current_aggregate_skill_coverage_checked"] is False
