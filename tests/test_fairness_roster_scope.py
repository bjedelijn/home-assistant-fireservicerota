"""Aggregate anonymous scope tests; never include roster identities."""

from custom_components.fireservicerota.fairness_roster_scope import (
    assess_candidate_roster_source,
)


def test_own_duty_is_not_station_duty():
    result = assess_candidate_roster_source(
        194,
        groups=[
            {"id": 194, "type": "station", "memberships": [
                {"id": 11, "user_id": 1001, "status": "active", "name": "PRIVATE ONE"},
                {"id": 22, "user_id": 1002, "status": "active", "name": "PRIVATE TWO"},
            ]},
            {"id": 200, "type": "station", "memberships": [
                {"id": 99, "user_id": 9999, "status": "active", "name": "FOREIGN"},
            ]},
        ],
        own_membership_index={11: {"name": "PRIVATE ONE"}},
        own_membership_duty={11: {"available": True}},
    )
    assert result["cached_active_related_membership_count"] == 2
    assert result["own_memberships_with_cached_duty_at_station"] == 1
    assert result["current_station_full_roster_verified"] is False
    assert result["can_build_operational_prediction"] is False
    assert result["predicted_lineup"] is None
    assert "PRIVATE" not in str(result)
    assert "1001" not in str(result)


def test_even_all_cached_memberships_seen_do_not_prove_full_station():
    result = assess_candidate_roster_source(
        194,
        groups=[{"id": 194, "type": "station", "memberships": [
            {"id": 11, "user_id": 1001, "status": "active"},
        ]}],
        own_membership_index={11: {}}, own_membership_duty={11: {}},
    )
    assert result["own_memberships_with_cached_duty_at_station"] == 1
    assert result["current_station_full_roster_verified"] is False


def test_related_team_and_duplicate_group_are_not_double_counted():
    result = assess_candidate_roster_source(
        194, groups=[
            {"id": 194, "type": "station", "memberships": [
                {"id": 11, "user_id": 1001, "status": "active"},
            ]},
            {"id": 777, "type": "team", "parent_group_id": 194,
             "memberships": [
                {"id": 11, "user_id": 1001, "status": "active"},
                {"id": 22, "user_id": 1002, "status": "active"},
             ]},
        ],
        own_membership_index={11: {}}, own_membership_duty={11: {}},
    )
    assert result["cached_active_related_membership_count"] == 2
    assert result["cached_membership_identity_link_issues"] == 0


def test_missing_user_link_and_conflicting_user_link_report_only_counts():
    result = assess_candidate_roster_source(
        194, groups=[
            {"id": 194, "type": "station", "memberships": [
                {"id": 11, "user_id": 1001, "status": "active"},
                {"id": 22, "status": "active"},
            ]},
            {"id": 777, "type": "team", "parent_group_id": 194,
             "memberships": [{"id": 11, "user_id": 9999, "status": "active"}]},
        ],
        own_membership_index={}, own_membership_duty={},
    )
    assert result["cached_membership_identity_link_issues"] == 2
    assert "9999" not in str(result)


def test_no_groups_never_suggests_no_station_firefighters():
    result = assess_candidate_roster_source(
        194, groups=None, own_membership_index={}, own_membership_duty={},
    )
    assert result["station_discovered"] is False
    assert result["diagnostic_status"] == "groups_not_available"
    assert result["cached_active_related_membership_count"] is None
    assert result["current_station_full_roster_verified"] is False


def test_invalid_station_id_rejected():
    import pytest

    with pytest.raises(ValueError):
        assess_candidate_roster_source(
            True, groups=[], own_membership_index={}, own_membership_duty={},
        )


def test_unexpected_cached_group_shapes_do_not_crash_or_leak_raw_content():
    result = assess_candidate_roster_source(
        194,
        groups=[
            {"id": 194, "type": "station", "ancestor_ids": "PRIVATE",
             "memberships": [
                None, {"id": 1, "user_id": 9, "status": "active", "name": "SECRET"},
            ]},
            {"id": 700, "type": "team", "parent_group_id": 194,
             "memberships": {"person": "SECRET"}},
        ],
        own_membership_index="SECRET",
        own_membership_duty=None,
    )
    assert result["invalid_active_membership_rows"] == 2
    assert result["cached_active_related_membership_count"] == 1
    assert result["current_station_full_roster_verified"] is False
    assert "SECRET" not in str(result)
    assert "PRIVATE" not in str(result)


def test_no_new_api_calls_possible_in_pure_scope_inspector():
    # Fixed booleans cannot turn a cached snapshot into a live roster.
    result = assess_candidate_roster_source(
        194,
        groups=[{"id": 194, "type": "station", "memberships": []}],
        own_membership_index={}, own_membership_duty={},
    )
    assert result["can_build_operational_prediction"] is False
    assert result["predicted_lineup"] is None
    assert result["current_station_all_member_availability_verified"] is False


