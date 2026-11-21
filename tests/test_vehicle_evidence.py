"""Tests for privacy-filtered BrandweerRooster vehicle evidence."""
from custom_components.fireservicerota.vehicle_evidence import incident_vehicle_evidence


def test_exposes_only_vehicle_numbers_and_paths():
    example = {
        "id": 123,
        "email": "person@example.net",
        "incident_responses": [{"user_name": "Private Person", "phone": "0612345678"}],
        "incident_vehicles": [
            {"vehicle_number": "04-2333", "station_id": 3853},
            {"vehicle_number": "041037", "station_id": 3853},
        ],
        "message": "Personal information",
    }
    result = incident_vehicle_evidence(example)
    assert result["incident_id"] == 123
    assert result["fields_found"] >= 2
    numbers = {n for item in result["vehicle_fields"] for n in item["unit_numbers"]}
    assert numbers == {"042333", "041037"}
    rendered = repr(result)
    assert "Private Person" not in rendered
    assert "person@example.net" not in rendered
    assert "Personal information" not in rendered
    assert "0612345678" not in rendered


def test_ordinary_task_names_are_not_mistaken_for_vehicles():
    result = incident_vehicle_evidence({
        "id": 1, "task_ids": [7674],
        "resolved_tasks": [{"name": "TS 7674", "station_id": 194}],
    })
    assert result["vehicle_fields"] == []


def test_empty_and_malformed_inputs_are_safe():
    assert incident_vehicle_evidence({})["fields_found"] == 0
    assert incident_vehicle_evidence(None)["incident_id"] is None
