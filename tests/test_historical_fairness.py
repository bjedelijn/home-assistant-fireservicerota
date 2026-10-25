"""Anonymous regression tests for opt-in historical fairness evidence."""
import asyncio

import pytest

from custom_components.fireservicerota.historical_fairness import (
    _reported_status_code,
    build_compact_history_evidence,
    build_historical_role_preview,
    build_one_time_incident_staffing_evidence,
    enrich_compact_history_task_names,
    enrich_compact_history_crew_coverage,
    select_retained_history_ids,
    summarize_incident_for_history,
)
from custom_components.fireservicerota import historical_fairness_store as storage_module


def analysis(
    incident_id="12001",
    *,
    roles=None,
    responses=None,
    station_ids=(100,),
    complete=True,
    count=3,
):
    if roles is None:
        roles = [
            {"name": "Person One", "role": "Bevelvoerder"},
            {"name": "Person Two", "role": "Chauffeur"},
        ]
    if responses is None:
        responses = [
            {"user_id": 1, "membership_id": 11, "user_name": "Person One"},
            {"user_id": 2, "membership_id": 22, "user_name": "Person Two"},
        ]
    groups = [
        {
            "station": {"station_id": sid} if sid is not None else None,
            "response_count": len(responses),
            "response_people": responses,
        }
        for sid in station_ids
    ]
    return {
        "incident_id": incident_id,
        "audit_complete": complete,
        "fairness_suggestion_count": count,
        "latest_fairness_suggestion": {
            "at": "2026-10-12T13:00:00+02:00",
            "members": roles,
        },
        "staffing_by_group": {"groups": groups},
    }


def test_latest_proposal_per_incident_links_to_unique_memberships():
    result = summarize_incident_for_history(analysis(), 100)
    assert result["status"] == "imported"
    record = result["record"]
    assert record["proposal_snapshots_seen"] == 3
    assert len(record["people"]) == 2
    assert record["people"][0]["membership_id"] == "11"
    assert record["people"][1]["role"] == "Chauffeur"
    assert record["source"] == "complete_audit_latest_fairness_proposal"


def test_incomplete_history_is_not_used_even_when_proposals_present():
    result = summarize_incident_for_history(analysis(complete=False), 100)
    assert result["status"] == "skipped"
    assert result["reason"] == "audit_incomplete"


def test_no_proposal_is_not_interpreted_as_staffing_disabled():
    result = summarize_incident_for_history(analysis(count=0), 100)
    assert result["reason"] == "no_fairness_proposals"


@pytest.mark.parametrize("station_ids,reason", [
    ((100, 200), "multi_station_or_other_station"),
    ((None,), "station_unresolved"),
    ((200,), "multi_station_or_other_station"),
])
def test_cross_station_and_ambiguous_proposals_are_not_attributed(
    station_ids, reason
):
    result = summarize_incident_for_history(
        analysis(station_ids=station_ids), 100
    )
    assert result["reason"] == reason


def test_duplicate_display_names_are_excluded_from_profiles():
    records = [
        {"user_id": 1, "membership_id": 11, "user_name": "Person One"},
        {"user_id": 3, "membership_id": 13, "user_name": "Person One"},
        {"user_id": 2, "membership_id": 22, "user_name": "Person Two"},
    ]
    result = summarize_incident_for_history(analysis(responses=records), 100)
    assert result["status"] == "imported"
    assert [p["name"] for p in result["record"]["people"]] == ["Person Two"]
    assert result["record"]["ambiguous_name_seats"] == 1


def test_unmatched_audit_names_do_not_create_unverified_members():
    result = summarize_incident_for_history(
        analysis(roles=[{"name": "Unknown", "role": "Bevelvoerder"}]), 100
    )
    assert result["reason"] == "no_unambiguous_membership_matches"


def test_historical_profiles_count_incidents_not_every_audit_snapshot():
    first = summarize_incident_for_history(analysis("12001", count=15), 100)["record"]
    second = summarize_incident_for_history(analysis("12002", count=9), 100)["record"]
    second["latest_proposal_at"] = "2026-10-13T13:00:00+02:00"
    output = build_historical_role_preview([first, first, second], 100)
    assert output["distinct_incidents_with_complete_matched_audit"] == 2
    roles = {r["role"]: r["candidates"] for r in output["historical_roles"]}
    assert roles["Bevelvoerder"][0]["incidents_in_latest_proposal"] == 2
    assert roles["Chauffeur"][0]["incidents_in_latest_proposal"] == 2
    assert output["prediction_status"] == "history_only_not_a_lineup_prediction"
    assert output["current_duty_or_availability_checked"] is False
    assert output["fairness_percentage_calculated"] is False