def test_too_many_groups_fail_closed_without_partial_counts():
    result = assess_candidate_roster_source(
        194, groups=[{"id": 194, "type": "station", "memberships": []}] * 251,
        own_membership_index={}, own_membership_duty={},
    )
    assert result["diagnostic_status"] == "groups_limit_exceeded"
    assert result["cached_active_related_membership_count"] is None
    assert result["can_build_operational_prediction"] is False


def test_too_many_memberships_in_one_group_are_not_partially_counted():
    result = assess_candidate_roster_source(
        194, groups=[{"id": 194, "type": "station",
                      "memberships": [{"id": x, "status": "active"}
                                      for x in range(1, 502)]}],
        own_membership_index={}, own_membership_duty={},
    )
    assert result["diagnostic_status"] == "group_membership_limit_exceeded"
    assert result["cached_active_related_membership_count"] is None


def test_large_own_duty_index_fails_closed():
    result = assess_candidate_roster_source(
        194, groups=[], own_membership_index={},
        own_membership_duty={x: {} for x in range(501)},
    )
    assert result["diagnostic_status"] == "own_membership_limit_exceeded"
    assert result["own_memberships_with_cached_duty_at_station"] is None


def test_invalid_groups_structure_is_not_mistaken_for_empty_station():
    result = assess_candidate_roster_source(
        194, groups={"memberships": [{"name": "PRIVATE"}]},
        own_membership_index={}, own_membership_duty={},
    )
    assert result["diagnostic_status"] == "groups_structure_invalid"
    assert result["cached_active_related_membership_count"] is None
    assert "PRIVATE" not in str(result)


def test_two_memberships_one_person_are_not_two_people():
    result = assess_candidate_roster_source(
        194,
        groups=[{"id": 194, "type": "station", "memberships": [
            {"id": 11, "user_id": 1001, "status": "active", "name": "SECRET"},
            {"id": 22, "user_id": 1001, "status": "active"},
            {"id": 33, "user_id": 1002, "status": "active"},
        ]}],
        own_membership_index={}, own_membership_duty={},
    )
    assert result["cached_active_related_membership_count"] == 3
    assert result["cached_distinct_user_count_if_fully_linked"] == 2
    assert result["cached_multi_membership_user_count_if_fully_linked"] == 1
    assert result["current_station_full_roster_verified"] is False
    assert "1001" not in str(result)
    assert "SECRET" not in str(result)


def test_incomplete_identity_links_do_not_guess_unique_person_count():
    result = assess_candidate_roster_source(
        194, groups=[{"id": 194, "type": "station", "memberships": [
            {"id": 11, "user_id": 1001, "status": "active"},
            {"id": 22, "status": "active"},
        ]}], own_membership_index={}, own_membership_duty={},
    )
    assert result["cached_active_related_membership_count"] == 2
    assert result["cached_distinct_user_count_if_fully_linked"] is None
    assert result["cached_multi_membership_user_count_if_fully_linked"] is None


def test_repeated_group_membership_is_one_person_without_double_counting():
    member = {"id": 11, "user_id": 1001, "status": "active"}
    result = assess_candidate_roster_source(
        194, groups=[
            {"id": 194, "type": "station", "memberships": [member]},
            {"id": 777, "type": "team", "parent_group_id": 194,
             "memberships": [member]},
        ],
        own_membership_index={}, own_membership_duty={},
    )
    assert result["cached_active_related_membership_count"] == 1
    assert result["cached_distinct_user_count_if_fully_linked"] == 1
    assert result["cached_multi_membership_user_count_if_fully_linked"] == 0


def test_station_direct_and_related_team_memberships_are_separate():
    result = assess_candidate_roster_source(
        194, groups=[
            {"id": 194, "type": "station", "memberships": [
                {"id": 11, "user_id": 101, "status": "active"},
                {"id": 22, "user_id": 102, "status": "active"},
            ]},
            {"id": 700, "type": "team", "parent_group_id": 194,
             "memberships": [
                {"id": 11, "user_id": 101, "status": "active"},
                {"id": 33, "user_id": 103, "status": "active"},
             ]},
        ], own_membership_index={11: {}, 33: {}},
        own_membership_duty={11: {}, 33: {}},
    )
    assert result["cached_active_related_membership_count"] == 3
    assert result["cached_active_direct_station_membership_count"] == 2
    assert result["cached_active_related_only_membership_count"] == 1
    assert result["own_memberships_in_direct_station_group"] == 1
    assert result["own_memberships_with_cached_duty_at_station"] == 2
    assert result["current_station_full_roster_verified"] is False


