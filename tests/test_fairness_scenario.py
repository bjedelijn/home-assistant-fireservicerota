"""Synthetic tests only: no personal roster information or API calls."""

from custom_components.fireservicerota.fairness_scenario import evaluate_verified_seat_scenario


def snapshot(members):
    return {
        "station_id": 194, "observed_at": "2026-11-12T12:00:00+01:00",
        "complete": True, "current": True, "availability_verified": True,
        "eligibility_verified": True, "members": members,
    }


def requirements(slots):
    return {
        "station_id": 194, "task_id": 7674, "verified": True,
        "current": True, "slots": slots,
        "coverage_model": "explicit_distinct_seat_slots",
        "slot_model_verified": True,
    }


def person(mid, skills, available=True):
    return {"membership_id": mid, "skill_ids": skills, "available": available}


def calculate(members, slots, **kwargs):
    return evaluate_verified_seat_scenario(
        station_id=194, task_id=7674,
        current_snapshot=snapshot(members),
        task_requirements=requirements(slots), **kwargs,
    )


def test_distinct_members_with_overlapping_qualifications():
    result = calculate(
        [person(1, [7, 1168]), person(2, [7]), person(3, [1168]),
         person(4, [775]), person(5, [775])],
        [{"skill_id": 7, "count": 1},
         {"skill_id": 1168, "count": 1},
         {"skill_id": 775, "count": 2}],
        include_membership_ids=True,
    )
    assert result["staffing_feasible"] is True
    assert len({x["membership_id"] for x in result["illustrative_assignment"]}) == 4
    assert result["predicted_lineup"] is None
    assert result["is_operational_prediction"] is False


def test_two_chauffeurs_are_separate_required_slots():
    result = calculate(
        [person(1, [7]), person(2, [1168]), person(3, [1168])],
        [{"skill_id": 7, "count": 1}, {"skill_id": 1168, "count": 2}],
        include_membership_ids=True,
    )
    assert result["staffing_feasible"]
    assert [x["skill_id"] for x in result["illustrative_assignment"]].count("1168") == 2


def test_multiskilled_person_cannot_fill_two_seats():
    result = calculate(
        [person(1, [7, 1168])],
        [{"skill_id": 7, "count": 1}, {"skill_id": 1168, "count": 1}],
    )
    assert result["staffing_feasible"] is False
    assert result["illustrative_assignment"] is None


def test_unavailable_member_is_excluded():
    result = calculate(
        [person(1, [7], False)],
        [{"skill_id": 7, "count": 1}],
    )
    assert result["staffing_feasible"] is False


def test_default_output_has_no_member_identifiers():
    result = calculate(
        [person(12345, [7])], [{"skill_id": 7, "count": 1}],
    )
    assert result["staffing_feasible"] is True
    assert result["illustrative_assignment"] is None
    assert "12345" not in str(result)


def test_missing_current_flags_fail_closed():
    s = snapshot([person(1, [7])])
    s["availability_verified"] = False
    result = evaluate_verified_seat_scenario(
        station_id=194, task_id=7674,
        current_snapshot=s, task_requirements=requirements([{"skill_id": 7, "count": 1}]),
    )
    assert result["scenario_status"] == "current_availability_or_eligibility_not_verified"
    assert result["staffing_feasible"] is None


def test_cross_station_and_task_scope_rejected():
    req = requirements([{"skill_id": 7, "count": 1}])
    req["task_id"] = 7001
    result = evaluate_verified_seat_scenario(
        station_id=194, task_id=7674,
        current_snapshot=snapshot([person(1, [7])]), task_requirements=req,
    )
    assert result["scenario_status"] == "station_or_task_scope_mismatch"


def test_duplicate_memberships_refused():
    result = calculate(
        [person(1, [7]), person(1, [1168])],
        [{"skill_id": 7, "count": 1}],
    )
    assert result["scenario_status"] == "invalid_or_duplicate_membership"


def test_aspirant_not_automatically_substituted_for_manschap():
    result = calculate(
        [person(1, [165])], [{"skill_id": 775, "count": 1}],
    )
    assert result["staffing_feasible"] is False


def test_invalid_counts_and_bool_ids_refused():
    result = calculate([person(1, [7])], [{"skill_id": 7, "count": True}])
    assert result["scenario_status"] == "invalid_task_slots"
    result = calculate([person(True, [7])], [{"skill_id": 7, "count": 1}])
    assert result["scenario_status"] == "invalid_or_duplicate_membership"


def test_raw_api_skill_requirements_are_not_distinct_seats():
    req = requirements([{"skill_id": 7, "count": 1}, {"skill_id": 1168, "count": 2}])
    req.pop("coverage_model")
    req.pop("slot_model_verified")
    result = evaluate_verified_seat_scenario(
        station_id=194, task_id=7674,
        current_snapshot=snapshot([person(1, [7, 1168]), person(2, [1168])]),
        task_requirements=req,
    )
    assert result["scenario_status"] == "distinct_seat_model_not_verified"
    assert result["staffing_feasible"] is None
    assert result["predicted_lineup"] is None


def test_claimed_slot_model_without_verified_seat_distinction_is_refused():
    req = requirements([{"skill_id": 7, "count": 1}])
    req["coverage_model"] = "aggregated_overlapping_skill_requirements"
    result = evaluate_verified_seat_scenario(
        station_id=194, task_id=7674,
        current_snapshot=snapshot([person(1, [7])]),
        task_requirements=req,
    )
    assert result["scenario_status"] == "distinct_seat_model_not_verified"


def test_explicit_slot_model_with_unverified_flag_is_refused():
    req = requirements([{"skill_id": 7, "count": 1}])
    req["slot_model_verified"] = False
    result = evaluate_verified_seat_scenario(
        station_id=194, task_id=7674,
        current_snapshot=snapshot([person(1, [7])]),
        task_requirements=req,
    )
    assert result["scenario_status"] == "distinct_seat_model_not_verified"
