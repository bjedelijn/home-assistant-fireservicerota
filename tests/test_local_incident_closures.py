"""Synthetic regression tests for a durable local-only incident closure journal."""
import asyncio
from datetime import datetime, timezone

from custom_components.fireservicerota.incident_store import (
    IncidentStore, OPERATIONAL_STATUS_MANUAL_PENDING,
)
from custom_components.fireservicerota.local_incident_closures import LocalIncidentClosures


class MemoryStorage:
    def __init__(self):
        self.value = None

    async def async_load(self):
        return self.value

    async def async_save(self, content):
        self.value = dict(content)


def test_private_journal_survives_independent_store_instances(monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr(
        "custom_components.fireservicerota.local_incident_closures.Store",
        lambda *_: storage,
    )
    first = LocalIncidentClosures(object(), "entry")
    ended = datetime(2026, 11, 17, 7, 19, tzinfo=timezone.utc).isoformat()
    assert first.record(3081177, ended) is True
    asyncio.run(first.async_save())
    assert storage.value == {"closures": {"3081177": ended}}
    second = LocalIncidentClosures(object(), "entry")
    asyncio.run(second.async_load())
    assert second.get("3081177") == ended
    assert second.get(3081177) == ended
    assert second.forget(3081177) is True
    asyncio.run(second.async_save())
    third = LocalIncidentClosures(object(), "entry")
    asyncio.run(third.async_load())
    assert third.get(3081177) is None


def test_old_rest_incident_remains_manual_closed_even_without_history(monkeypatch):
    ended = datetime(2026, 11, 17, 7, 19, tzinfo=timezone.utc).isoformat()
    journal = LocalIncidentClosures.__new__(LocalIncidentClosures)
    journal._rows = {"3081177": ended}
    instance = IncidentStore.__new__(IncidentStore)
    instance._incidents = {}
    instance._latest_incident_id = None
    instance._last_rest_refresh = {}
    instance._final_refresh_tasks = {}
    instance._fast_refresh_tasks = {}
    instance._local_closures = journal
    monkeypatch.setattr(
        instance, "_compact_snapshot",
        lambda data, previous, source, default_active: {
            "id": data["id"], "incident_active": True,
            "operational_status": "active",
        },
    )
    monkeypatch.setattr(instance, "_notify", lambda: None)
    record = instance.upsert({"id": 3081177}, source="rest")
    assert record["incident_active"] is False
    assert record["operational_status"] == OPERATIONAL_STATUS_MANUAL_PENDING
    assert record["manual_closed_at"] == ended
    assert record["api_closed"] is False


def test_journal_rejects_invalid_ids_and_unverified_end_times():
    journal = LocalIncidentClosures.__new__(LocalIncidentClosures)
    journal._rows = {}
    assert journal.record(True, "2026-11-17T07:19:00+00:00") is False
    assert journal.record("PRIVATE ID", "2026-11-17T07:19:00+00:00") is False
    assert journal.record(3081177, "not a date") is False
    assert journal.record(3081177, "2026-11-17T07:19:00") is False
    assert journal._rows == {}
