"""Regression tests for local, time-scoped P2000 replacement assignments."""
from custom_components.fireservicerota.replacement_vehicles import (
    effective_assignment,
    normalize_unit,
)


def assignment(number="041034", station="Gramsbergen", end=None):
    return {
        "vehicle_number": number,
        "station_id": 123,
        "station_name": station,
        "start_time": "2026-11-07T10:00:00+00:00",
        "end_time": end,
    }


def test_numbers_are_normalized():
    assert normalize_unit("04-1034") == "041034"
    assert normalize_unit("041037") == "041037"


def test_matching_is_valid_only_in_assignment_window():
    rows = [assignment(end="2026-11-08T12:00:00+00:00")]
    assert effective_assignment(rows, "04-1034", "2026-11-07T13:00:00+00:00")["station_name"] == "Gramsbergen"
    assert effective_assignment(rows, "04-1034", "2026-11-09T13:00:00+00:00") is None
    assert effective_assignment(rows, "04-1034", "2026-11-06T13:00:00+00:00") is None


def test_other_units_are_unaffected():
    assert effective_assignment([assignment()], "04-2333", "2026-11-07T13:00:00+00:00") is None


def test_ambiguous_assignment_is_ignored():
    assert effective_assignment(
        [assignment(), assignment(station="Other")],
        "041034", "2026-11-07T13:00:00+00:00",
    ) is None


def test_missing_timestamps_do_not_apply_mapping():
    assert effective_assignment([assignment()], "041034", "") is None
