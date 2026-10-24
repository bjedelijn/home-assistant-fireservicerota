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


def test_single_station_fairness_proposals_count_as_observed_for_incident():
    incident = {
        "incident_responses": [
            {"user_id": 1, "membership_id": 101, "group_id": 100}
        ],
        "incident_skill_assignments": [
            {"user_id": 1, "membership_id": 101, "skill_ids": [91]}
        ],
    }
    groups = [{"id": 100, "name": "Station Alpha", "type": "station"}]
    result = build_staffing_by_group(
        incident,
        groups,
        suggestions=[{"at": "2026-10-10T12:00:00+02:00", "members": []}],
    )
    mode = result["groups"][0]["automatic_staffing"]
    assert mode["status"] == "enabled"
    assert mode["source"] == "fairness_proposal_observed_for_incident"
    assert mode["scope"] == "this_incident_only"
    assert mode["fairness_proposal_evidence"] == "observed_single_station_incident"
    assert mode["skill_assignment_count"] == 1


def test_no_fairness_does_not_prove_disabled_and_explicit_confirmation_does():
    incident = {
        "incident_responses": [
            {"user_id": 1, "membership_id": 101, "group_id": 3853,
             "reported_status": "shown_up"}
        ],
        "incident_skill_assignments": [],
    }
    groups = [{"id": 3853, "name": "Station Alpha", "type": "station"}]
    unknown = build_staffing_by_group(incident, groups, suggestions=[])
    mode = unknown["groups"][0]["automatic_staffing"]
    assert mode["status"] == "unknown"
    assert mode["source"] == "insufficient_evidence"
    assert mode["fairness_proposal_evidence"] == "not_observed_in_retrieved_audit"

    confirmed = build_staffing_by_group(
        incident,
        groups,
        suggestions=[],
        station_staffing_modes={3853: "disabled"},
    )
    confirmed_mode = confirmed["groups"][0]["automatic_staffing"]
    assert confirmed_mode["status"] == "disabled"
    assert confirmed_mode["source"] == "user_confirmed_for_incident"
    assert confirmed["unused_confirmed_station_ids"] == []


def test_confirmed_enabled_is_not_converted_to_off_on_empty_audit():
    incident = {
        "incident_responses": [{"user_id": 1, "group_id": 100}],
    }
    groups = [{"id": 100, "name": "Station Alpha", "type": "station"}]
    result = build_staffing_by_group(
        incident, groups, suggestions=[],
        station_staffing_modes={"100": "enabled"},
    )
    assert result["groups"][0]["automatic_staffing"]["status"] == "enabled"
    assert result["groups"][0]["automatic_staffing"]["warning"] is None


def test_fairness_proposals_do_not_get_attributed_to_two_stations():
    incident = {
        "incident_responses": [
            {"user_id": 1, "group_id": 100},
            {"user_id": 2, "group_id": 200},
        ]
    }
    groups = [
        {"id": 100, "name": "Station Alpha", "type": "station"},
        {"id": 200, "name": "Station Beta", "type": "station"},
    ]
    result = build_staffing_by_group(
        incident, groups,
        suggestions=[{"at": "2026-10-10T12:00:00+02:00", "members": []}],
        station_staffing_modes={"200": "disabled"},
    )
    by_id = {item["group_id"]: item for item in result["groups"]}
    assert by_id[100]["automatic_staffing"]["status"] == "unknown"
    assert by_id[200]["automatic_staffing"]["status"] == "disabled"
    for group in result["groups"]:
        assert group["automatic_staffing"]["fairness_proposal_evidence"] == (
            "observed_but_station_unattributed"
        )


def test_conflicting_confirmation_is_reported_without_changing_it():
    incident = {
        "incident_responses": [{"user_id": 1, "group_id": 100}],
    }
    groups = [{"id": 100, "name": "Station Alpha", "type": "station"}]
    result = build_staffing_by_group(
        incident, groups,
        suggestions=[{"at": "2026-10-10T12:00:00+02:00", "members": []}],
        station_staffing_modes={"100": "disabled"},
    )
    mode = result["groups"][0]["automatic_staffing"]
    assert mode["status"] == "disabled"
    assert "verify vehicle/task scope" in mode["warning"]


def test_unused_station_confirmation_is_reported_instead_of_inferred():
    result = build_staffing_by_group(
        {"incident_responses": [{"user_id": 1, "group_id": 100}]},
        [{"id": 100, "name": "Station Alpha", "type": "station"}],
        suggestions=[],
        station_staffing_modes={"200": "disabled"},
    )
    assert result["unused_confirmed_station_ids"] == ["200"]
    assert result["groups"][0]["automatic_staffing"]["status"] == "unknown"
