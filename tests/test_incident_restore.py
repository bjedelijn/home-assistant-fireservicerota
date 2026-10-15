from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.fireservicerota.incident_store import IncidentStore


def _iso_utc(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


def test_old_unverified_alerting_snapshot_is_not_restored_active() -> None:
    data = {
        "id": 1001,
        "created_at": _iso_utc(timedelta(days=-21)),
        "state": "alerting",
    }

    assert IncidentStore.should_restore_as_active(data) is False


def test_recent_unverified_alerting_snapshot_can_survive_short_reload() -> None:
    data = {
        "id": 1002,
        "created_at": _iso_utc(timedelta(minutes=-30)),
        "state": "alerting",
    }

    assert IncidentStore.should_restore_as_active(data) is True


def test_explicit_open_lifecycle_wins_even_for_old_snapshot() -> None:
    data = {
        "id": 1003,
        "created_at": _iso_utc(timedelta(days=-2)),
        "state": "active",
    }

    assert IncidentStore.should_restore_as_active(data) is True


def test_explicit_end_time_is_never_restored_active() -> None:
    data = {
        "id": 1004,
        "created_at": _iso_utc(timedelta(minutes=-30)),
        "state": "alerting",
        "end_time": _iso_utc(timedelta(minutes=-5)),
    }

    assert IncidentStore.should_restore_as_active(data) is False
