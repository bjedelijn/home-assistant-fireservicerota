"""Synthetic-only task/vehicle evidence regression tests."""
from custom_components.fireservicerota.task_vehicle_evidence import (
    matched_p2000_evidence,
    task_evidence,
)


def test_task_context_only_current_index_and_no_private_data():
    incident = {
        "id": 1234,
        "task_ids": [100, 100, 200],
        "crew_requirements": [{"skills": [{"required": 2}]}],
        "responses": [{"name": "PERSON_NOT_FOR_OUTPUT", "membership_id": 12345}],
        "formatted_address": "PRIVATE_ADDRESS_NOT_FOR_OUTPUT",
    }
    index = {
        100: [{"id": 100, "name": "TS", "station_id": 10}],
        200: [{"id": 200, "name": "WTS", "station_id": 10}],
    }
    result = task_evidence(incident, index)
    assert result["task_ids"] == ["100", "200"]
    assert result["resolved_tasks"][0]["station_tasks"] == [
        {"station_id": "10", "task_name": "TS"}
    ]
    assert result["crew_requirement_groups"] == 1
    assert "PERSON_NOT_FOR_OUTPUT" not in str(result)
    assert "PRIVATE_ADDRESS_NOT_FOR_OUTPUT" not in str(result)


def test_tasks_unknown_and_malformed_do_not_infer_vehicle():
    result = task_evidence({"task_ids": [99, "abc", None]}, {})
    assert result["task_ids"] == ["99"]
    assert result["resolved_tasks"][0]["resolution"] == "unresolved"
    assert "units" not in result


def test_p2000_correlated_incident_only_no_raw_messages():
    matches = [
        {
            "incident_ids": ["1234"],
            "p2000_enrichment": {
                "units": ["042330"],
                "sources": ["p2000_page"],
                "message": "PRIVATE_TEXT_NOT_FOR_OUTPUT",
            },
        },
        {
            "incident_ids": ["5678"],
            "p2000_enrichment": {
                "units": ["042999"],
                "sources": ["rtl"],
            },
        },
    ]
    result = matched_p2000_evidence(matches, 1234)
    assert result["status"] == "correlated_p2000_alert"
    assert result["units"] == ["042330"]
    assert result["sources"] == ["p2000_page"]
    assert "PRIVATE_TEXT_NOT_FOR_OUTPUT" not in str(result)
    assert matched_p2000_evidence(matches, 7777)["status"] == "no_retained_correlation"
