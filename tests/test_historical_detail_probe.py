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


def test_reviewed_keys_and_nested_structure_never_leak_values():
    result = summarize_incident_detail_capabilities([{
        "priority": 2,
        "task_ids": [9],
        "incident_responses": [{
            "membership_id": 99999,
            "reported_status": "SYNTHETIC_SENSITIVE_STATUS",
            "private_person_name": "SYNTHETIC_PRIVATE_NAME",
        }],
        "responding": [{"response_people": [{"name": "SYNTHETIC_PRIVATE_NAME"}]}],
        "unrecognized_field": {"secret": "SYNTHETIC_SECRET"},
    }])
    assert result["reviewed_keys_present_count"]["priority"]["priority"] == 1
    assert result["reviewed_keys_present_count"]["task_reference"]["task_ids"] == 1
    assert result["reviewed_nested_keys_present_count"]["incident_responses"]["membership_id"] == 1
    assert result["reviewed_nested_keys_present_count"]["incident_responses"]["reported_status"] == 1
    assert result["reviewed_nested_keys_present_count"]["responding"]["response_people"] == 1
    assert "SYNTHETIC_" not in str(result)
    assert "99999" not in str(result)


def test_known_group_arrival_and_skill_fields_are_counted_without_values():
    result = summarize_incident_detail_capabilities([
        {"incident_responses": [{"group_id": 987654321,
                                 "arrived_at_station": "SYNTHETIC_ARRIVAL"}],
         "incident_skill_assignments": [{"membership_id": 987654322,
                                         "skill_ids": [987654323]}]},
        {"incident_responses": [{"group_id": None}],
         "incident_skill_assignments": []},
    ])
    nested = result["reviewed_nested_keys_present_count"]
    assert nested["incident_responses"]["group_id"] == 1
    assert nested["incident_responses"]["arrived_at_station"] == 1
    assert nested["incident_skill_assignments"]["membership_id"] == 1
    assert nested["incident_skill_assignments"]["skill_ids"] == 1
    assert result["fields_present_count"]["skill_assignment_information"] == 1
    assert result["physical_departure_verified"] is False
    assert result["fairness_evidence_verified"] is False
    assert "98765432" not in str(result)
    assert "SYNTHETIC_ARRIVAL" not in str(result)
