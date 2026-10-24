"""Anonymous regression tests for opt-in historical fairness evidence."""
import asyncio

import pytest

from custom_components.fireservicerota.historical_fairness import (
    build_historical_role_preview,
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