def test_same_person_can_be_observed_in_different_roles_not_double_counted():
    first = summarize_incident_for_history(analysis("12001"), 100)["record"]
    second = summarize_incident_for_history(
        analysis(
            "12002",
            roles=[
                {"name": "Person One", "role": "Chauffeur"},
                {"name": "Person Two", "role": "Manschap"},
            ],
        ),
        100,
    )["record"]
    result = build_historical_role_preview([first, second], 100)
    by_role = {r["role"]: r["candidates"] for r in result["historical_roles"]}
    assert by_role["Chauffeur"][0]["membership_id"] in {"11", "22"}
    assert {c["membership_id"] for c in by_role["Chauffeur"]} == {"11", "22"}
    assert len(by_role["Manschap"]) == 1


class FakeStorage:
    def __init__(self):
        self.saved = None

    async def async_load(self):
        return self.saved

    async def async_save(self, data):
        self.saved = data


def test_private_storage_deduplicates_and_can_be_cleared(monkeypatch):
    fake = FakeStorage()
    monkeypatch.setattr(storage_module, "Store", lambda *args: fake)

    async def exercise():
        cache = storage_module.HistoricalFairnessStorage(object(), "test")
        incident = summarize_incident_for_history(analysis(), 100)["record"]
        one = await cache.async_upsert(incident)
        two = await cache.async_upsert(incident)
        assert one["replaced"] == 0
        assert two["replaced"] == 1
        assert len(await cache.async_list(100)) == 1
        assert fake.saved["records"][0].get("audit_turnout_status_changes") is None
        assert await cache.async_delete_station(100) == 1
        assert await cache.async_list(100) == []
        assert fake.saved["records"] == []

    asyncio.run(exercise())


def test_retained_history_batch_offset_uses_next_ids():
    history = [{"id": idx} for idx in range(1, 26)]
    first = select_retained_history_ids(history, offset=0, limit=10)
    second = select_retained_history_ids(history, offset=10, limit=10)
    last = select_retained_history_ids(history, offset=20, limit=10)
    assert first["ids"] == [str(idx) for idx in range(1, 11)]
    assert first["next_offset"] == 10
    assert second["ids"] == [str(idx) for idx in range(11, 21)]
    assert second["next_offset"] == 20
    assert last["ids"] == [str(idx) for idx in range(21, 26)]
    assert last["available_retained_incidents"] == 25
    assert last["next_offset"] is None


def test_retained_history_batch_can_be_empty_and_filters_bad_ids():
    rows = [{"id": "1"}, {"id": None}, {"id": "invalid"}, {"id": "2"}]
    result = select_retained_history_ids(rows, offset=2, limit=1)
    assert result["ids"] == []
    assert result["available_retained_incidents"] == 2
    assert result["next_offset"] is None


@pytest.mark.parametrize("offset,limit", [(-1, 10), (25, 10), (0, 0), (0, 11)])
def test_retained_history_batch_rejects_out_of_bounds(offset, limit):
    with pytest.raises(ValueError):
        select_retained_history_ids([{"id": 1}], offset=offset, limit=limit)


def test_single_and_multiple_task_contexts_do_not_assign_vehicle_seats():
    first = analysis()
    first["staffing_by_group"]["incident_task_ids"] = [88]
    result_one = summarize_incident_for_history(first, 100)["record"]
    assert result_one["task_context"] == "single_incident_task"
    assert result_one["incident_task_ids"] == ["88"]
    assert all("task_id" not in person for person in result_one["people"])

    multiple = analysis(incident_id="12002")
    multiple["staffing_by_group"]["incident_task_ids"] = [88, 99]
    result_many = summarize_incident_for_history(multiple, 100)["record"]
    assert result_many["task_context"] == "multiple_incident_tasks"
    assert result_many["incident_task_ids"] == ["88", "99"]
    assert all("task_id" not in person for person in result_many["people"])

    summary = build_historical_role_preview([result_one, result_many], 100)
    assert summary["task_context_incident_counts"] == {
        "single_incident_task": 1,
        "multiple_incident_tasks": 1,
        "no_task_ids": 0,
        "legacy_not_imported": 0,
    }


def test_comparison_uses_only_reported_api_states_and_explicit_memberships():
    sample = analysis()
    group = sample["staffing_by_group"]["groups"][0]
    group["response_people"][0]["reported_status"] = "dispatched"
    group["response_people"][1]["reported_status"] = "shown_up"
    group["skill_assignments"] = [
        {"membership_id": 11, "skill_ids": [42]},
        {"user_id": 2, "skill_ids": [43]},  # No membership: do not infer.
    ]
    record = summarize_incident_for_history(sample, 100)["record"]
    by_role = {item["role"]: item for item in record["role_api_observations"]}
    assert by_role["Bevelvoerder"]["reported_status_counts"] == {
        "dispatched": 1
    }
    assert by_role["Chauffeur"]["reported_status_counts"] == {"shown_up": 1}
    assert by_role["Bevelvoerder"]["api_skill_assignment_member_appearances"] == 1
    assert by_role["Chauffeur"]["api_skill_assignment_member_appearances"] == 0

    preview = build_historical_role_preview([record], 100)
    assert preview["proposal_to_api_record_comparison"][
        "incidents_with_comparison_data"
    ] == 1
    rows = {
        item["role"]: item
        for item in preview["proposal_to_api_record_comparison"]["role_observations"]
    }
    assert rows["Bevelvoerder"]["reported_status_counts"]["dispatched"] == 1
    assert preview["actual_vehicle_crew_verified"] is False
    assert preview["prediction_status"] == "history_only_not_a_lineup_prediction"


