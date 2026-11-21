"""Guarded reconciliation of *verified live* BWR vehicle dispatches.

BWR task names and P2000 callsigns alone never change a replacement.
The actual BWR vehicle assignment field must be verified before activation.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any

from .replacement_vehicles import normalize_unit, normalize_vehicle_function
from .replacement_reconciliation import evaluate_replacement
from .replacement_notifications import async_send_discrepancy


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def live_vehicle_assignments(incident: Any, *, now: datetime | None = None) -> list[dict]:
    """Only explicit, confirmed BWR vehicle dispatch records.

    This is intentionally not a heuristic for resolved_tasks, staffing or a
    six-digit number found in a narrative. An unrecognized BWR schema yields [].
    """
    if not isinstance(incident, dict) or incident.get("trigger") not in {"new", "update"}:
        return []
    if incident.get("id") is None:
        return []
    instant = _utc(incident.get("created_at"))
    current = now or datetime.now(timezone.utc)
    if instant is None or not (-30 <= (current - instant).total_seconds() <= 180):
        return []
    raw = incident.get("dispatched_vehicles")
    if not isinstance(raw, list):
        return []
    results = []
    for item in raw[:40]:
        if not isinstance(item, dict) or item.get("confirmed") is not True:
            continue
        try:
            station_id = int(item["station_id"])
            unit = normalize_unit(item["vehicle_number"])
            role = normalize_vehicle_function(item["vehicle_function"])
        except (ValueError, TypeError, KeyError):
            continue
        if not role or station_id <= 0:
            continue
        results.append({
            "station_id": station_id,
            "vehicle_number": unit,
            "vehicle_function": role,
            "event_time": incident["created_at"],
            "incident_id": incident["id"],
        })
    return results


class ReplacementVehicleMonitor:
    """Per integration-entry reconciliation; no output without verified records."""

    def __init__(self, hass, store, options: dict):
        self._hass = hass
        self._store = store
        self._options = dict(options)
        self._pending: dict[tuple[str, int, str], tuple[dict, dict]] = {}
        self._pending_tasks: dict[tuple[str, int, str], asyncio.Task] = {}
        self._seen: set[tuple[str, int, str, str]] = set()
        self._order: deque[tuple[str, int, str, str]] = deque(maxlen=500)
        self._closed = False

    def stop(self) -> None:
        self._closed = True
        self._pending.clear()
        for task in self._pending_tasks.values():
            task.cancel()
        self._pending_tasks.clear()

    def _mark_once(self, key: tuple[str, int, str, str]) -> bool:
        if key in self._seen:
            return False
        if len(self._order) == self._order.maxlen:
            self._seen.discard(self._order.popleft())
        self._seen.add(key)
        self._order.append(key)
        return True

    async def _emit_notification(self, decision: dict, role: str) -> None:
        if self._closed or not self._options.get("replacement_alerts_enabled", False):
            return
        key = (
            str(decision["incident_id"]), int(decision["station_id"]),
            str(decision["original_vehicle_number"]), str(decision["reason"]),
        )
        if not self._mark_once(key):
            return
        self._hass.bus.async_fire("fireservicerota_vehicle_discrepancy", {
            **decision, "vehicle_function": role, "silent": True,
        })
        await async_send_discrepancy(self._hass, self._options, decision, function=role)

    async def async_handle_live(self, incident: dict) -> None:
        """Observe BWR websocket events, not restored or polled incident history."""
        if self._closed:
            return
        for dispatch in live_vehicle_assignments(incident):
            station_id = dispatch["station_id"]
            role = dispatch["vehicle_function"]
            matching = [
                r for r in self._store.active
                if r.get("station_id") == station_id
                and r.get("vehicle_function") == role
            ]
            # A station can have multiple vehicles of the same function. Do
            # not guess which replacement a dispatch refers to.
            if len(matching) != 1:
                continue
            record = matching[0]
            decision = evaluate_replacement(
                record, bwr_station_id=station_id,
                bwr_vehicle_number=dispatch["vehicle_number"],
                bwr_event_time=dispatch["event_time"],
                bwr_incident_id=dispatch["incident_id"],
                bwr_verified_live=True,
            )
            decision["station_name"] = record.get("station_name")
            key = (
                str(dispatch["incident_id"]), station_id,
                str(record["original_vehicle_number"]),
            )
            if decision["reason"] == "third_vehicle":
                await self._emit_notification(decision, role)
            elif decision["reason"] == "original_unconfirmed":
                if key not in self._pending:
                    self._pending[key] = (record, dispatch)
                    task = self._hass.async_create_task(self._check_later(key, role))
                    self._pending_tasks[key] = task

    async def _check_later(self, key: tuple[str, int, str], role: str) -> None:
        await asyncio.sleep(120)
        if self._closed:
            return
        self._pending_tasks.pop(key, None)
        pending = self._pending.pop(key, None)
        if pending is None:
            return
        record, dispatch = pending
        if not self._still_active(record):
            return
        # No confirmed matching P2000 within the window: notify, do not clear.
        decision = evaluate_replacement(
            record, bwr_station_id=dispatch["station_id"],
            bwr_vehicle_number=dispatch["vehicle_number"],
            bwr_event_time=dispatch["event_time"],
            bwr_incident_id=dispatch["incident_id"],
            bwr_verified_live=True,
        )
        decision["station_name"] = record.get("station_name")
        await self._emit_notification(decision, role)

    def _still_active(self, record: dict) -> bool:
        """Reject evidence for a manually changed or already cleared replacement."""
        return any(
            item.get("station_id") == record.get("station_id")
            and item.get("original_vehicle_number") == record.get("original_vehicle_number")
            and item.get("vehicle_number") == record.get("vehicle_number")
            and item.get("start_time") == record.get("start_time")
            for item in self._store.active
        )

    async def async_handle_p2000_match(self, incident_id: Any, events: list[Any]) -> None:
        """React only to P2000 events the existing incident matcher attached."""
        if self._closed:
            return
        for key, (record, dispatch) in list(self._pending.items()):
            if str(incident_id) != key[0] or not self._still_active(record):
                continue
            for event in events:
                decision = evaluate_replacement(
                    record,
                    bwr_station_id=dispatch["station_id"],
                    bwr_vehicle_number=dispatch["vehicle_number"],
                    bwr_event_time=dispatch["event_time"],
                    bwr_incident_id=dispatch["incident_id"],
                    bwr_verified_live=True,
                    p2000_vehicle_numbers=getattr(event, "units", []),
                    p2000_event_time=getattr(event, "event_time", None),
                    p2000_correlated=True,
                )
                if decision["action"] != "clear":
                    continue
                self._pending.pop(key, None)
                timer = self._pending_tasks.pop(key, None)
                if timer is not None:
                    timer.cancel()
                if self._options.get("replacement_auto_clear_enabled", False):
                    changed = await self._store.async_clear(
                        station_id=dispatch["station_id"],
                        original_vehicle_number=record["original_vehicle_number"],
                        end_reason="bwr_p2000_confirmed_return",
                        end_incident_id=dispatch["incident_id"],
                        expected_vehicle_number=record["vehicle_number"],
                        expected_start_time=record["start_time"],
                    )
                    if not changed:
                        return
                    self._hass.bus.async_fire("fireservicerota_vehicle_replacement_cleared", {
                        "station_id": dispatch["station_id"],
                        "original_vehicle_number": record["original_vehicle_number"],
                        "replacement_vehicle_number": record["vehicle_number"],
                        "incident_id": dispatch["incident_id"],
                        "source": "bwr_p2000",
                    })
                return
