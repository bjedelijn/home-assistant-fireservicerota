"""Evidence-only station task P2000 association preview tests."""

from custom_components.fireservicerota.station_task_p2000_history import (
    preview_station_task_p2000_history,
)


def index():
    return {
        7678: [{"id": 7678, "name": "TS-BT", "station_id": 194}],
        7674: [{"id": 7674, "name": "TS", "station_id": 194}],
        7684: [{"id": 7684, "name": "TW-G", "station_id": 194}],
        9999: [{"id": 9999, "name": "OTHER-STATION", "station_id": 500}],
    }


def incident(ident, tasks, body):
    return {
        "id": ident,
        "task_ids": tasks,
        "body": body,
        "incident_responses": [{"person": "PRIVATE NAME", "email": "secret"}],
        "address": {"formatted_address": "PRIVATE ADDRESS"},
        "credentials": "PRIVATE TOKEN",
    }


def known_hardenberg():
    return [
        incident(3012389, [7674, 7678, 7684],
                 "042330 042340 042241 042040 052441 059088 059001"),
        incident(2992516, [7678, 7684],
                 "059004 059091 042340 055341 042241"),
        incident(2969366, [7674, 7678], "042330 042340"),
        incident(2864999, [7678], "059004 059091 055341 042340 059002"),
        incident(2805609, [7678], "042340"),
        incident(200001, [7674], "042330"),
        incident(200002, [7674], "042330"),
        incident(200003, [7674], "042330"),
        incident(200004, [7674], "042330"),
        incident(200005, [7684], "042360"),
    ]


def preview(rows=None, task_index=None, station=194, **kw):
    rows = known_hardenberg() if rows is None else rows
    task_index = index() if task_index is None else task_index
    return preview_station_task_p2000_history(
        station, task_index, rows, retained_count=len(rows), **kw
    )


def by_id(report):
    return {row["task_id"]: row for row in report["task_results"]}


def test_station_preview_proposes_distinct_strong_task_candidates():
    result = preview()
    assert result["probe_status"] == "station_historical_task_p2000_preview"
    assert result["station_id"] == "194"
    assert result["station_task_count"] == 3
    assert result["tasks_analyzed"] == 3
    assert result["tasks_omitted_due_to_limit"] == 0
    assert result["strong_historical_candidate_tasks"] >= 2
    assert result["tasks_with_conflicting_candidates"] == 0
    ids = by_id(result)
    assert ids["7678"]["candidate_p2000_term"] == "042340"
    assert ids["7678"]["target_task_incidents"] == 5
    assert ids["7678"]["single_task_incidents"] == 2
    assert ids["7678"]["multi_task_incidents"] == 3
    assert ids["7678"]["candidate_heuristic_score"] == 100
    assert ids["7678"]["review_status"] == "strong_candidate_for_manual_verification"
    assert ids["7678"]["candidate_conflict"] is False
    assert ids["7678"]["conflicting_task_ids"] == []

    assert ids["7674"]["candidate_p2000_term"] == "042330"
    assert ids["7674"]["single_task_incidents"] == 4
    assert ids["7674"]["review_status"] == "strong_candidate_for_manual_verification"
    assert ids["7684"]["candidate_p2000_term"] is None
    assert ids["7684"]["review_status"] == "no_supported_unique_candidate"
    assert len(ids["7678"]["top_terms"]) <= 3
    assert ids["7678"]["top_terms"][0]["p2000_term"] == "042340"

    for forbidden in (
        "PRIVATE NAME", "PRIVATE ADDRESS", "PRIVATE TOKEN",
        "incident_responses", "formatted_address", "secret",
    ):
        assert forbidden not in str(result)
    assert result["local_storage_modified"] is False
    assert result["brandweerrooster_modified"] is False
    assert result["current_task_configuration_verified"] is False
    assert result["operational_vehicle_dispatch_verified"] is False
    assert result["raw_incident_bodies_returned"] is False
    assert result["personal_data_returned"] is False


