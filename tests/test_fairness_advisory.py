"""Anonymous tests for the strictly read-only task-scoped advisory preview."""

import pytest

from custom_components.fireservicerota.fairness_advisory import (
    build_task_fairness_advisory,
    summarize_cached_station_roster_shape,
)
from custom_components.fireservicerota.historical_fairness import (
    summarize_incident_for_history,
)


def historical_record(
    incident_id, task_ids, roles, *, at="2026-10-21T12:00:00+02:00",
    station=100, partial=False,
):
    names = {
        "Alpha": (1, 11),
        "Bravo": (2, 22),
        "Charlie": (3, 33),
    }
    responses = [
        {"user_id": user, "membership_id": membership,
         "user_name": name, "reported_status": "dispatched"}
        for name, (user, membership) in names.items()
    ]
    evidence = {
        "incident_id": str(incident_id),
        "audit_complete": True,
        "fairness_suggestion_count": 4,
        "latest_fairness_suggestion": {
            "at": at,
            "members": [
                {"name": name, "role": role} for name, role in roles
            ] + (
                [{"name": "UNMATCHED", "role": "Manschap"}]
                if partial else []
            ),
        },
        "staffing_by_group": {
            "incident_task_ids": task_ids,
            "groups": [{
                "station": {"station_id": station},
                "response_count": len(responses),
                "response_people": responses,
            }],
        },
    }
    return summarize_incident_for_history(evidence, station)["record"]


def groups_snapshot():
    return [
        {
            "id": 100, "type": "station",
            "memberships": [
                {"id": 11, "status": "active", "user_name": "SENSITIVE ALPHA",
                 "skill_ids": [7]},
                {"id": 22, "status": "inactive", "user_name": "SENSITIVE BRAVO"},
            ],
        },
        {
            "id": 919, "type": "team", "parent_group_id": 100,
            "memberships": [{"id": 33, "status": "active", "user_name": "SECRET"}],
        },
        {
            "id": 200, "type": "station",
            "memberships": [{"id": 999, "status": "active", "user_name": "OTHER"}],
        },
    ]


def task_index():
    return {
        7674: [{"id": 7674, "name": "TS", "station_id": 100}],
        7689: [{"id": 7689, "name": "RV", "station_id": 100}],
        7001: [{"id": 7001, "name": "WTS", "station_id": 200}],
    }


def samples():
    first = historical_record(
        12001, [7674],
        [("Alpha", "Bevelvoerder"), ("Bravo", "Chauffeur")],
        at="2026-10-22T12:00:00+02:00",
    )
    second = historical_record(
        12002, [7674],
        [("Alpha", "Bevelvoerder"), ("Charlie", "Aspirant Manschap")],
        at="2026-10-21T12:00:00+02:00",
    )
    third = historical_record(
        12003, [7689], [("Alpha", "Bediener Redvoertuig")],
        at="2026-10-20T12:00:00+02:00",
    )
    partial = historical_record(
        12004, [7674], [("Bravo", "Manschap")],
        at="2026-10-19T12:00:00+02:00", partial=True,
    )
    multiple = historical_record(
        12005, [7674, 7001], [("Charlie", "Chauffeur")],
        at="2026-10-18T12:00:00+02:00",
    )
    other_station = historical_record(
        12006, [7674], [("Alpha", "Bevelvoerder")],
        station=200,
    )
    return [first, second, third, partial, multiple, other_station]


def test_task_scoped_counts_do_not_mix_task_or_station_and_omit_people():
    result = build_task_fairness_advisory(
        samples(), "100", 7674,
        task_index=task_index(), groups=groups_snapshot(),
    )
    sample = result["historical_sample"]
    assert sample["distinct_cached_incidents_for_station"] == 5
    assert sample["single_task_incidents_matching"] == 3
    assert sample["usable_complete_proposal_incidents"] == 2
    assert sample["excluded_partial_or_ambiguous_proposal_incidents"] == 1
    assert sample["excluded_multi_task_incidents_containing_task"] == 1
    assert result["task_name"] == "TS"
    assert result["task_name_resolution"] == "current_station_task_index"
    profiles = {item["role"]: item for item in result["historical_roles"]}
    assert set(profiles) == {
        "Bevelvoerder", "Chauffeur", "Aspirant Manschap",
    }
    assert profiles["Bevelvoerder"]["proposal_appearances"] == 2
    assert profiles["Bevelvoerder"]["distinct_historical_candidates"] == 1
    assert profiles["Aspirant Manschap"]["role_position_interpretation"] == (
        "supplemental_ts_asp"
    )
    assert "historical_candidates" not in str(result)
    assert "membership_id" not in str(result)
    assert "SENSITIVE" not in str(result)
    assert "Alpha" not in str(result)
    assert "Bravo" not in str(result)
    assert "Charlie" not in str(result)
    assert "UNMATCHED" not in str(result)
    assert result["predicted_lineup"] is None
    assert result["selection_probability_calculated"] is False
    assert result["fairness_percentage_calculated"] is False
    assert result["current_duty_or_availability_checked"] is False
    assert result["current_task_skill_eligibility_checked"] is False


