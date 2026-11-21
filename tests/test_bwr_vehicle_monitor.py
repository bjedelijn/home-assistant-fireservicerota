"""Guardrails around live BWR dispatch matching and vehicle changes."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.fireservicerota.bwr_vehicle_monitor import (
    ReplacementVehicleMonitor, live_vehicle_assignments,
)

NOW = datetime.now(timezone.utc)
TS = NOW.isoformat()
START = (NOW - timedelta(minutes=2)).isoformat()


def sample(*, trigger="new", dispatched=None):
    return {
        "id": 3154000,
        "trigger": trigger,
        "created_at": TS,
        "task_ids": [7674],
        "dispatched_vehicles": dispatched if dispatched is not None else [
            {
                "station_id": 3853, "vehicle_number": "04-1099",
                "vehicle_function": "TS", "confirmed": True,
            }
        ],
    }


def test_no_heuristic_detection_from_task_or_unverified_callsign():
    assert live_vehicle_assignments({"id": 1, "trigger": "new", "created_at": TS, "task_ids": [7674]}) == []
    assert live_vehicle_assignments(sample(dispatched=[{"station_id": 3853, "vehicle_number": "042333", "vehicle_function": "TS"}])) == []
    assert live_vehicle_assignments(sample(trigger=None)) == []
    assert live_vehicle_assignments(sample(trigger="new", dispatched=[{"station_id": 3853, "vehicle_number": "042333", "confirmed": True}])) == []


def test_only_exact_live_confirmed_station_function_unit():
    result = live_vehicle_assignments(sample(), now=NOW)
    assert result[0]["station_id"] == 3853
    assert result[0]["vehicle_number"] == "041099"
    assert result[0]["vehicle_function"] == "TS"


class Store:
    def __init__(self):
        self.records = [{
            "station_id": 3853,
            "station_name": "Gramsbergen",
            "original_vehicle_number": "042333",
            "vehicle_number": "041037",
            "vehicle_function": "TS",
            "start_time": START,
            "end_time": None,
        }]
        self.clears = []

    @property
    def active(self):
        return [dict(r) for r in self.records if not r.get("end_time")]

    async def async_clear(self, **kwargs):
        self.clears.append(kwargs)
        expected = kwargs["expected_vehicle_number"]
        started = kwargs["expected_start_time"]
        for rec in self.records:
            if rec["vehicle_number"] == expected and rec["start_time"] == started and not rec["end_time"]:
                rec["end_time"] = TS
                return True
        return False


class Bus:
    def __init__(self):
        self.events = []
    def async_fire(self, kind, payload):
        self.events.append((kind, payload))


class Services:
    def __init__(self):
        self.calls = []
    async def async_call(self, domain, service, data, *, target=None, blocking=False):
        self.calls.append((domain, service, data, target))


class Hass:
    def __init__(self):
        self.bus = Bus()
        self.services = Services()
    def async_create_task(self, awaitable):
        return asyncio.create_task(awaitable)


def options(**kwargs):
    return {
        "replacement_auto_clear_enabled": True,
        "replacement_alerts_enabled": True,
        "replacement_alert_channel": "push",
        "replacement_alert_push_entity": "notify.mobile_app_test",
        **kwargs,
    }


def test_third_vehicle_warns_once_and_does_not_clear():
    async def run():
        hass, store = Hass(), Store()
        monitor = ReplacementVehicleMonitor(hass, store, options())
        await monitor.async_handle_live(sample())
        await monitor.async_handle_live(sample(trigger="update"))
        assert len(hass.services.calls) == 1
        assert hass.services.calls[0][:2] == ("notify", "send_message")
        assert len(hass.bus.events) == 1
        assert hass.bus.events[0][1]["silent"] is True
        assert store.clears == []
        monitor.stop()
    asyncio.run(run())


def test_original_return_requires_correlated_p2000_and_cannot_clear_changed_mapping():
    async def run():
        hass, store = Hass(), Store()
        monitor = ReplacementVehicleMonitor(hass, store, options())
        record = store.active[0]
        dispatch = {
            "incident_id": 3154000, "station_id": 3853,
            "vehicle_number": "042333", "vehicle_function": "TS",
            "event_time": TS,
        }
        key = ("3154000", 3853, "042333")
        monitor._pending[key] = (record, dispatch)
        await monitor.async_handle_p2000_match(3154000, [
            SimpleNamespace(units=["041037"], event_time=TS)
        ])
        assert store.clears == []

        store.records[0]["vehicle_number"] = "041099"
        await monitor.async_handle_p2000_match(3154000, [
            SimpleNamespace(units=["042333"], event_time=TS)
        ])
        assert store.clears == []
        assert hass.bus.events == []
        monitor.stop()
    asyncio.run(run())


def test_original_return_clears_only_expected_mapping():
    async def run():
        hass, store = Hass(), Store()
        monitor = ReplacementVehicleMonitor(hass, store, options())
        record = store.active[0]
        dispatch = {
            "incident_id": 3154000, "station_id": 3853,
            "vehicle_number": "042333", "vehicle_function": "TS",
            "event_time": TS,
        }
        monitor._pending[("3154000", 3853, "042333")] = (record, dispatch)
        await monitor.async_handle_p2000_match(3154000, [
            SimpleNamespace(units=["042333"], event_time=TS)
        ])
        # A positive message must not clear until the correlation window closes.
        assert store.clears == []
        await monitor._finalize_pending(("3154000", 3853, "042333"), "TS")
        assert len(store.clears) == 1
        assert store.clears[0]["expected_vehicle_number"] == "041037"
        assert store.clears[0]["expected_start_time"] == START
        assert store.active == []
        assert hass.bus.events[0][0] == "fireservicerota_vehicle_replacement_cleared"
        monitor.stop()
    asyncio.run(run())


def test_mixed_p2000_group_never_clears_original():
    async def run():
        hass, store = Hass(), Store()
        monitor = ReplacementVehicleMonitor(hass, store, options())
        record = store.active[0]
        dispatch = {
            "incident_id": 3154000, "station_id": 3853,
            "vehicle_number": "042333", "vehicle_function": "TS",
            "event_time": TS,
        }
        monitor._pending[("3154000", 3853, "042333")] = (record, dispatch)
        await monitor.async_handle_p2000_match(3154000, [
            SimpleNamespace(units=["042333"], event_time=TS, message="P1 042333"),
            SimpleNamespace(units=["041037"], event_time=TS, message="P1 041037"),
        ])
        assert store.clears == []
        await monitor._finalize_pending(("3154000", 3853, "042333"), "TS")
        assert store.clears == []
        assert store.active
        monitor.stop()
    asyncio.run(run())


def test_p2000_replacement_annotation_never_clears_original():
    async def run():
        hass, store = Hass(), Store()
        monitor = ReplacementVehicleMonitor(hass, store, options())
        record = store.active[0]
        dispatch = {
            "incident_id": 3154000, "station_id": 3853,
            "vehicle_number": "042333", "vehicle_function": "TS",
            "event_time": TS,
        }
        monitor._pending[("3154000", 3853, "042333")] = (record, dispatch)
        await monitor.async_handle_p2000_match(3154000, [
            SimpleNamespace(units=["042333"], event_time=TS,
                            message="042333 vervanging"),
        ])
        assert store.clears == []
        await monitor._finalize_pending(("3154000", 3853, "042333"), "TS")
        assert store.clears == []
        assert store.active
        monitor.stop()
    asyncio.run(run())


def test_late_conflicting_p2000_event_before_window_blocks_clear():
    async def run():
        hass, store = Hass(), Store()
        monitor = ReplacementVehicleMonitor(hass, store, options())
        record = store.active[0]
        dispatch = {
            "incident_id": 3154000, "station_id": 3853,
            "vehicle_number": "042333", "vehicle_function": "TS",
            "event_time": TS,
        }
        key = ("3154000", 3853, "042333")
        monitor._pending[key] = (record, dispatch)
        await monitor.async_handle_p2000_match(3154000, [
            SimpleNamespace(source="page", external_id="a", units=["042333"],
                            event_time=TS, message="P1 042333")
        ])
        # This used to remove the replacement immediately; it must not.
        assert store.clears == []
        await monitor.async_handle_p2000_match(3154000, [
            SimpleNamespace(source="rtl", external_id="b", units=["041037"],
                            event_time=TS, message="P1 041037")
        ])
        await monitor._finalize_pending(key, "TS")
        assert store.clears == []
        assert store.active
        assert hass.bus.events[0][0] == "fireservicerota_vehicle_discrepancy"
        monitor.stop()
    asyncio.run(run())


def test_original_without_correlated_p2000_keeps_replacement_and_warns_once():
    async def run():
        hass, store = Hass(), Store()
        monitor = ReplacementVehicleMonitor(hass, store, options())
        record = store.active[0]
        key = ("3154000", 3853, "042333")
        monitor._pending[key] = (record, {
            "incident_id": 3154000, "station_id": 3853,
            "vehicle_number": "042333", "vehicle_function": "TS",
            "event_time": TS,
        })
        await monitor._finalize_pending(key, "TS")
        assert store.clears == []
        assert store.active
        assert len(hass.services.calls) == 1
        assert hass.bus.events[0][1]["reason"] == "original_unconfirmed"
        await monitor._finalize_pending(key, "TS")
        assert len(hass.services.calls) == 1
        monitor.stop()
    asyncio.run(run())


def test_positive_p2000_with_auto_clear_disabled_only_finishes_observation():
    async def run():
        hass, store = Hass(), Store()
        monitor = ReplacementVehicleMonitor(
            hass, store, options(replacement_auto_clear_enabled=False)
        )
        key = ("3154000", 3853, "042333")
        monitor._pending[key] = (store.active[0], {
            "incident_id": 3154000, "station_id": 3853,
            "vehicle_number": "042333", "vehicle_function": "TS",
            "event_time": TS,
        })
        await monitor.async_handle_p2000_match(3154000, [
            SimpleNamespace(units=["042333"], event_time=TS,
                            message="P1 042333")
        ])
        await monitor._finalize_pending(key, "TS")
        assert store.clears == []
        assert store.active
        assert hass.bus.events == []
        monitor.stop()
    asyncio.run(run())