def test_conflicting_api_reported_status_is_not_forced_to_one_result():
    sample = analysis()
    group = sample["staffing_by_group"]["groups"][0]
    group["response_people"].append(
        {
            "user_id": 1, "membership_id": 11,
            "user_name": "Person One", "reported_status": "no_show",
        }
    )
    group["response_people"][0]["reported_status"] = "dispatched"
    record = summarize_incident_for_history(sample, 100)["record"]
    captain = {
        item["role"]: item for item in record["role_api_observations"]
    }["Bevelvoerder"]
    assert captain["ambiguous_reported_status_count"] == 1
    assert captain["reported_status_counts"] == {}


def test_legacy_cached_records_are_kept_without_false_api_comparison():
    record = summarize_incident_for_history(analysis(), 100)["record"]
    del record["task_context"]
    del record["incident_task_ids"]
    del record["role_api_observations"]
    summary = build_historical_role_preview([record], 100)
    assert summary["distinct_incidents_with_complete_matched_audit"] == 1
    assert summary["task_context_incident_counts"]["legacy_not_imported"] == 1
    assert summary["proposal_to_api_record_comparison"][
        "incidents_with_comparison_data"
    ] == 0


def test_per_member_history_preserves_exact_api_status_and_no_guessed_assignment():
    sample = analysis()
    group = sample["staffing_by_group"]["groups"][0]
    group["response_people"][0]["reported_status"] = "dispatched"
    group["response_people"][1]["reported_status"] = "no_show"
    group["skill_assignments"] = [
        {"membership_id": 11, "skill_ids": [42]},
        {"user_id": 2, "skill_ids": [43]},  # Missing membership is not inferred.
    ]
    record = summarize_incident_for_history(sample, 100)["record"]
    per_membership = {item["membership_id"]: item for item in record["people"]}
    assert per_membership["11"]["api_reported_status"] == "dispatched"
    assert per_membership["11"]["api_skill_assignment_recorded"] is True
    assert per_membership["22"]["api_reported_status"] == "no_show"
    assert per_membership["22"]["api_skill_assignment_recorded"] is False
    assert record["api_record_checked_at"].endswith("+00:00")

    roles = {
        item["role"]: item["candidates"][0]
        for item in build_historical_role_preview([record], 100)["historical_roles"]
    }
    assert roles["Bevelvoerder"]["incidents_with_person_api_comparison"] == 1
    assert roles["Bevelvoerder"]["api_reported_status_counts"] == {"dispatched": 1}
    assert roles["Bevelvoerder"]["api_skill_assignment_recorded_incidents"] == 1
    assert roles["Chauffeur"]["api_reported_status_counts"] == {"no_show": 1}
    assert roles["Chauffeur"]["api_skill_assignment_recorded_incidents"] == 0


def test_per_member_ambiguous_status_not_inferred_as_dispatched():
    sample = analysis()
    people = sample["staffing_by_group"]["groups"][0]["response_people"]
    people[0]["reported_status"] = "dispatched"
    people.append({
        "membership_id": 11, "user_id": 1, "user_name": "Person One",
        "reported_status": "no_show",
    })
    record = summarize_incident_for_history(sample, 100)["record"]
    proposed = {item["membership_id"]: item for item in record["people"]}
    assert proposed["11"]["api_reported_status"] == "ambiguous"
    evidence = {row["role"]: row for row in record["role_api_observations"]}
    assert evidence["Bevelvoerder"]["ambiguous_reported_status_count"] == 1
    assert evidence["Bevelvoerder"]["reported_status_counts"] == {}


def test_legacy_profile_retains_candidate_without_fabricated_person_outcome():
    legacy = summarize_incident_for_history(analysis(), 100)["record"]
    legacy["people"] = [
        {key: value for key, value in person.items()
         if key not in ("api_reported_status", "api_skill_assignment_recorded")}
        for person in legacy["people"]
    ]
    recent = summarize_incident_for_history(analysis("12002"), 100)["record"]
    preview = build_historical_role_preview([legacy, recent], 100)
    by_role = {item["role"]: item["candidates"][0]
               for item in preview["historical_roles"]}
    commander = by_role["Bevelvoerder"]
    assert commander["incidents_in_latest_proposal"] == 2
    assert commander["incidents_with_person_api_comparison"] == 1
    assert commander["api_reported_status_counts"] == {"missing": 1}
    assert commander["api_skill_assignment_recorded_incidents"] == 0
    assert preview["person_api_comparison_status"] == (
        "retrospective_api_records_not_verified_turnout"
    )