def test_conflicting_top_candidates_not_mistaken_for_unique_mappings():
    tasks = {
        1001: [{"id": 1001, "name": "TASK-A", "station_id": 194}],
        1002: [{"id": 1002, "name": "TASK-B", "station_id": 194}],
    }
    rows = [
        incident(111001, [1001], "042340"),
        incident(111002, [1001], "042340"),
        incident(111003, [1001], "042340"),
        incident(112001, [1002], "042340"),
        incident(112002, [1002], "042340"),
        incident(112003, [1002], "042340"),
    ]
    result = preview(rows, tasks)
    assert result["strong_historical_candidate_tasks"] == 2
    assert result["tasks_with_conflicting_candidates"] == 2
    first = by_id(result)["1001"]
    second = by_id(result)["1002"]
    assert first["candidate_conflict"] is True
    assert first["conflicting_task_ids"] == ["1002"]
    assert first["review_status"] == "candidate_shared_by_multiple_station_tasks"
    assert second["candidate_conflict"] is True
    assert second["conflicting_task_ids"] == ["1001"]
    assert second["review_status"] == "candidate_shared_by_multiple_station_tasks"


def test_no_incident_history_returns_unknown_task_evidence_only():
    result = preview([])
    assert result["tasks_analyzed"] == 3
    assert result["strong_historical_candidate_tasks"] == 0
    assert result["tentative_historical_candidate_tasks"] == 0
    assert result["tasks_with_conflicting_candidates"] == 0
    assert all(
        task["candidate_p2000_term"] is None
        for task in result["task_results"]
    )


def test_only_authorized_station_tasks_are_previewed():
    result = preview(station=500)
    assert result["station_task_count"] == 1
    assert len(result["task_results"]) == 1
    assert result["task_results"][0]["task_id"] == "9999"
    assert result["task_results"][0]["task_name"] == "OTHER-STATION"
    assert result["task_results"][0]["candidate_p2000_term"] is None


def test_task_limit_is_bounded_and_visible():
    task_index = {
        ident: [{"id": ident, "name": f"NAME-{ident}", "station_id": 194}]
        for ident in range(1000, 1060)
    }
    result = preview([], task_index)
    assert result["station_task_count"] == 60
    assert result["tasks_analyzed"] == 40
    assert result["tasks_omitted_due_to_limit"] == 20
    assert len(result["task_results"]) == 40
    assert result["task_results"][0]["task_id"] == "1000"


def test_unindexed_and_duplicate_station_task_entries_are_not_guessed():
    task_index = {
        123: [{"id": 123, "name": "TASK-ONE", "station_id": 194},
              {"id": 123, "name": "TASK-ONE", "station_id": 194}],
        124: [{"id": 124, "name": "TASK-TWO", "station_id": 194}],
        125: [{"id": 125, "name": "TASK-OTHER", "station_id": 500}],
    }
    result = preview([incident(10001, [123], "042340")], task_index)
    assert result["station_task_count"] == 2
    assert by_id(result)["123"]["probe_status"] == (
        "task_not_uniquely_indexed_for_this_station"
    )
    assert by_id(result)["123"]["candidate_p2000_term"] is None


def test_optional_explicit_incident_request_summary_contains_only_numeric_ids():
    report = preview(
        explicitly_requested_ids=["3012389", "2992516"],
        api_ids_read=["3012389"],
        api_ids_failed=["2992516"],
    )
    assert report["explicit_incident_ids_requested"] == [
        "3012389", "2992516"
    ]
    assert report["api_incident_ids_read"] == ["3012389"]
    assert report["api_incident_ids_failed"] == ["2992516"]
    assert len(report["task_results"]) == 3


def test_station_without_task_configuration_no_fabricated_mapping():
    result = preview(known_hardenberg(), {})
    assert result["station_task_count"] == 0
    assert result["task_results"] == []
    assert result["strong_historical_candidate_tasks"] == 0
    assert result["tasks_with_conflicting_candidates"] == 0


def test_do_not_confuse_score_with_confidence_percent():
    result = preview()
    assert "not a probability" in result["interpretation"]
    assert result["task_results"][0]["candidate_heuristic_score"] is not None
    assert all(
        "current_task_configuration_verified" not in task
        for task in result["task_results"]
    )


def test_non_numeric_station_id_rejected_before_preview():
    try:
        preview(station="PRIVATE")
    except ValueError as exc:
        assert "numeric station ID" in str(exc)
    else:
        raise AssertionError("Expected station ID validation")
