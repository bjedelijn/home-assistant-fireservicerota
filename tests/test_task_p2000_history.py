"""Regression checks for historical task P2000 association without assignments."""

import pytest

from custom_components.fireservicerota.task_p2000_history import (
    analyze_task_p2000_history,
)


def task_index():
    return {
        7678: [{"id": 7678, "name": "TS-BT", "station_id": 194}],
        7674: [{"id": 7674, "name": "TS", "station_id": 194}],
        7684: [{"id": 7684, "name": "TW-G", "station_id": 194}],
        6000: [{"id": 6000, "name": "OTHER-STATION", "station_id": 500}],
    }


def record(ident, tasks, body):
    return {
        "id": ident,
        "task_ids": tasks,
        "body": body,
        "name": "PRIVATE INCIDENT NAME",
        "address": "PERSONAL HOME ADDRESS",
        "incident_responses": [
            {"user_name": "PRIVATE FIREFIGHTER", "membership_id": 12345}
        ],
        "p2000_enrichment": {"person": "SECRET PERSON"},
    }


def html_history_cases():
    """P2000 term pattern and task lists based on five user-supplied 2026 rows.

    Only the numeric incident IDs, tasks and terms are needed; no location,
    persons or alert text from the original incidents is included.
    """
    return [
        record(3012389, [7674, 7678, 7684],
               "P 1 042330 042340 042241 042040 052441 059088 059001"),
        record(2992516, [7678, 7684],
               "P 1 059004 059091 042340 055341 042241"),
        record(2969366, [7674, 7678], "P 1 042330 042340"),
        record(2864999, [7678], "P 1 059004 059091 055341 042340 059002"),
        record(2805609, [7678], "P 2 042340"),
    ]


def analyze(rows, task=7678, station=194, **kwargs):
    return analyze_task_p2000_history(
        station, task, task_index(), rows, retained_count=len(rows), **kwargs
    )


def test_five_ts_bt_incidents_strong_historical_candidate():
    result = analyze(html_history_cases())
    assert result["probe_status"] == "strong_historical_candidate_not_verified"
    assert result["candidate_p2000_term"] == "042340"
    assert result["candidate_evidence_grade"] == "strong_historical_candidate"
    assert result["candidate_heuristic_score"] == 100
    assert result["target_task_incidents"] == 5
    assert result["target_single_task_incidents"] == 2
    assert result["target_multi_task_incidents"] == 3
    assert result["records_examined"] == 5
    assert result["usable_incident_records"] == 5
    first = result["candidate_terms"][0]
    assert first["p2000_term"] == "042340"
    assert first["incidents_with_task_and_term"] == 5
    assert first["single_task_incidents_with_term"] == 2
    assert first["single_task_single_term_incidents"] == 1
    assert first["coverage_percent"] == 100
    assert first["single_task_incident_ids"] == ["2805609", "2864999"]
    assert result["operational_vehicle_dispatch_verified"] is False
    assert result["current_task_configuration_verified"] is False
    assert result["local_storage_modified"] is False
    assert result["brandweerrooster_modified"] is False
    assert result["personal_data_returned"] is False
    assert result["raw_incident_bodies_returned"] is False
    for secret in (
        "PRIVATE INCIDENT NAME", "PERSONAL HOME ADDRESS",
        "PRIVATE FIREFIGHTER", "SECRET PERSON", "membership_id",
    ):
        assert secret not in str(result)


def test_no_solo_evidence_must_never_select_code():
    rows = [
        record(10001, [7674, 7678], "P 1 042340"),
        record(10002, [7678, 7684], "P 1 042340"),
        record(10003, [7678, 7684], "P 1 042340"),
    ]
    result = analyze(rows)
    assert result["probe_status"] == "multi_task_only_no_per_task_attribution"
    assert result["candidate_p2000_term"] is None
    assert result["candidate_evidence_grade"] == "multi_task_only"
    assert result["candidate_terms"][0]["incidents_with_task_and_term"] == 3
    assert result["candidate_terms"][0]["single_task_incidents_with_term"] == 0


def test_two_tied_codes_in_all_solo_events_are_ambiguous():
    rows = [
        record(10001, [7678], "P 1 042330 042340"),
        record(10002, [7678], "P 1 042330 042340"),
        record(10003, [7678, 7684], "P 1 042330 042340"),
    ]
    result = analyze(rows)
    assert result["probe_status"] == "ambiguous_equally_supported_terms"
    assert result["candidate_p2000_term"] is None
    assert result["candidate_heuristic_score"] is None


def test_two_solo_incidents_support_tentative_only():
    result = analyze([
        record(10001, [7678], "P 1 042340"),
        record(10002, [7678], "P 1 042340 042330"),
    ])
    assert result["probe_status"] == "tentative_historical_candidate_not_verified"
    assert result["candidate_p2000_term"] == "042340"
    assert result["candidate_evidence_grade"] == "tentative_historical_candidate"


def test_single_occurrence_never_selects_candidate():
    result = analyze([record(10001, [7678], "P 1 042340")])
    assert result["probe_status"] == "insufficient_historical_incident_evidence"
    assert result["candidate_p2000_term"] is None
    assert result["candidate_evidence_grade"] == "insufficient"


def test_no_valid_target_incident_no_guess():
    rows = [
        record(10001, [7674], "P 1 042330"),
        record(10002, [7684], "P 1 042340"),
    ]
    result = analyze(rows)
    assert result["target_task_incidents"] == 0
    assert result["candidate_p2000_term"] is None
    assert result["probe_status"] == "insufficient_historical_incident_evidence"
    assert result["other_station_task_incidents"] == 2