@pytest.mark.parametrize("raw,expected", [
    ("dispatched", "dispatched"),
    (" shown_up ", "shown_up"),
    ("NOT_DISPATCHED", "unmapped:not_dispatched"),
    ("not-dispatched", "unmapped:not-dispatched"),
    ("standby", "unmapped:standby"),
    ("unknown", "unknown"),
    (" UNKNOWN ", "unknown"),
    (None, "missing"),
    ("", "missing"),
    ("  ", "missing"),
    ([], "other"),
    ("not dispatched", "other"),
    ("<sensitive data>", "other"),
    ("X" * 100, "other"),
])
def test_unrecognized_api_status_enum_is_bounded_and_not_misinterpreted(
    raw, expected
):
    assert _reported_status_code(raw) == expected


def test_unrecognized_enum_is_preserved_per_member_and_role():
    sample = analysis()
    group = sample["staffing_by_group"]["groups"][0]
    group["response_people"][0]["reported_status"] = "not_dispatched"
    group["response_people"][1]["reported_status"] = "dispatched"
    record = summarize_incident_for_history(sample, 100)["record"]
    by_role = {person["role"]: person for person in record["people"]}
    assert by_role["Bevelvoerder"]["api_reported_status"] == (
        "unmapped:not_dispatched"
    )
    assert by_role["Chauffeur"]["api_reported_status"] == "dispatched"
    comparison = build_historical_role_preview([record], 100)
    roles = {
        row["role"]: row
        for row in comparison["proposal_to_api_record_comparison"][
            "role_observations"
        ]
    }
    assert roles["Bevelvoerder"]["reported_status_counts"] == {
        "unmapped:not_dispatched": 1
    }
    assert roles["Chauffeur"]["reported_status_counts"] == {
        "dispatched": 1
    }
    assert comparison["actual_vehicle_crew_verified"] is False


def test_explicit_unknown_is_distinct_from_missing_api_status():
    sample = analysis()
    group = sample["staffing_by_group"]["groups"][0]
    group["response_people"][0]["reported_status"] = "unknown"
    # Person Two has no reported_status key at all.
    record = summarize_incident_for_history(sample, 100)["record"]
    by_role = {p["role"]: p for p in record["people"]}
    assert by_role["Bevelvoerder"]["api_reported_status"] == "unknown"
    assert by_role["Chauffeur"]["api_reported_status"] == "missing"
    rows = build_historical_role_preview([record], 100)[
        "proposal_to_api_record_comparison"
    ]["role_observations"]
    counts = {row["role"]: row["reported_status_counts"] for row in rows}
    assert counts["Bevelvoerder"] == {"unknown": 1}
    assert counts["Chauffeur"] == {"missing": 1}


def test_previous_unknown_label_is_read_compatibly_without_storage_mutation():
    incident = summarize_incident_for_history(analysis(), 100)["record"]
    incident["people"][0]["api_reported_status"] = "unmapped:unknown"
    commander = next(
        row for row in incident["role_api_observations"]
        if row["role"] == "Bevelvoerder"
    )
    commander["reported_status_counts"] = {"unmapped:unknown": 1}
    preview = build_historical_role_preview([incident], 100)
    by_role = {r["role"]: r for r in preview["historical_roles"]}
    assert by_role["Bevelvoerder"]["candidates"][0]["api_reported_status_counts"] == {
        "unknown": 1
    }
    evidence = preview["proposal_to_api_record_comparison"]["role_observations"]
    assert next(r for r in evidence if r["role"] == "Bevelvoerder")[
        "reported_status_counts"
    ] == {"unknown": 1}
    assert incident["people"][0]["api_reported_status"] == "unmapped:unknown"


def test_incident_evidence_overview_identifies_two_drivers_without_names():
    sample = analysis(roles=[
        {"name": "Person One", "role": "Chauffeur"},
        {"name": "Person Two", "role": "Chauffeur"},
    ])
    sample["staffing_by_group"]["incident_task_ids"] = [70]
    people = sample["staffing_by_group"]["groups"][0]["response_people"]
    people[0]["reported_status"] = "dispatched"
    people[1]["reported_status"] = "unknown"
    summary = build_historical_role_preview(
        [summarize_incident_for_history(sample, 100)["record"]], 100
    )
    row = summary["incident_evidence_overview"][0]
    assert row["incident_id"] == "12001"
    assert row["role_seats"] == [{"role": "Chauffeur", "proposed_seats": 2}]
    assert row["incident_task_ids"] == ["70"]
    assert row["total_proposed_role_seats"] == 2
    assert row["distinct_proposed_memberships"] == 2
    assert row["members_in_multiple_proposed_roles"] == 0
    assert row["api_reported_status_counts"] == {
        "dispatched": 1, "unknown": 1
    }
    assert "Person One" not in str(row)
    assert "Person Two" not in str(row)
    assert "membership_id" not in str(row)
    assert "user_id" not in str(row)


