"""Privacy tests for single-candidate read-only schedule endpoint probe."""

from datetime import datetime, timezone

import pytest

from custom_components.fireservicerota.fairness_availability_probe import (
    choose_one_candidate_schedule_probe,
    summarize_one_candidate_schedule_probe,
)


def history():
    return [
        {
            "incident_id": "12001",
            "station_id": "194",
            "source": "complete_audit_latest_fairness_proposal",
            "incident_task_ids": ["7674"],
            "latest_proposal_at": "2026-10-22T13:00:00+02:00",
            "unmatched_proposal_seats": 0,
            "ambiguous_name_seats": 0,
            "people": [
                {"membership_id": "11", "name": "PRIVATE PERSON A",
                 "role": "Bevelvoerder"},
                {"membership_id": "22", "name": "PRIVATE PERSON B",
                 "role": "Chauffeur"},
            ],
        },
        {
            "incident_id": "12002",
            "station_id": "194",
            "source": "complete_audit_latest_fairness_proposal",
            "incident_task_ids": ["7689"],
            "latest_proposal_at": "2026-10-21T13:00:00+02:00",
            "people": [{"membership_id": "33", "name": "PRIVATE OTHER TASK"}],
        },
        {
            "incident_id": "12003",
            "station_id": "200",
            "source": "complete_audit_latest_fairness_proposal",
            "incident_task_ids": ["7674"],
            "people": [{"membership_id": "44", "name": "PRIVATE OTHER POST"}],
        },
        {
            "incident_id": "12004",
            "station_id": "194",
            "source": "complete_audit_latest_fairness_proposal",
            "incident_task_ids": ["7674", "7001"],
            "people": [{"membership_id": "55", "name": "PRIVATE MULTITASK"}],
        },
        {
            "incident_id": "12005",
            "station_id": "194",
            "source": "complete_audit_latest_fairness_proposal",
            "incident_task_ids": ["7674"],
            "unmatched_proposal_seats": 1,
            "people": [{"membership_id": "66", "name": "PRIVATE PARTIAL"}],
        },
    ]


def groups():
    return [
        {
            "id": 194, "type": "station", "memberships": [
                {"id": 11, "user_id": 1001, "status": "active"},
                {"id": 99, "user_id": 1099, "status": "inactive"},
            ],
        },
        {
            "id": 777, "type": "team", "parent_group_id": 194,
            "memberships": [
                {"id": 22, "user_id": 1001, "status": "active"},
                {"id": 55, "user_id": 1005, "status": "active"},
                {"id": 66, "user_id": 1006, "status": "active"},
            ],
        },
        {
            "id": 200, "type": "station", "memberships": [
                {"id": 33, "user_id": 1003, "status": "active"},
                {"id": 44, "user_id": 1004, "status": "active"},
            ],
        },
    ]


def task_index():
    return {
        7674: [{"id": 7674, "name": "TS", "station_id": 194}],
        7689: [{"id": 7689, "name": "RV", "station_id": 194}],
        7001: [{"id": 7001, "name": "WTS", "station_id": 200}],
    }


def test_one_member_selected_only_from_exact_station_task_and_current_group():
    member, meta = choose_one_candidate_schedule_probe(
        history(), groups(), task_index(), 194, 7674
    )
    assert member == 11
    assert meta["probe_status"] == "ready_for_single_read_only_GET"
    assert meta["historical_proposal_candidate_count"] == 2
    assert meta["active_related_group_membership_match_count"] == 2
    assert meta["active_related_group_distinct_user_ids"] == 3
    assert meta["candidate_identifiers_returned"] is False
    assert meta["api_get_attempted"] is False
    assert meta["current_station_crew_eligibility_verified"] is False
    assert meta["full_station_availability_verified"] is False
    assert "PRIVATE" not in str(meta)
    assert "PRIVATE PERSON" not in str(meta)
    assert "membership_id" not in meta
    assert "user_id" not in meta


def test_ineligible_context_and_missing_group_do_not_attempt_a_get():
    bad_task, meta = choose_one_candidate_schedule_probe(
        history(), groups(), task_index(), 194, 7001
    )
    assert bad_task is None
    assert meta["probe_status"] == "task_not_indexed_for_this_station"
    assert meta["api_get_attempted"] is False

    missing, meta2 = choose_one_candidate_schedule_probe(
        history(), groups()[2:], task_index(), 194, 7674
    )
    assert missing is None
    assert meta2["probe_status"] == (
        "no_history_member_match_in_active_cached_groups"
    )
    assert meta2["api_get_attempted"] is False


