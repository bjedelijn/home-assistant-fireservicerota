"""Persist local, time-scoped replacement-vehicle assignments.

Do not modify raw P2000 messages or Brandbase registry records.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

from homeassistant.helpers.storage import Store

_STORAGE_VERSION = 1
_UNIT_PATTERN = re.compile(r"^(?:0?4[- ]?)?(\d{6})$")


def normalize_unit(value: str) -> str:
    """Normalize a Dutch six-digit radio callsign (04-1034 -> 041034)."""
    raw = str(value or "").strip().replace(" ", "").replace("-", "")
    if not re.fullmatch(r"\d{6}", raw):
        raise ValueError("Use a six-digit vehicle number, e.g. 04-1034")
    return raw


def _date(value: str) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def effective_assignment(records: list[dict], unit: str, at: str) -> dict | None:
    """Return the unique replacement assignment at an event's actual time."""
    instant = _date(at)
    if instant is None:
        return None
    try:
        normalized = normalize_unit(unit)
    except ValueError:
        return None
    matches = []
    for record in records:
        if record.get("vehicle_number") != normalized:
            continue
        start = _date(record.get("start_time"))
        end = _date(record.get("end_time")) if record.get("end_time") else None
        if start and start <= instant and (end is None or instant < end):
            matches.append(record)
    return matches[0] if len(matches) == 1 else None


class ReplacementVehicleStore:
    """Keep replacement history so old incidents keep their original attribution."""

    def __init__(self, hass, entry_id: str):
        self._store = Store(hass, _STORAGE_VERSION, f"fireservicerota.replacement_vehicles_{entry_id}")
        self._records: list[dict] = []

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self._records = list(data.get("records", [])) if isinstance(data, dict) else []

    @property
    def records(self) -> list[dict]:
        return [dict(record) for record in self._records]

    @property
    def active(self) -> list[dict]:
        return [dict(record) for record in self._records if not record.get("end_time")]

    async def async_set(self, *, station_id: int, station_name: str, vehicle_number: str) -> dict:
        number = normalize_unit(vehicle_number)
        active = self.active
        if any(
            record["vehicle_number"] == number and record["station_id"] != station_id
            for record in active
        ):
            raise ValueError("This replacement vehicle is already assigned to another station")
        matching = [r for r in active if r["station_id"] == station_id]
        if len(matching) == 1 and matching[0]["vehicle_number"] == number:
            return dict(matching[0])
        timestamp = datetime.now(timezone.utc).isoformat()
        for record in self._records:
            if not record.get("end_time") and record["station_id"] == station_id:
                record["end_time"] = timestamp
        record = {
            "station_id": station_id,
            "station_name": station_name,
            "vehicle_number": number,
            "start_time": timestamp,
            "end_time": None,
        }
        self._records.append(record)
        await self._store.async_save({"records": self._records})
        return dict(record)

    async def async_clear(self, station_id: int) -> bool:
        changed = False
        timestamp = datetime.now(timezone.utc).isoformat()
        for record in self._records:
            if record["station_id"] == station_id and not record.get("end_time"):
                record["end_time"] = timestamp
                changed = True
        if changed:
            await self._store.async_save({"records": self._records})
        return changed