def test_incident_evidence_overview_catches_cross_role_same_member():
    sample = analysis(roles=[
        {"name": "Person One", "role": "Chauffeur"},
        {"name": "Person One", "role": "Manschap"},
    ])
    record = summarize_incident_for_history(sample, 100)["record"]
    summary = build_historical_role_preview([record], 100)
    row = summary["incident_evidence_overview"][0]
    assert row["total_proposed_role_seats"] == 2
    assert row["distinct_proposed_memberships"] == 1
    assert row["members_in_multiple_proposed_roles"] == 1


def test_incident_evidence_legacy_reports_missing_comparison_not_unknown():
    record = summarize_incident_for_history(analysis(), 100)["record"]
    record.pop("task_context")
    record.pop("incident_task_ids")
    for person in record["people"]:
        person.pop("api_reported_status")
        person.pop("api_skill_assignment_recorded")
    row = build_historical_role_preview(
        [record], 100
    )["incident_evidence_overview"][0]
    assert row["task_context"] == "legacy_not_imported"
    assert row["api_comparison_role_seats"] == 0
    assert row["api_reported_status_counts"] == {}
    assert row["total_proposed_role_seats"] == 2


def test_compact_preview_omits_candidate_identifiers_and_full_name_lists():
    record = summarize_incident_for_history(analysis(), 100)["record"]
    full = build_historical_role_preview([record], 100)
    compact = build_compact_history_evidence(full)
    assert compact["distinct_incidents_with_complete_matched_audit"] == 1
    assert len(compact["incident_evidence_overview"]) == 1
    assert "historical_roles" not in compact
    assert compact["prediction_status"] == "history_only_not_a_lineup_prediction"
    assert compact["actual_vehicle_crew_verified"] is False
    assert "Person One" not in str(compact)
    assert "Person Two" not in str(compact)
    assert "membership_id" not in str(compact)
    assert "user_id" not in str(compact)


def test_compact_task_names_resolve_from_current_station_without_guessing():
    sample = analysis()
    sample["staffing_by_group"]["incident_task_ids"] = [7001, 7689, 9999]
    record = summarize_incident_for_history(sample, 100)["record"]
    compact = build_compact_history_evidence(
        build_historical_role_preview([record], 100)
    )
    index = {
        7001: [
            {"id": 7001, "name": "WTS", "station_id": 100},
            {"id": 7001, "name": "Other station task", "station_id": 200},
        ],
        "7689": [{"id": 7689, "name": "Red vehicle", "station_id": "100"}],
        9999: [{"id": 9999, "name": "Do not expose", "station_id": 200}],
    }
    enriched = enrich_compact_history_task_names(compact, index, 100)
    tasks = enriched["incident_evidence_overview"][0]["resolved_tasks"]
    assert tasks == [
        {"id": "7001", "name": "WTS", "resolution": "current_station_task_index"},
        {"id": "7689", "name": "Red vehicle", "resolution": "current_station_task_index"},
        {
            "id": "9999",
            "resolution": "name_not_available_in_current_station_index",
        },
    ]
    assert enriched["task_name_source"] == (
        "current_station_task_index_not_historical_task_snapshot"
    )
    assert "resolved_tasks" not in compact["incident_evidence_overview"][0]
    assert "historical_roles" not in enriched
    assert "Other station task" not in str(enriched)
    assert "Do not expose" not in str(enriched)
    assert "membership_id" not in str(enriched)
    assert "user_id" not in str(enriched)


def test_conflicting_station_task_names_remain_unresolved():
    sample = analysis()
    sample["staffing_by_group"]["incident_task_ids"] = [7001]
    record = summarize_incident_for_history(sample, 100)["record"]
    compact = build_compact_history_evidence(
        build_historical_role_preview([record], 100)
    )
    index = {
        7001: [
            {"id": 7001, "name": "WTS", "station_id": 100},
            {"id": 7001, "name": "Other name", "station_id": 100},
        ]
    }
    tasks = enrich_compact_history_task_names(
        compact, index, 100
    )["incident_evidence_overview"][0]["resolved_tasks"]
    assert tasks == [{"id": "7001", "resolution": "conflicting_current_task_names"}]

