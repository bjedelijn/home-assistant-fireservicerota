"""One-task, bounded, privacy-safe P2000 term API diagnostic tests."""

from copy import deepcopy

import pytest

from custom_components.fireservicerota.task_p2000_probe import (
    choose_task_p2000_probe,
    inspect_task_fields,
    summarize_task_p2000_probe,
)


def task_index():
    return {
        7678: [{
            "id": 7678, "name": "TS-BT", "station_id": 194,
        }],
        7674: [{
            "id": 7674, "name": "TS", "station_id": 194,
        }],
        1012: [{
            "id": 1012, "name": "TS", "station_id": 500,
        }],
    }


def cached_groups():
    return [{
        "id": 194,
        "type": "station",
        "name": "Hardenberg",
        "memberships": [
            {"user_name": "NEVER RETURN A CREW NAME", "id": 777777},
        ],
        "tasks": [{
            "id": 7678,
            "name": "TS-BT",
            "station_ids": [194],
            "p2000_filters": {
                "required_terms_in_p2000_message": "042340",
                "excluded_terms_in_p2000_message": "Intrekken",
            },
            "member_details": {"name": "SENSITIVE"},
            "authentication_token": "PRIVATE",
        }],
    }]


def selected():
    return choose_task_p2000_probe(
        194, 7678, task_index(), cached_groups()
    )


def task_api():
    return {
        "id": 7678,
        "name": "TS-BT",
        "station_ids": [194],
        "gms_station_code": "HARDBG",
        "gms_team_code": "b-ts",
        "required_terms_in_p2000_message": "042340",
        "excluded_terms_in_p2000_message": "Intrekken, 041034",
        "memberships": [{
            "id": 1000, "name": "VERY PRIVATE", "user_id": 2000,
        }],
        "user_data": {"full_name": "SECRET PERSON"},
        "secret_token": "supersecret",
    }


def test_candidate_is_current_station_task_only():
    selection = selected()
    assert selection["probe_status"] == "ready_for_single_task_GET"
    assert selection["task_id"] == "7678"
    assert selection["station_id"] == "194"
    assert selection["task_name"] == "TS-BT"
    assert selection["api_get_attempted"] is False
    assert selection["cached_task_records_found"] == 1
    assert selection["cached_required_p2000_vehicle_terms"] == ["042340"]
    assert selection["cached_required_term_paths"] == [
        "p2000_filters.required_terms_in_p2000_message"
    ]
    assert selection["vehicle_number"] is None
    assert selection["personal_data_returned"] is False
    for confidential in ["NEVER RETURN", "SENSITIVE", "PRIVATE", "user_name"]:
        assert confidential not in str(selection)


def test_live_task_p2000_config_maps_042340_from_exact_required_field():
    result = summarize_task_p2000_probe(selected(), task_api())
    assert result["probe_status"] == "task_detail_readable"
    assert result["api_task_id_matches"] is True
    assert result["api_required_term_paths"] == [
        "required_terms_in_p2000_message"
    ]
    assert result["api_required_p2000_vehicle_terms"] == ["042340"]
    assert result["vehicle_number"] == "042340"
    assert result["vehicle_mapping_source"] == (
        "live_task_api_required_message_filter"
    )
    assert result["vehicle_mapping_status"] == (
        "one_explicit_required_p2000_number"
    )
    assert result["api_get_attempted"] is True
    assert result["brandweerrooster_modified"] is False
    assert result["local_storage_modified"] is False
    assert result["operational_vehicle_dispatch_verified"] is False
    for confidential in (
        "VERY PRIVATE", "SECRET PERSON", "supersecret",
        "member_details", "memberships", "user_data", "secret_token",
        "Intrekken", "041034", "1000", "2000",
    ):
        assert confidential not in str(result)


def test_live_api_takes_precedence_over_cached_discovery():
    record = task_api()
    record["required_terms_in_p2000_message"] = "042330"
    result = summarize_task_p2000_probe(selected(), record)
    assert result["vehicle_number"] == "042330"
    assert result["api_required_p2000_vehicle_terms"] == ["042330"]
    assert result["cached_required_p2000_vehicle_terms"] == ["042340"]


def test_cached_term_is_explicitly_identified_if_task_detail_omits_it():
    record = task_api()
    record.pop("required_terms_in_p2000_message")
    result = summarize_task_p2000_probe(selected(), record)
    assert result["api_required_p2000_vehicle_terms"] == []
    assert result["vehicle_number"] == "042340"
    assert result["vehicle_mapping_source"] == (
        "cached_group_task_required_message_filter"
    )


