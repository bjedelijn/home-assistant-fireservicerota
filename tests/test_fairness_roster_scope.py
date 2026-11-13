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
             "memberships": {"person": "SECRET"}},
            {"id": 194, "type": "station", "memberships": [
                None, {"id": 1, "user_id": 9, "status": "active", "name": "SECRET"},
            ]},
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