def test_retained_wts_shortfall_is_skill_coverage_not_unique_crew():
    sample = analysis(roles=[
        {"name": "Person One", "role": "Chauffeur"},
        {"name": "Person Two", "role": "Chauffeur"},
    ])
    sample["staffing_by_group"]["incident_task_ids"] = [7001]
    record = summarize_incident_for_history(sample, 100)["record"]
    compact = build_compact_history_evidence(
        build_historical_role_preview([record], 100)
    )
    retained = [{
        "id": 12001,
        "crew_summary": {"individual_assignments_available": True},
        "crew_requirements": [{
            "availability_requirement_id": 9,
            "station_ids": [100], "task_ids": [7001],
            "skills": [
                {"skill_id": 7, "short_code": "Bev", "required": 1,
                 "assigned": 1, "coverage_source": "warning_statuses"},
                {"skill_id": 1168, "short_code": "Ch", "required": 2,
                 "assigned": 2, "coverage_source": "warning_statuses"},
                {"skill_id": 775, "short_code": "Ms", "required": 4,
                 "assigned": 2, "coverage_source": "warning_statuses"},
            ],
        }],
    }]
    row = enrich_compact_history_crew_coverage(
        compact, retained, 100
    )["incident_evidence_overview"][0]
    assert row["crew_coverage_status"] == "recorded_skill_requirements_found"
    req = row["crew_requirement_evidence"][0]
    assert req["sufficient"] is False
    assert [(v["short_code"], v["shortfall"]) for v in req["skills"]] == [
        ("Bev", 0), ("Ch", 0), ("Ms", 2)
    ]
    assert "required_positions" not in str(row)
    assert "membership_id" not in str(row)


def test_coverage_is_unknown_without_retained_snapshot():
    record = summarize_incident_for_history(analysis(), 100)["record"]
    compact = build_compact_history_evidence(
        build_historical_role_preview([record], 100)
    )
    row = enrich_compact_history_crew_coverage(
        compact, [], 100
    )["incident_evidence_overview"][0]
    assert row["crew_coverage_status"] == "no_retained_staffing_snapshot"
    assert row["crew_requirement_evidence"] == []


def test_available_memberships_are_not_assigned_coverage():
    sample = analysis()
    sample["staffing_by_group"]["incident_task_ids"] = [7001]
    record = summarize_incident_for_history(sample, 100)["record"]
    compact = build_compact_history_evidence(
        build_historical_role_preview([record], 100)
    )
    retained = [{"id": "12001", "crew_requirements": [{
        "station_ids": [100], "task_ids": [7001],
        "skills": [{"skill_id": 775, "required": 4, "assigned": 8,
                    "coverage_source": "warning_statuses_available_memberships"}],
    }]}]
    row = enrich_compact_history_crew_coverage(
        compact, retained, 100
    )["incident_evidence_overview"][0]
    assert row["crew_requirement_evidence"][0]["skills"][0]["assigned"] is None
    assert row["crew_requirement_evidence"][0]["skills"][0]["shortfall"] is None
    assert row["crew_requirement_evidence"][0]["sufficient"] is None


def test_other_station_or_task_requirements_are_not_joined():
    sample = analysis()
    sample["staffing_by_group"]["incident_task_ids"] = [7001]
    record = summarize_incident_for_history(sample, 100)["record"]
    compact = build_compact_history_evidence(
        build_historical_role_preview([record], 100)
    )
    retained = [{"id": 12001, "crew_requirements": [
        {"station_ids": [200], "task_ids": [7001], "skills": [
            {"skill_id": 775, "required": 4, "assigned": 2,
             "coverage_source": "warning_statuses"}]},
        {"station_ids": [100], "task_ids": [9999], "skills": [
            {"skill_id": 775, "required": 4, "assigned": 2,
             "coverage_source": "warning_statuses"}]},
    ]}]
    row = enrich_compact_history_crew_coverage(
        compact, retained, 100
    )["incident_evidence_overview"][0]
    assert row["crew_coverage_status"] == "no_unambiguous_station_task_requirements"
    assert row["crew_requirement_evidence"] == []

def test_ts_asp_is_additional_not_a_regular_crew_shortage():
    """Incident-like TS6: 6 individual assignments, optional Asp unfilled."""
    sample = analysis()
    sample["staffing_by_group"]["incident_task_ids"] = [7674]
    record = summarize_incident_for_history(sample, 100)["record"]
    compact = build_compact_history_evidence(
        build_historical_role_preview([record], 100)
    )
    compact["incident_evidence_overview"][0]["resolved_tasks"] = [
        {"id": "7674", "name": "TS"}
    ]
    history = [
        {
            "id": "12001",
            "crew_summary": {
                "individual_assignments_available": True,
                "assigned_member_count": 6,
                "responding_count": 8,
                "reserve_responding_count": 2,
            },
            "crew_requirements": [{
                "station_ids": [100], "task_ids": [7674],
                "skills": [
                    {"skill_id": 7, "short_code": "Bev", "required": 1,
                     "assigned": 3, "individual_assignment_count": 1,
                     "coverage_source": "warning_statuses"},
                    {"skill_id": 1168, "short_code": "Ch", "required": 1,
                     "assigned": 1, "individual_assignment_count": 1,
                     "coverage_source": "warning_statuses"},
                    {"skill_id": 775, "short_code": "Ms", "required": 4,
                     "assigned": 5, "individual_assignment_count": 4,
                     "coverage_source": "warning_statuses"},
                    {"skill_id": 165, "short_code": None, "required": 1,
                     "assigned": 0, "individual_assignment_count": 0,
                     "coverage_source": "incident_skill_assignments"},
                ],
            }],
        },
        {
            "id": "12000", "crew_requirements": [{
                "station_ids": [100], "task_ids": [7674],
                "skills": [{"skill_id": 165, "short_code": "Asp"}],
            }],
        },
    ]
    result = enrich_compact_history_crew_coverage(compact, history, 100)
    req = result["incident_evidence_overview"][0][
        "crew_requirement_evidence"
    ][0]
    assert req["sufficient"] is False  # Raw API: includes additional Asp.
    assert req["regular_crew_sufficient"] is True
    assert req["supplemental_positions_sufficient"] is False
    bev, ch, ms, asp = req["skills"]
    assert [s["individual_assignment_count"] for s in (bev, ch, ms, asp)] == [
        1, 1, 4, 0
    ]
    assert bev["assigned"] == 3  # Warning count stays independent.
    assert bev["individual_assignment_count"] == 1
    assert asp["short_code"].casefold() == "asp"
    assert asp["short_code_source"] == "same_station_task_retained_history"
    assert asp["position_type"] == "supplemental"
    assert asp["individual_assignment_shortfall"] == 1
    assert "membership_id" not in str(result)


