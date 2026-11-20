"""Offline normalization tests for the optional p2000.page provider."""
from datetime import datetime, timezone

from custom_components.fireservicerota.enrichment.nl.p2000.page import (
    normalize_page_event,
    valid_regions,
)


def test_region_validation_rejects_url_injection_and_duplicates():
    assert valid_regions("06")
    assert valid_regions("06~17")
    assert not valid_regions("06~06")
    assert not valid_regions("06/uid/test")
    assert not valid_regions("99")
    assert not valid_regions("")


def test_live_brandweer_event_normalizes_without_secrets():
    received = datetime(2026, 11, 20, tzinfo=timezone.utc).isoformat()
    event = normalize_page_event({
        "uid": "synthetic-test-01",
        "timestamp": "1792751330",
        "dienst": "Brandweer",
        "melding": "P 1 Brand woning 042330 042360",
        "plaats": "Zwolle",
        "prio": "1",
        "capcodes": "0611072 0620591",
        "voertuigen_json": '["042330", "042360"]',
    }, received)
    assert event is not None
    assert event.source == "p2000_page"
    assert event.external_id == "p2000_page:synthetic-test-01"
    assert event.units == ["042330", "042360"]
    assert event.priority == 1
    assert event.event_time is not None
    assert event.received_at == received


def test_non_fire_or_malformed_is_dropped():
    received = "2026-11-20T19:00:00+00:00"
    assert normalize_page_event({"uid": "test", "dienst": "Ambulance", "melding": "test"}, received) is None
    assert normalize_page_event({"dienst": "Brandweer", "melding": "test"}, received) is None
    assert normalize_page_event({"uid": "test", "dienst": "Brandweer"}, received) is None


def test_missing_vehicles_and_bad_timestamp_do_not_crash():
    event = normalize_page_event({
        "uid": "test", "dienst": "Brandweer", "melding": "P 2 melding",
        "timestamp": "not-a-time", "capcodes_json": "{invalid json",
    }, "2026-11-20T19:00:00+00:00")
    assert event is not None
    assert event.event_time is None
    assert event.units == []