def test_only_related_team_without_station_group_has_unknown_direct_count():
    result = assess_candidate_roster_source(
        194, groups=[{"id": 700, "type": "team", "parent_group_id": 194,
                      "memberships": [
                          {"id": 33, "user_id": 103, "status": "active"}
                      ]}],
        own_membership_index={33: {}}, own_membership_duty={33: {}},
    )
    assert result["station_discovered"] is False
    assert result["cached_active_direct_station_membership_count"] is None
    assert result["cached_active_related_only_membership_count"] is None
    assert result["own_memberships_in_direct_station_group"] is None
    assert result["cached_active_related_membership_count"] == 1


def test_foreign_station_not_counted_as_direct():
    result = assess_candidate_roster_source(
        194, groups=[
            {"id": 194, "type": "station", "memberships": []},
            {"id": 3853, "type": "station", "memberships": [
                {"id": 88, "user_id": 888, "status": "active"}
            ]},
        ], own_membership_index={88: {}}, own_membership_duty={88: {}},
    )
    assert result["cached_active_direct_station_membership_count"] == 0
    assert result["cached_active_related_only_membership_count"] == 0
    assert result["own_memberships_in_direct_station_group"] == 0
    assert result["current_station_full_roster_verified"] is False


def test_duplicate_station_group_records_cannot_be_combined():
    result = assess_candidate_roster_source(
        194,
        groups=[
            {"id": 194, "type": "station", "memberships": [
                {"id": 11, "user_id": 1001, "status": "active"},
            ]},
            {"id": "194", "type": "station", "memberships": [
                {"id": 22, "user_id": 1002, "status": "active"},
            ]},
        ],
        own_membership_index={}, own_membership_duty={},
    )
    assert result["diagnostic_status"] == "ambiguous_duplicate_station_group"
    assert result["cached_active_direct_station_membership_count"] is None
    assert result["cached_distinct_user_count_if_fully_linked"] is None
    assert result["can_build_operational_prediction"] is False


def test_requested_station_id_reused_as_team_fails_closed():
    result = assess_candidate_roster_source(
        194,
        groups=[{"id": 194, "type": "team", "memberships": [
            {"id": 11, "user_id": 1001, "status": "active"},
        ]}],
        own_membership_index={}, own_membership_duty={},
    )
    assert result["diagnostic_status"] == "station_group_type_mismatch"
    assert result["cached_active_related_membership_count"] is None


def test_exact_duplicate_station_group_still_rejected():
    station = {"id": 194, "type": "station", "memberships": []}
    result = assess_candidate_roster_source(
        194, groups=[station, station],
        own_membership_index={}, own_membership_duty={},
    )
    assert result["diagnostic_status"] == "ambiguous_duplicate_station_group"
    assert result["station_discovered"] is False


def test_conflicting_active_inactive_status_for_same_membership_fails_closed():
    result = assess_candidate_roster_source(
        194, groups=[
            {"id": 194, "type": "station", "memberships": [
                {"id": 11, "user_id": 1001, "status": "active"},
            ]},
            {"id": 700, "type": "team", "parent_group_id": 194,
             "memberships": [
                {"id": 11, "user_id": 1001, "status": "inactive"},
            ]},
        ], own_membership_index={}, own_membership_duty={},
    )
    assert result["diagnostic_status"] == "conflicting_membership_status"
    assert result["cached_active_related_membership_count"] is None
    assert result["can_build_operational_prediction"] is False


def test_missing_or_unknown_member_status_is_not_treated_as_inactive():
    for member in (
        {"id": 11, "user_id": 1001},
        {"id": 11, "user_id": 1001, "status": "unknown"},
    ):
        result = assess_candidate_roster_source(
            194, groups=[{"id": 194, "type": "station",
                          "memberships": [member]}],
            own_membership_index={}, own_membership_duty={},
        )
        assert result["diagnostic_status"] == "unrecognized_membership_status"
        assert result["cached_active_direct_station_membership_count"] is None


def test_agreeing_active_status_across_station_and_team_is_deduplicated():
    member = {"id": 11, "user_id": 1001, "status": "active"}
    result = assess_candidate_roster_source(
        194, groups=[
            {"id": 194, "type": "station", "memberships": [member]},
            {"id": 700, "type": "team", "parent_group_id": 194,
             "memberships": [member]},
        ], own_membership_index={}, own_membership_duty={},
    )
    assert result["diagnostic_status"] == "cached_partial_scope_only"
    assert result["cached_active_related_membership_count"] == 1
    assert result["cached_active_direct_station_membership_count"] == 1