def test_single_candidate_api_format_has_no_private_schedule_or_status():
    selected, meta = choose_one_candidate_schedule_probe(
        history(), groups(), task_index(), 194, 7674
    )
    assert selected is not None
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    schedule = {
        "membership_id": selected,
        "private_name": "SENSITIVE SCHEDULE",
        "intervals": [
            {
                "start_time": "2026-10-25T10:00:00+00:00",
                "end_time": "2026-10-25T11:00:00+00:00",
                "available": True,
                "detailed_availability": {"exception": {
                    "comments": "PRIVATE", "skill_ids": [7]
                }},
            },
        ],
    }
    outcome = summarize_one_candidate_schedule_probe(meta, schedule, now)
    assert outcome["api_get_attempted"] is True
    assert outcome["schedule_response_structure_readable"] is True
    assert outcome["probe_status"] == "readable_schedule_current_interval"
    assert outcome["schedule_interval_count"] == 1
    assert outcome["current_interval_present"] is True
    assert outcome["current_interval_matches"] == 1
    shape = outcome["current_interval_field_presence"]
    assert shape["available_is_boolean"] is True
    assert shape["active_is_boolean"] is False
    assert shape["skill_ids_is_list"] is False
    assert shape["assigned_function_ids_is_list"] is False
    assert shape["detailed_availability_is_object"] is True
    assert shape["detail_kinds_present"] == ["exception"]
    assert shape["nested_skill_ids_is_list"] is True
    assert shape["nested_assigned_function_ids_is_list"] is False
    assert outcome["current_candidate_available"] is None
    assert outcome["full_station_availability_verified"] is False
    assert outcome["remote_schedule_data_persisted"] is False
    assert outcome["candidate_identifiers_returned"] is False
    assert "PRIVATE" not in str(outcome)
    assert "SENSITIVE" not in str(outcome)
    assert "membership_id" not in outcome
    assert "available': True" not in str(outcome)
    assert "10:00:00+00:00" not in str(outcome)


def test_unavailable_and_unexpected_schedule_are_clearly_distinct():
    _member, meta = choose_one_candidate_schedule_probe(
        history(), groups(), task_index(), 194, 7674
    )
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    missing = summarize_one_candidate_schedule_probe(meta, None, now)
    assert missing["probe_status"] == (
        "api_schedule_unavailable_or_permission_denied"
    )
    assert missing["current_interval_present"] is None
    assert missing["current_candidate_available"] is None

    malformed = summarize_one_candidate_schedule_probe(
        meta, {"intervals": "invalid"}, now
    )
    assert malformed["probe_status"] == "unexpected_schedule_response_structure"
    assert malformed["current_interval_present"] is None


def test_interval_gap_is_not_proof_of_unavailability():
    _member, meta = choose_one_candidate_schedule_probe(
        history(), groups(), task_index(), 194, 7674
    )
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    gap = summarize_one_candidate_schedule_probe(meta, {
        "intervals": [{
            "start_time": "2026-10-25T11:00:00+00:00",
            "end_time": "2026-10-25T12:00:00+00:00",
            "available": False,
        }],
    }, now)
    assert gap["probe_status"] == "readable_schedule_but_no_current_interval"
    assert gap["current_interval_present"] is False
    assert gap["current_candidate_available"] is None
    assert gap["current_interval_field_presence"] is None


@pytest.mark.parametrize("station,task", [
    ("not-a-number", 7674), (194, "TS"), (None, 7674),
    (194, None), (True, 7674), (194, False),
])
def test_invalid_identifiers_are_rejected(station, task):
    with pytest.raises(ValueError):
        choose_one_candidate_schedule_probe(
            [], [], {}, station, task
        )

def test_multiple_current_intervals_do_not_merge_private_field_shapes():
    _member, meta = choose_one_candidate_schedule_probe(
        history(), groups(), task_index(), 194, 7674
    )
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    summary = summarize_one_candidate_schedule_probe(
        meta,
        {
            "intervals": [
                {
                    "start_time": "2026-10-25T10:00:00+00:00",
                    "end_time": "2026-10-25T11:00:00+00:00",
                    "available": True,
                    "skill_ids": [7, 775],
                    "private_name": "CONFIDENTIAL",
                },
                {
                    "start_time": "2026-10-25T10:20:00+00:00",
                    "end_time": "2026-10-25T10:40:00+00:00",
                    "available": False,
                    "assigned_function_ids": [8],
                },
            ]
        },
        now,
    )
    assert summary["current_interval_present"] is True
    assert summary["current_interval_matches"] == 2
    assert summary["current_interval_field_presence"] is None
    assert summary["current_candidate_available"] is None
    assert "CONFIDENTIAL" not in str(summary)
    assert "775" not in str(summary)
    assert "available': False" not in str(summary)


def test_valid_interval_reports_only_presence_not_skill_values():
    _member, meta = choose_one_candidate_schedule_probe(
        history(), groups(), task_index(), 194, 7674
    )
    now = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)
    summary = summarize_one_candidate_schedule_probe(meta, {
        "intervals": [{
            "start_time": "2026-10-25T10:00:00+00:00",
            "end_time": "2026-10-25T11:00:00+00:00",
            "available": False,
            "active": True,
            "skill_ids": [99991],
            "assigned_function_ids": [22223],
            "detailed_availability": {
                "standby_duty": {
                    "skill_ids": [77778],
                    "assigned_function_ids": [66667],
                    "sensitive": "SECRET",
                },
                "unknown_provider_key": {
                    "member_name": "DO NOT DISCLOSE",
                },
            },
        }],
    }, now)
    shape = summary["current_interval_field_presence"]
    assert shape == {
        "available_is_boolean": True,
        "active_is_boolean": True,
        "skill_ids_is_list": True,
        "assigned_function_ids_is_list": True,
        "detailed_availability_is_object": True,
        "detail_kinds_present": ["standby_duty"],
        "nested_skill_ids_is_list": True,
        "nested_assigned_function_ids_is_list": True,
    }
    for forbidden in (
        "99991", "22223", "77778", "66667", "SECRET",
        "DO NOT DISCLOSE", "unknown_provider_key",
    ):
        assert forbidden not in str(summary)
    assert summary["current_candidate_available"] is None
    assert summary["current_candidate_duty_type"] is None