@pytest.mark.parametrize("station,task", [
    (500, 7678),
    (194, 6000),
    (194, 999999),
])
def test_cross_station_or_unknown_task_rejected(station, task):
    result = analyze(html_history_cases(), task=task, station=station)
    assert result["probe_status"] == "task_not_uniquely_indexed_for_this_station"
    assert result["candidate_p2000_term"] is None
    assert result["candidate_terms"] == []
    assert result["records_examined"] == 0


def test_both_other_stations_and_task_multiple_count_as_multi():
    rows = [
        record(10001, [7678, 6000], "P 1 042340"),
        record(10002, [7678, 6000], "P 1 042340"),
    ]
    result = analyze(rows)
    assert result["target_multi_task_incidents"] == 2
    assert result["target_single_task_incidents"] == 0
    assert result["candidate_p2000_term"] is None


def test_distinguishes_other_station_task_negative_samples():
    rows = html_history_cases() + [
        record(10013, [7674], "P 1 042330 049999"),
        record(10014, [7684], "P 1 042360 049999"),
    ]
    result = analyze(rows)
    assert result["target_task_incidents"] == 5
    assert result["other_station_task_incidents"] == 2
    assert result["candidate_p2000_term"] == "042340"
    assert result["candidate_terms"][0]["other_station_task_incidents_with_term"] == 0


def test_every_repeated_token_in_one_body_counts_only_once():
    rows = [
        record(10001, [7678], "042340 042340 042340"),
        record(10002, [7678], "042340"),
        record(10003, [7678, 7674], "042340 042340"),
    ]
    result = analyze(rows)
    assert result["candidate_terms"][0]["incidents_with_task_and_term"] == 3
    assert result["candidate_terms"][0]["single_task_incidents_with_term"] == 2
    assert result["candidate_terms"][0]["single_task_single_term_incidents"] == 2


def test_explicit_newer_incident_detail_overrides_same_id_only():
    rows = [
        record(10001, [7678], "P 1 042330"),
        record(10002, [7678], "P 1 042340"),
        record(10001, [7678], "P 1 042340"),
    ]
    result = analyze(rows, explicitly_requested_ids=["10001"],
                     api_ids_read=["10001"])
    assert result["records_examined"] == 3
    assert result["usable_incident_records"] == 2
    assert result["target_task_incidents"] == 2
    assert result["candidate_p2000_term"] == "042340"
    assert result["candidate_terms"][0]["incidents_with_task_and_term"] == 2
    assert result["explicit_incident_ids_requested"] == ["10001"]
    assert result["api_incident_ids_read"] == ["10001"]


@pytest.mark.parametrize("bad", [
    {"id": "10001", "task_ids": [7678], "body": "P 1: no six digit code"},
    {"id": "10001", "task_ids": [], "body": "042340"},
    {"id": "10001", "task_ids": [7678], "body": 4240},
    {"id": "10001", "task_ids": "7678", "body": "042340"},
    {"id": "PRIVATE", "task_ids": [7678], "body": "042340"},
    {"id": 10001, "task_ids": [True], "body": "042340"},
    {"id": 10001, "task_ids": [7678], "body": "x" * 12001},
])
def test_bad_incident_rows_are_skipped_without_raw_leaks(bad):
    result = analyze([bad])
    assert result["usable_incident_records"] == 0
    assert result["skipped_unusable_records"] == 1
    assert result["candidate_p2000_term"] is None
    assert "PRIVATE" not in str(result)


def test_missing_body_is_not_silently_recovered_from_other_private_fields():
    row = record(10001, [7678], "")
    row["description"] = "P 1 042340"
    row["p2000_enrichment"]["body"] = "P 1 042340"
    result = analyze([row])
    assert result["candidate_terms"] == []
    assert result["usable_incident_records"] == 0


def test_avoid_embedded_id_or_capcode_false_positive():
    rows = [
        record(10001, [7678], "P 1 0423400 610306 042340"),
        record(10002, [7678], "P 1 1042340 042340"),
    ]
    result = analyze(rows)
    assert result["candidate_terms"][0]["p2000_term"] == "042340"
    assert len(result["candidate_terms"]) == 1


def test_truncates_input_records_and_cannot_return_personal_data():
    rows = [
        record(i, [7678], f"P 1 0{i:05d}")
        for i in range(10001, 10071)
    ]
    result = analyze(rows)
    assert result["records_examined"] == 40
    assert result["usable_incident_records"] == 40
    assert len(result["candidate_terms"]) <= 15
    assert result["raw_incident_bodies_returned"] is False
    assert "PRIVATE" not in str(result)


def test_no_score_should_be_mistaken_for_statistical_probability():
    result = analyze(html_history_cases())
    assert result["candidate_heuristic_score"] is not None
    assert any("uncalibrated" in s for s in result["caveats"])
    assert any("not a historical" in s for s in result["caveats"])


def test_no_api_fetched_incidents_reports_only_explicit_id_errors():
    result = analyze(
        html_history_cases(),
        explicitly_requested_ids=["999", "1000"],
        api_ids_read=["999"],
        api_ids_failed=["1000"],
    )
    assert result["api_incident_ids_failed"] == ["1000"]
    assert result["api_incident_ids_read"] == ["999"]
    assert result["explicit_incident_ids_requested"] == ["999", "1000"]
