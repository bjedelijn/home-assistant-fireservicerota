"""Synthetic detail capability probes; never include live incident information."""
from custom_components.fireservicerota.historical_detail_probe import (
    summarize_incident_detail_capabilities,
)


def test_only_static_presence_counts_are_emitted():
    result = summarize_incident_detail_capabilities([
        {
            "id": 1001,
            "title": "SYNTHETIC_PRIVATE_INCIDENT",
            "priority": 1,
            "created_at": "2024-03-01T12:00:00+01:00",
            "station_id": 9001,
            "incident_responses": [{"name": "SYNTHETIC_PRIVATE_NAME"}],
            "tokens": ["SYNTHETIC_PRIVATE_TOKEN"],
        },
        {
            "id": 1002,
            "description": "SYNTHETIC_PRIVATE_INCIDENT_TWO",
            "task_ids": [10, 20],
            "crew_assignments": [{"membership_id": 99}],
        },
    ])
    assert result["samples_inspected"] == 2
    assert result["fields_present_count"]["incident_title"] == 2
    assert result["fields_present_count"]["station_reference"] == 1
    assert result["fields_present_count"]["response_information"] == 1
    assert result["fields_present_count"]["fairness_assignment"] == 1
    assert result["field_semantics_verified"] is False
    assert result["fairness_evidence_verified"] is False
    assert result["incident_identifiers_returned"] is False
    assert "SYNTHETIC_PRIVATE" not in str(result)
    assert "1001" not in str(result)
    assert "9001" not in str(result)


def test_invalid_response_shape_and_empty_fields():
    result = summarize_incident_detail_capabilities([
        None,
        [],
        {"name": "", "priority": None, "station_ids": [], "vehicles": {}},
    ])
    assert result["samples_inspected"] == 3
    assert result["unexpected_response_shapes"] == 2
    assert result["dict_responses"] == 1
    assert all(value == 0 for value in result["fields_present_count"].values())


def test_unknown_keys_are_never_echoed():
    key = "SYNTHETIC_DYNAMIC_MEMBER_KEY"
    result = summarize_incident_detail_capabilities([
        {key: "SYNTHETIC_PRIVATE_NAME"},
    ])
    assert key not in str(result)
    assert result["dict_responses"] == 1