def test_no_guessed_optional_role_without_same_task_skill_label():
    sample = analysis()
    sample["staffing_by_group"]["incident_task_ids"] = [7674]
    record = summarize_incident_for_history(sample, 100)["record"]
    compact = build_compact_history_evidence(
        build_historical_role_preview([record], 100)
    )
    compact["incident_evidence_overview"][0]["resolved_tasks"] = [
        {"id": "7674", "name": "TS"}
    ]
    retained = [
        {"id": "12001", "crew_summary": {
            "individual_assignments_available": True,
        }, "crew_requirements": [{
            "station_ids": [100], "task_ids": [7674],
            "skills": [{"skill_id": 165, "short_code": None,
                        "required": 1, "assigned": 0,
                        "individual_assignment_count": 0,
                        "coverage_source": "incident_skill_assignments"}],
        }]},
        # Same skill ID but other station must not establish role.
        {"id": "12000", "crew_requirements": [{
            "station_ids": [200], "task_ids": [7674],
            "skills": [{"skill_id": 165, "short_code": "Asp"}],
        }]},
    ]
    req = enrich_compact_history_crew_coverage(
        compact, retained, 100
    )["incident_evidence_overview"][0]["crew_requirement_evidence"][0]
    assert req["regular_crew_sufficient"] is False
    assert req["supplemental_positions_sufficient"] is None
    assert req["skills"][0]["position_type"] == "regular"
    assert req["skills"][0]["short_code"] is None


def test_non_ts_asp_does_not_override_required_skill():
    sample = analysis()
    sample["staffing_by_group"]["incident_task_ids"] = [7001]
    record = summarize_incident_for_history(sample, 100)["record"]
    compact = build_compact_history_evidence(
        build_historical_role_preview([record], 100)
    )
    compact["incident_evidence_overview"][0]["resolved_tasks"] = [
        {"id": "7001", "name": "WTS"}
    ]
    retained = [{"id": "12001", "crew_summary": {
        "individual_assignments_available": True,
    }, "crew_requirements": [{
        "station_ids": [100], "task_ids": [7001],
        "skills": [{"skill_id": 165, "short_code": "Asp", "required": 1,
                    "assigned": 0, "individual_assignment_count": 0,
                    "coverage_source": "incident_skill_assignments"}],
    }]}]
    req = enrich_compact_history_crew_coverage(
        compact, retained, 100
    )["incident_evidence_overview"][0]["crew_requirement_evidence"][0]
    assert req["regular_crew_sufficient"] is False
    assert req["supplemental_positions_sufficient"] is None
    assert req["skills"][0]["position_type"] == "regular"


def test_warning_counts_without_individual_records_cannot_verify_regular_crew():
    sample = analysis()
    sample["staffing_by_group"]["incident_task_ids"] = [7674]
    record = summarize_incident_for_history(sample, 100)["record"]
    compact = build_compact_history_evidence(
        build_historical_role_preview([record], 100)
    )
    compact["incident_evidence_overview"][0]["resolved_tasks"] = [
        {"id": "7674", "name": "TS"}
    ]
    retained = [{"id": "12001", "crew_requirements": [{
        "station_ids": [100], "task_ids": [7674],
        "skills": [{"skill_id": 775, "short_code": "Ms",
                    "required": 4, "assigned": 8,
                    "coverage_source": "warning_statuses"}],
    }]}]
    req = enrich_compact_history_crew_coverage(
        compact, retained, 100
    )["incident_evidence_overview"][0]["crew_requirement_evidence"][0]
    assert req["sufficient"] is True
    assert req["regular_crew_sufficient"] is None
    assert req["skills"][0]["individual_assignment_count"] is None

