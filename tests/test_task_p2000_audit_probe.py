"""Privacy and station-scoping regression tests for historical task audit probe."""

import pytest

from custom_components.fireservicerota.task_p2000_audit_probe import (
    choose_task_audit_probe,
    summarize_task_audit_probe,
)


def known_index():
    return {
        7678: [{"id": 7678, "name": "TS-BT", "station_id": 194}],
        7674: [{"id": 7674, "name": "TS", "station_id": 194}],
        5000: [{"id": 5000, "name": "TS", "station_id": 500}],
    }


def selection(page=2):
    return choose_task_audit_probe(194, 7678, known_index(), page)


def example_page():
    return [
        {
            "created_at": {"value": "2026-07-01T13:09:15.523+02:00"},
            "audit_log_subject": {"value": "PRIVATE USER"},
            "whodunnit": {"value": "PERSON SECRET"},
            "changes": {"value": (
                "Vereiste termen in P2000 bericht voor aanmaken incident "
                "gewijzigd van 041034 naar 042340"
            )},
        },
        {
            "created_at": "2026-05-01T08:00:00+02:00",
            "changes": "Uitgesloten termen in P2000 bericht: 041034",
        },
        {
            "created_at": "2026-04-01T08:00:00+02:00",
            "changes": "Andere instelling aangepast: 049999",
        },
        {
            "created_at": "2026-03-01T08:00:00+02:00",
            "changes": (
                "Required P2000 message filter changed:\n"
                "old: 041033\n"
                "new: 042340"
            ),
        },
    ]


def test_one_task_one_audit_page_authorized():
    selected = selection()
    assert selected["probe_status"] == "ready_for_one_audit_page_GET"
    assert selected["station_id"] == "194"
    assert selected["task_id"] == "7678"
    assert selected["task_name"] == "TS-BT"
    assert selected["page"] == 2
    assert selected["audit_object_type"] == "task"
    assert selected["api_get_attempted"] is False
    assert selected["raw_audit_changes_returned"] is False


def test_sanitized_page_finds_required_terms_only():
    result = summarize_task_audit_probe(selection(), example_page())
    assert result["probe_status"] == "task_audit_page_readable"
    assert result["audit_record_count"] == 4
    assert result["filter_change_record_count"] == 2
    assert result["historical_numeric_p2000_terms"] == [
        "041033", "041034", "042340",
    ]
    assert result["matching_filter_change_examples"] == [
        {
            "at": "2026-07-01T13:09:15+02:00",
            "numeric_terms": ["041034", "042340"],
        },
        {
            "at": "2026-03-01T08:00:00+02:00",
            "numeric_terms": ["041033", "042340"],
        },
    ]
    assert result["mapping_source"] == (
        "historical_task_audit_changes_not_current"
    )
    assert result["vehicle_number"] is None
    assert result["current_task_vehicle_mapping_verified"] is False
    assert result["personal_data_returned"] is False
    assert result["raw_audit_changes_returned"] is False
    assert result["brandweerrooster_modified"] is False
    assert result["local_storage_modified"] is False
    for private in (
        "PRIVATE USER", "PERSON SECRET", "whodunnit",
        "audit_log_subject", "Uitgesloten termen", "049999",
    ):
        assert private not in str(result)


@pytest.mark.parametrize("bad_station,bad_task", [
    (194, 5000), (500, 7678), (194, 99999),
])
def test_audit_refuses_non_station_task(bad_station, bad_task):
    result = choose_task_audit_probe(
        bad_station, bad_task, known_index(), 1
    )
    assert result["probe_status"] == "task_not_uniquely_indexed_for_this_station"
    assert result["api_get_attempted"] is False


@pytest.mark.parametrize("bad_page", [0, 6, -1, "2", None, True])
def test_audit_page_must_be_bounded_integer(bad_page):
    with pytest.raises(ValueError):
        choose_task_audit_probe(194, 7678, known_index(), bad_page)


@pytest.mark.parametrize("wrong_type", [None, {}, "string", {"data": []}])
def test_invalid_audit_response_does_not_claim_any_changes(wrong_type):
    result = summarize_task_audit_probe(selection(), wrong_type)
    assert result["probe_status"] == "task_audit_unavailable_or_unexpected"
    assert result["historical_numeric_p2000_terms"] == []
    assert result["vehicle_number"] is None
    assert result["api_get_attempted"] is True


def test_no_filter_changes_is_not_current_negative_evidence():
    result = summarize_task_audit_probe(
        selection(1),
        [
            {"changes": {"value": "Gewijzigd door Mevrouw van Example"}},
            {"changes": {"value": "P2000 uitgesloten termen: 042340"}},
        ],
    )
    assert result["probe_status"] == "task_audit_page_readable"
    assert result["audit_record_count"] == 2
    assert result["filter_change_record_count"] == 0
    assert result["historical_numeric_p2000_terms"] == []
    assert result["mapping_source"] is None
    assert result["current_task_vehicle_mapping_verified"] is False


def test_audit_limits_records_and_never_returns_raw_user_content():
    rows = [{
        "created_at": "not-a-date",
        "changes": (
            "Vereiste termen in P2000 bericht: 042340. "
            "PRIVATE CREW NAME MUST NOT LEAK."
        ),
        "whodunnit": "SECRET ADMIN",
    }] * 700
    result = summarize_task_audit_probe(selection(), rows)
    assert result["audit_record_count"] == 500
    assert result["audit_page_truncated"] is True
    assert len(result["matching_filter_change_examples"]) <= 25
    assert result["historical_numeric_p2000_terms"] == ["042340"]
    assert result["matching_filter_change_examples"][0]["at"] is None
    assert "PRIVATE CREW NAME" not in str(result)
    assert "SECRET ADMIN" not in str(result)


def test_large_or_invalid_change_text_is_not_exposed_or_parsed():
    records = [
        {"changes": "required p2000 term 042340 " * 3000},
        {"changes": {"value": {"person": "SECRET", "id": 042340}}},
        {"changes": 123},
    ]
    result = summarize_task_audit_probe(selection(), records)
    assert result["audit_record_count"] == 3
    assert result["filter_change_record_count"] == 0
    assert result["historical_numeric_p2000_terms"] == []
    assert "SECRET" not in str(result)
