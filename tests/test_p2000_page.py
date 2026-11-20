"""Offline normalization tests for the optional p2000.page provider."""
from collections import deque
from datetime import datetime, timezone

from custom_components.fireservicerota.enrichment.nl.p2000.page import (
    P2000PageWebsocketProvider,
    normalize_page_event,
    matches_regions,
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


def test_provider_accepts_uid_once_and_wakes_processing():
    """Same provider UID must never cause a second live announcement."""
    wake_calls = []
    provider = object.__new__(P2000PageWebsocketProvider)
    provider._pending = deque(maxlen=500)
    provider._seen = deque(maxlen=1000)
    provider._seen_set = set()
    provider._on_event = lambda: wake_calls.append(True)
    provider._received = 0
    provider._regions = "06"
    data = {
        "uid": "synthetic-unique-id",
        "regios": "R06",
        "dienst": "Brandweer",
        "melding": "P 1 Brand woning 042330",
        "timestamp": "1792751330",
    }
    provider._accept(data)
    provider._accept(data)
    assert provider._received == 1
    assert len(provider._pending) == 1
    assert len(wake_calls) == 1
    assert provider.provider_debug["pending_events"] == 1
    assert "api_key" not in provider.provider_debug


def test_region_filter_rejects_wrong_and_missing_regions():
    assert matches_regions({"regios": "R04"}, "04")
    assert matches_regions({"regios": "R04 R06"}, "06~17")
    assert not matches_regions({"regios": "R04"}, "06")
    assert not matches_regions({"regios": ""}, "04")
    assert not matches_regions({"regios": "R99"}, "04")
    assert not matches_regions({}, "04")


def test_wrong_region_never_enters_live_queue():
    provider = object.__new__(P2000PageWebsocketProvider)
    provider._pending = deque(maxlen=500)
    provider._seen = deque(maxlen=1000)
    provider._seen_set = set()
    provider._on_event = None
    provider._received = 0
    provider._regions = "06"
    provider._accept({
        "uid": "wrong-region", "regios": "R04", "dienst": "Brandweer",
        "melding": "P 1 Brand woning", "timestamp": "1792751330",
    })
    assert provider._received == 0
    assert len(provider._pending) == 0
