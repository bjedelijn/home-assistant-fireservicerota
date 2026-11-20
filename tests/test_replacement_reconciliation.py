"""Offline guardrails for vehicle replacement reconciliation."""
from custom_components.fireservicerota.replacement_reconciliation import evaluate_replacement

RECORD = {
    "station_id": 3853, "station_name": "Gramsbergen",
    "original_vehicle_number": "042333", "vehicle_number": "041037",
    "start_time": "2026-11-20T20:00:00+00:00", "end_time": None,
}
BWR = dict(
    bwr_station_id=3853,
    bwr_vehicle_number="042333",
    bwr_event_time="2026-11-20T21:00:00+00:00",
    bwr_incident_id=3154000,
    bwr_verified_live=True,
)
P2000 = dict(
    p2000_correlated=True,
    p2000_event_time="2026-11-20T21:00:22+00:00",
    p2000_vehicle_numbers=["042333"],
)


def decide(record=None, **kwargs):
    return evaluate_replacement(record or RECORD, **{**BWR, **kwargs})


def test_clears_only_two_confirming_sources():
    result = decide(**P2000)
    assert result["action"] == "clear"
    assert result["reason"] == "bwr_and_p2000_confirmed"
    assert result["incident_id"] == 3154000


def test_original_from_bwr_alone_must_not_clear():
    assert decide()["action"] == "notify"


def test_replacement_never_clears():
    assert decide(bwr_vehicle_number="041037", **P2000)["action"] == "ignore"


def test_unknown_third_vehicle_warns_but_does_not_clear():
    result = decide(bwr_vehicle_number="041099", **P2000)
    assert result["action"] == "notify"
    assert result["reason"] == "third_vehicle"


def test_wrong_station_or_unverified_stream_never_changes():
    assert decide(bwr_station_id=194, **P2000)["action"] == "ignore"
    assert decide(bwr_verified_live=False, **P2000)["action"] == "ignore"


def test_historical_replays_never_change_mapping():
    assert decide(bwr_event_time="2026-11-19T21:00:00+00:00", **P2000)["action"] == "ignore"
    assert decide(record={**RECORD, "end_time": "2026-11-20T20:30:00+00:00"}, **P2000)["action"] == "ignore"


def test_p2000_mismatch_wrong_incident_and_stale_event():
    assert decide(**{**P2000, "p2000_vehicle_numbers": ["041037"]})["action"] == "notify"
    assert decide(**{**P2000, "p2000_correlated": False})["action"] == "notify"
    assert decide(**{**P2000, "p2000_event_time": "2026-11-20T20:30:00+00:00"})["action"] == "notify"


def test_bad_vehicle_never_changes_mapping():
    assert decide(bwr_vehicle_number="unknown", **P2000)["action"] == "ignore"
