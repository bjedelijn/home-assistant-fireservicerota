"""Regression tests for simultaneous and historical vehicle replacements."""
import asyncio

import pytest

from custom_components.fireservicerota import replacement_vehicles as vehicles

def record(original="042350", replacement="041050", station_id=194, start="2026-11-07T10:00:00+00:00", end=None):
    return {
        "station_id": station_id, "station_name": "Test Post",
        "original_vehicle_number": original, "vehicle_number": replacement,
        "start_time": start, "end_time": end,
    }

def test_format_and_event_timing():
    assert vehicles.normalize_unit("04-1050") == "041050"
    rows = [record(end="2026-11-08T12:00:00+00:00")]
    assert vehicles.effective_assignment(rows, "04-1050", "2026-11-07T13:00:00+00:00")["original_vehicle_number"] == "042350"
    assert vehicles.effective_assignment(rows, "041050", "2026-11-09T13:00:00+00:00") is None
    assert vehicles.effective_assignment(rows, "041050", "2026-11-06T13:00:00+00:00") is None
    assert vehicles.effective_assignment(rows, "042350", "2026-11-07T13:00:00+00:00") is None

def test_ambiguous_legacy_or_duplicate_mapping_is_not_assumed():
    old = record()
    legacy = {**old, "original_vehicle_number": None, "station_id": 3853}
    assert vehicles.effective_assignment([old, legacy], "041050", "2026-11-07T13:00:00+00:00") is None
    assert vehicles.effective_assignment([old], "041050", "") is None

class FakeStore:
    storage = None
    def __init__(self, hass, version, key):
        self.storage = hass
    async def async_load(self):
        return self.storage.get("data")
    async def async_save(self, value):
        self.storage["data"] = value

def test_two_replacements_per_station_and_targeted_clear(monkeypatch):
    monkeypatch.setattr(vehicles, "Store", FakeStore)
    disk = {}
    store = vehicles.ReplacementVehicleStore(disk, "demo")

    async def run():
        await store.async_load()
        await store.async_set(station_id=194, station_name="Test Post", original_vehicle_number="04-2350", vehicle_number="04-1050")
        await store.async_set(station_id=194, station_name="Test Post", original_vehicle_number="04-2360", vehicle_number="04-1060")
        assert len(store.active) == 2
        assert await store.async_clear(station_id=194, original_vehicle_number="04-2350") is True
        assert len(store.active) == 1
        assert store.active[0]["original_vehicle_number"] == "042360"
        assert store.active[0]["vehicle_number"] == "041060"
        assert await store.async_clear(station_id=194, original_vehicle_number="04-2350") is False
    asyncio.run(run())

def test_replace_one_does_not_touch_other_and_preserves_history(monkeypatch):
    monkeypatch.setattr(vehicles, "Store", FakeStore)
    disk = {}
    store = vehicles.ReplacementVehicleStore(disk, "demo")
    async def run():
        await store.async_load()
        await store.async_set(station_id=194, station_name="Test Post", original_vehicle_number="042350", vehicle_number="041050")
        await store.async_set(station_id=194, station_name="Test Post", original_vehicle_number="042360", vehicle_number="041060")
        await store.async_set(station_id=194, station_name="Test Post", original_vehicle_number="042350", vehicle_number="041051")
        assert len(store.active) == 2
        assert len(store.records) == 3
        assert any(x["original_vehicle_number"] == "042350" and x["vehicle_number"] == "041050" and x["end_time"] for x in store.records)
        assert any(x["original_vehicle_number"] == "042360" and x["vehicle_number"] == "041060" and not x["end_time"] for x in store.records)
    asyncio.run(run())

def test_reject_duplicate_replacement_across_posts(monkeypatch):
    monkeypatch.setattr(vehicles, "Store", FakeStore)
    disk = {}
    store = vehicles.ReplacementVehicleStore(disk, "demo")
    async def run():
        await store.async_load()
        await store.async_set(station_id=194, station_name="Test Post", original_vehicle_number="042350", vehicle_number="041050")
        with pytest.raises(ValueError, match="already assigned"):
            await store.async_set(station_id=3853, station_name="Other", original_vehicle_number="042333", vehicle_number="041050")
        with pytest.raises(ValueError, match="different"):
            await store.async_set(station_id=194, station_name="Test Post", original_vehicle_number="042350", vehicle_number="042350")
    asyncio.run(run())

def test_beta1_migration_deactivates_unqualified_active_mapping(monkeypatch):
    monkeypatch.setattr(vehicles, "Store", FakeStore)
    disk = {"data": {"records": [
        {"station_id": 3853, "station_name": "Post", "vehicle_number": "041037",
         "start_time": "2026-11-06T12:00:00+00:00", "end_time": None}
    ]}}
    store = vehicles.ReplacementVehicleStore(disk, "demo")
    asyncio.run(store.async_load())
    assert store.active == []
    assert store.records[0]["original_vehicle_number"] is None
    assert store.records[0]["end_time"] is not None
    assert disk["data"]["records"][0]["end_time"] is not None
