"""Anonymized regression tests for cross-group staffing inspections."""

from custom_components.fireservicerota.staffing_insights import (
    build_staffing_by_group,
)


def test_multiple_stations_and_membership_specific_assignments():
    incident = {
        "task_ids": [30, 40],
        "incident_responses": [
            {
                "user_id": 1,
                "user_name": "Person One",
                "membership_id": 101,
                "group_id": 10,
                "status": "acknowledged",
                "reported_status": "dispatched",
            },
            {
                "user_id": 1,  # Same person has a different station membership.
                "user_name": "Person One",
                "membership_id": 202,
                "group_id": 20,
                "status": "acknowledged",
                "reported_status": "shown_up",
            },
            {
                "user_id": 2,
                "user_name": "Person Two",
                "membership_id": 203,
                "group_id": 20,
                "status": "acknowledged",
                "reported_status": "dispatched",
            },
        ],
        "incident_skill_assignments": [
            {"user_id": 1, "membership_id": 101, "skill_ids": [91]},
            {"user_id": 2, "membership_id": 203, "skill_ids": [92]},
        ],
        "warning_statuses": [
            {
                "skill_statuses": [
                    {"skill_id": 91, "short_code": "LEAD"},
                    {"skill_id": 92, "short_code": "DRIVE"},
                ]
            }
        ],
    }
    groups = [
        {"id": 100, "name": "Station Alpha", "type": "station"},
        {"id": 200, "name": "Station Beta", "type": "station"},
        {"id": 10, "name": "Crew Alpha", "type": "team", "parent_group_id": 100},
        {"id": 20, "name": "Crew Beta", "type": "team", "parent_group_id": 200},
    ]

    summary = build_staffing_by_group(incident, groups)
    by_id = {item["group_id"]: item for item in summary["groups"]}
    assert summary["incident_task_ids"] == [30, 40]
    assert summary["unmatched_assignment_count"] == 0
    assert by_id[10]["station"]["station_id"] == 100
    assert by_id[20]["station"]["station_id"] == 200
    assert by_id[10]["response_count"] == 1
    assert by_id[20]["response_count"] == 2
    assert by_id[20]["reported_status_counts"] == {"shown_up": 1, "dispatched": 1}
    assert by_id[10]["skill_assignments"][0]["skill_short_codes"] == ["LEAD"]
    assert by_id[20]["skill_assignments"][0]["user_name"] == "Person Two"
    assert by_id[20]["skill_assignments"][0]["skill_short_codes"] == ["DRIVE"]


def test_shared_user_without_membership_is_not_assigned_to_random_station():
    incident = {
        "incident_responses": [
            {"user_id": 1, "membership_id": 101, "group_id": 10},
            {"user_id": 1, "membership_id": 202, "group_id": 20},
        ],
        "incident_skill_assignments": [
            {"user_id": 1, "skill_ids": [91]},
        ],
    }
    result = build_staffing_by_group(incident)
    by_id = {item["group_id"]: item for item in result["groups"]}
    assert result["unmatched_assignment_count"] == 1
    assert len(by_id[None]["skill_assignments"]) == 1
    assert by_id[10]["skill_assignments"] == []
    assert by_id[20]["skill_assignments"] == []


def test_station_is_not_inferred_from_ambiguous_ancestor_groups():
    incident = {
        "incident_responses": [{"user_id": 1, "membership_id": 101, "group_id": 10}],
        "incident_skill_assignments": [],
    }
    groups = [
        {"id": 100, "name": "Station Alpha", "type": "station"},
        {"id": 200, "name": "Station Beta", "type": "station"},
        {"id": 10, "type": "team", "ancestor_ids": [100, 200]},
    ]
    result = build_staffing_by_group(incident, groups)
    assert result["groups"][0]["station"] is None


def test_empty_or_unavailable_incident_does_not_raise():
    result = build_staffing_by_group(None)
    assert result == {
        "available": False,
        "incident_task_ids": [],
        "groups": [],
        "unmatched_assignment_count": 0,
    }
    empty = build_staffing_by_group({})
    assert empty["available"] is True
    assert empty["groups"] == []