def test_one_time_api_staffing_restores_view_without_mutating_cached_history():
    cached = {
        "incident_id": "12001",
        "station_id": "100",
        "incident_task_ids": ["7674"],
    }
    incident = {
        "id": 12001,
        "task_ids": [7674],
        "incident_responses": [{"user_name": "SENSITIVE TEST PERSON"}],
    }
    normalized = {
        "crew_summary": {"individual_assignments_available": True},
        "crew_assignments": [{"user_name": "SENSITIVE TEST PERSON"}],
        "crew_requirements": [{
            "station_ids": [100],
            "task_ids": [7674],
            "skills": [
                {
                    "skill_id": 7, "short_code": "Bev", "required": 1,
                    "assigned": 3, "individual_assignment_count": 1,
                    "coverage_source": "warning_statuses",
                },
                {
                    "skill_id": 1168, "short_code": "Ch", "required": 1,
                    "assigned": 1, "individual_assignment_count": 1,
                    "coverage_source": "warning_statuses",
                },
                {
                    "skill_id": 775, "short_code": "Ms", "required": 4,
                    "assigned": 5, "individual_assignment_count": 4,
                    "coverage_source": "warning_statuses",
                },
                {
                    "skill_id": 165, "short_code": None, "required": 1,
                    "assigned": 0, "individual_assignment_count": 0,
                    "coverage_source": "incident_skill_assignments",
                },
            ],
        }],
    }
    retained = [{
        "id": 12000,
        "crew_requirements": [{
            "station_ids": [100], "task_ids": [7674],
            "skills": [{"skill_id": 165, "short_code": "Asp"}],
        }],
    }]
    response = build_one_time_incident_staffing_evidence(
        station_id=100,
        cached_fairness_record=cached,
        api_incident=incident,
        normalized_staffing=normalized,
        task_index={7674: [
            {"id": 7674, "name": "TS", "station_id": 100}
        ]},
        retained_history=retained,
    )
    req = response["crew_requirement_evidence"][0]
    assert response["crew_coverage_status"] == "recorded_skill_requirements_found"
    assert response["source"] == "one_time_authenticated_incident_api_get"
    assert response["fairness_cache_modified"] is False
    assert response["local_incident_history_modified"] is False
    assert response["historical_audit_refetched"] is False
    assert req["regular_crew_sufficient"] is True
    assert req["supplemental_positions_sufficient"] is False
    assert req["skills"][3]["position_type"] == "supplemental"
    assert req["skills"][3]["short_code"].lower() == "asp"
    assert "SENSITIVE TEST PERSON" not in str(response)
    assert "membership_id" not in str(response)
    assert "crew_assignments" not in str(response)
    assert retained[0]["id"] == 12000
    assert cached["incident_task_ids"] == ["7674"]


def test_one_time_api_staffing_rejects_mismatched_station():
    cached = {
        "incident_id": "12001",
        "station_id": "100",
        "incident_task_ids": ["7674"],
    }
    with pytest.raises(ValueError, match="not for this station"):
        build_one_time_incident_staffing_evidence(
            station_id=200,
            cached_fairness_record=cached,
            api_incident={"id": 12001, "task_ids": [7674]},
            normalized_staffing={"crew_requirements": []},
            task_index={},
            retained_history=[],
        )


def test_one_time_api_staffing_cannot_join_changed_task_context():
    response = build_one_time_incident_staffing_evidence(
        station_id="100",
        cached_fairness_record={
            "incident_id": "12001",
            "station_id": "100",
            "incident_task_ids": ["7674"],
        },
        api_incident={"id": 12001, "task_ids": [7001]},
        normalized_staffing={"crew_requirements": [
            {"station_ids": [100], "task_ids": [7674],
             "skills": [{"skill_id": 7, "required": 1, "assigned": 1}]},
        ]},
        task_index={},
        retained_history=[],
    )
    assert response["crew_coverage_status"] == "api_task_ids_differ_from_cached_fairness"
    assert response["crew_requirement_evidence"] == []


def test_one_time_api_staffing_handles_missing_api_data_conservatively():
    cached = {
        "incident_id": "12001",
        "station_id": "100",
        "incident_task_ids": ["7674"],
    }
    response = build_one_time_incident_staffing_evidence(
        station_id=100,
        cached_fairness_record=cached,
        api_incident={"id": 12001, "task_ids": [7674]},
        normalized_staffing=None,
        task_index={},
        retained_history=[],
    )
    assert response["crew_coverage_status"] == "api_staffing_requirements_unavailable"
    assert response["crew_requirement_evidence"] == []


def test_one_time_api_staffing_rejects_different_api_incident():
    response = build_one_time_incident_staffing_evidence(
        station_id=100,
        cached_fairness_record={
            "incident_id": "12001", "station_id": "100",
            "incident_task_ids": ["7674"],
        },
        api_incident={"id": 13002, "task_ids": [7674]},
        normalized_staffing={"crew_requirements": []},
        task_index={},
        retained_history=[],
    )
    assert response["crew_coverage_status"] == "api_incident_missing_or_id_mismatch"
    assert response["crew_requirement_evidence"] == []