def test_persons_are_opt_in_and_sorted_alphabetically_not_by_prediction():
    result = build_task_fairness_advisory(
        samples(), 100, "7674",
        task_index=task_index(), groups=groups_snapshot(),
        include_people=True,
    )
    by_role = {item["role"]: item for item in result["historical_roles"]}
    bev = by_role["Bevelvoerder"]["historical_candidates"]
    assert bev[0]["name"] == "Alpha"
    assert bev[0]["membership_id"] == "11"
    assert bev[0]["historical_proposal_incidents"] == 2
    assert bev[0]["retrospective_api_reported_status_counts"] == {
        "dispatched": 2
    }
    assert bev[0]["current_duty_status"] == "not_verified"
    assert bev[0]["current_task_eligibility"] == "not_verified"
    assert by_role["Bevelvoerder"]["candidate_display_order"] == (
        "alphabetical_not_prediction_order"
    )
    assert result["prediction_status"] == (
        "historical_task_evidence_only_not_ready_for_lineup"
    )


def test_cached_group_metadata_has_no_member_identity_or_live_claims():
    result = summarize_cached_station_roster_shape(groups_snapshot(), 100)
    assert result["station_group_found"] is True
    assert result["station_or_related_groups_observed"] == 2
    assert result["membership_rows_observed"] == 3
    assert result["distinct_membership_ids_observed"] == 3
    assert result["membership_row_status_counts"] == {
        "active": 2, "inactive": 1
    }
    assert "skill_ids" in result["possible_roster_field_names"]
    assert result["snapshot_freshness_verified"] is False
    assert result["current_availability_verified"] is False
    assert "SENSITIVE" not in str(result)
    assert "OTHER" not in str(result)
    assert "SECRET" not in str(result)
    assert "membership_id" not in str(result) or (
        "membership_ids_observed" in str(result)
    )


def test_historical_required_skills_are_not_current_vehicle_requirements():
    rows = samples()
    crew = {"incident_evidence_overview": [
        {"incident_id": "12001", "crew_requirement_evidence": [{
            "regular_crew_sufficient": True,
            "skills": [
                {"skill_id": "7", "short_code": "Bev", "required": 1,
                 "position_type": "regular"},
                {"skill_id": "165", "short_code": "Asp", "required": 1,
                 "position_type": "supplemental"},
            ],
        }]},
        {"incident_id": "12002", "crew_requirement_evidence": [{
            "regular_crew_sufficient": False,
            "skills": [
                {"skill_id": "7", "short_code": "Bev", "required": 2,
                 "position_type": "regular"},
            ],
        }]},
        {"incident_id": "12003", "crew_requirement_evidence": [{
            "regular_crew_sufficient": True,
            "skills": [{"skill_id": "10818", "required": 1,
                        "position_type": "regular"}],
        }]},
    ]}
    result = build_task_fairness_advisory(
        rows, 100, 7674,
        task_index=task_index(), groups=groups_snapshot(),
        crew_overview=crew,
    )
    snap = result["historical_crew_requirement_evidence"]
    assert snap["incidents_with_coverage_evidence"] == 2
    assert snap["regular_coverage_sufficient"] == 1
    assert snap["regular_coverage_insufficient"] == 1
    skills = {x["skill_id"]: x for x in snap["observed_required_skills"]}
    assert set(skills) == {"7", "165"}
    assert skills["7"]["observed_required_min"] == 1
    assert skills["7"]["observed_required_max"] == 2
    assert skills["165"]["position_type"] == "supplemental"
    assert result["current_task_skill_eligibility_checked"] is False


def test_no_task_specific_history_never_guesses_a_crew():
    result = build_task_fairness_advisory(
        samples(), 100, 7001,
        task_index=task_index(), groups=groups_snapshot(),
    )
    assert result["historical_sample"][
        "usable_complete_proposal_incidents"
    ] == 0
    assert result["historical_roles"] == []
    assert result["task_name"] is None  # Only the other station has WTS.
    assert result["predicted_lineup"] is None
    assert result["prediction_status"] == (
        "no_complete_historical_task_evidence"
    )


def test_group_and_task_name_conflicts_do_not_justify_eligibility():
    conflicts = {7674: [
        {"id": 7674, "name": "TS", "station_id": 100},
        {"id": 7674, "name": "Other name", "station_id": 100},
    ]}
    result = build_task_fairness_advisory(
        samples(), 100, 7674,
        task_index=conflicts, groups=groups_snapshot(),
    )
    assert result["task_name"] is None
    assert result["task_name_resolution"] == (
        "conflicting_current_station_task_names"
    )
    asp = next(
        item for item in result["historical_roles"]
        if item["role"] == "Aspirant Manschap"
    )
    assert asp["role_position_interpretation"] != "supplemental_ts_asp"
    assert result["predicted_lineup"] is None


@pytest.mark.parametrize("station,task", [
    (None, 7674), ("bad", 7674), (100, None), (100, "TS"),
    (True, 7674),
])
def test_invalid_task_or_station_refused(station, task):
    with pytest.raises(ValueError):
        build_task_fairness_advisory(
            [], station, task, task_index={}, groups=[],
        )


def test_anonymous_empty_group_discovery_is_still_unknown_not_off_duty():
    result = summarize_cached_station_roster_shape([], 100)
    assert result["membership_rows_observed"] == 0
    assert result["station_group_found"] is False
    assert result["current_duty_verified"] is False
    assert result["current_availability_verified"] is False