@pytest.mark.parametrize("response", [
    None, [], {}, {"id": 1111},
    {"task": {"id": 1111, "required_terms": "042340"}},
])
def test_unavailable_or_wrong_task_never_links_roepnummer(response):
    result = summarize_task_p2000_probe(selected(), response)
    assert result["vehicle_number"] is None
    assert result["api_required_p2000_vehicle_terms"] == []
    assert result["api_get_attempted"] is True
    assert result["vehicle_mapping_status"] == "unverified"


@pytest.mark.parametrize("bad_station,bad_task", [
    (500, 7678), (194, 1012), (194, 9999),
])
def test_no_cross_station_task_permission(bad_station, bad_task):
    result = choose_task_p2000_probe(
        bad_station, bad_task, task_index(), cached_groups()
    )
    assert result["probe_status"] == (
        "task_not_uniquely_indexed_for_this_station"
    )
    assert result["api_get_attempted"] is False
    assert result["vehicle_number"] is None


def test_ambiguous_station_index_does_not_attempt_remote_read():
    index = task_index()
    index[7678].append({"id": 7678, "name": "TS-BT", "station_id": 194})
    result = choose_task_p2000_probe(
        194, 7678, index, cached_groups()
    )
    assert result["probe_status"] == (
        "task_not_uniquely_indexed_for_this_station"
    )
    assert result["api_get_attempted"] is False


def test_excluded_or_user_supplied_numeric_values_never_become_vehicle():
    record = {
        "id": 7678,
        "excluded_terms_in_p2000_message": "042340",
        "user_id": 424242,
        "memberships": [{"required_terms": "049999"}],
        "authentication_token": "041034",
        "incident_body": "P 1 042340",
    }
    scan = inspect_task_fields(record)
    assert scan["required_vehicle_terms"] == []
    assert "user_id" not in scan["field_names"]
    assert "memberships" not in scan["field_names"]
    assert "authentication_token" not in scan["field_names"]


@pytest.mark.parametrize("input_value,expected", [
    ("042340", ["042340"]),
    ("042340,042330", ["042330", "042340"]),
    ("042340;042330", ["042330", "042340"]),
    ("042340\n042330", ["042330", "042340"]),
    (["042340", "042330"], ["042330", "042340"]),
    ("04-2340", []),
    ("P 1 042340", []),
    ("042340 042330", []),
    ("112233445566", []),
])
def test_only_exact_explicit_required_p2000_numbers_are_returned(
    input_value, expected,
):
    record = {
        "id": 7678,
        "required_terms_in_p2000_message": input_value,
        "excluded_terms": "041034",
    }
    scan = inspect_task_fields(record)
    assert scan["required_vehicle_terms"] == expected


def test_multiple_required_numbers_do_not_invent_one_vehicle():
    record = task_api()
    record["required_terms_in_p2000_message"] = "042340,042330"
    result = summarize_task_p2000_probe(selected(), record)
    assert result["vehicle_number"] is None
    assert result["vehicle_mapping_status"] == (
        "multiple_required_p2000_numbers"
    )


def test_nested_api_task_wrapper_and_nested_required_term_field():
    record = task_api()
    record.pop("required_terms_in_p2000_message")
    record["p2000_filters"] = {"required_terms": "042340"}
    response = {"task": record, "owner": "NEVER_RETURN_OWNER"}
    result = summarize_task_p2000_probe(selected(), response)
    assert result["vehicle_number"] == "042340"
    assert result["api_required_term_paths"] == [
        "p2000_filters.required_terms"
    ]
    assert "NEVER_RETURN_OWNER" not in str(result)


def test_no_recursive_person_data_extraction():
    record = task_api()
    record["member_details"] = {
        "required_terms_in_p2000_message": "049999",
        "user": "SECRET",
    }
    record["personal_info"] = {
        "p2000_required_terms": "049998",
    }
    scan = inspect_task_fields(record)
    assert scan["required_vehicle_terms"] == ["042340"]
    assert all(
        not key.startswith("member_details") and
        not key.startswith("personal_info")
        for key in scan["recognized_required_term_paths"]
    )


def test_malformed_large_payload_bounded_field_introspection():
    record = {"id": 7678}
    for idx in range(1000):
        record["field_" + str(idx)] = "042340"
    record["member_name"] = "DELICATE"
    preview = inspect_task_fields(record)
    assert len(preview["field_names"]) <= 80
    assert preview["required_vehicle_terms"] == []
    assert "member_name" not in preview["field_names"]
    assert "DELICATE" not in str(preview)
