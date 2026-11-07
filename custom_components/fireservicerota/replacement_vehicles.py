"""Time-scoped mappings from a station's original vehicle to its replacement.

The P2000 event always retains the original dispatched unit from the control room.
Mappings affect local attribution only, never the source feed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

from homeassistant.helpers.storage import Store

_STORAGE_VERSION = 1


def normalize_unit(value: str) -> str:
    """Normalize six-digit callsigns (04-1034 -> 041034)."""
    raw = str(value or "").strip().replace(" ", "").replace("-", "")
    if not re.fullmatch(r"\d{6}", raw):
        raise ValueError("Use a six-digit vehicle number, e.g. 04-1034")
    return raw


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def effective_assignment(records: list[dict], unit: str, at: str) -> dict | None:
    """Return only a unique assignment valid at the P2000 event timestamp."""
    instant = _date(at)
    if instant is None:
        return None
    try:
        number = normalize_unit(unit)
    except ValueError:
        return None
    matches = []
    for record in records:
        if record.get("vehicle_number") != number:
            continue
        start = _date(record.get("start_time"))
        end = _date(record.get("end_time"))
        if start is not None and start <= instant and (end is None or instant < end):
            matches.append(record)
    return matches[0] if len(matches) == 1 else None


class ReplacementVehicleStore:
    """Persist many independent vehicle replacements per station and their history."""

    def __init__(self, hass, entry_id: str):
        self._store = Store(
            hass, _STORAGE_VERSION,
            f"fireservicerota.replacement_vehicles_{entry_id}",
        )
        self._records: list[dict] = []

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self._records = list(data.get("records", [])) if isinstance(data, dict) else []
        # The beta.1 format omitted original_vehicle_number. We cannot infer which
        # vehicle was replaced. End active legacy records rather than wrongly treating
        # a legacy station-wide replacement as a new explicit original mapping.
        migrated = False
        migration_at = datetime.now(timezone.utc).isoformat()
        for record in self._records:
            if "original_vehicle_number" not in record:
                record["original_vehicle_number"] = None
                if not record.get("end_time"):
                    record["end_time"] = migration_at
                    migrated = True
        if migrated:
            await self._store.async_save({"records": self._records})

    @property
    def records(self) -> list[dict]:
        return [dict(record) for record in self._records]

    @property
    def active(self) -> list[dict]:
        return [dict(record) for record in self._records if not record.get("end_time")]

    async def async_set(
        self, *, station_id: int, station_name: str,
        original_vehicle_number: str, vehicle_number: str,
    ) -> dict:
        original = normalize_unit(original_vehicle_number)
        replacement = normalize_unit(vehicle_number)
        if original == replacement:
            raise ValueError("Original and replacement vehicle must be different")
        active = self.active
        if any(
            item["vehicle_number"] == replacement
            and (item["station_id"] != station_id or item.get("original_vehicle_number") != original)
            for item in active
        ):
            raise ValueError("Replacement is already assigned to another vehicle")
        matching = [
            item for item in active
            if item["station_id"] == station_id
            and item.get("original_vehicle_number") == original
        ]
        if len(matching) == 1 and matching[0]["vehicle_number"] == replacement:
            return dict(matching[0])
        now = datetime.now(timezone.utc).isoformat()
        for record in self._records:
            if (
                not record.get("end_time")
                and record["station_id"] == station_id
                and record.get("original_vehicle_number") == original
            ):
                record["end_time"] = now
        new = {
            "station_id": station_id,
            "station_name": station_name,
            "original_vehicle_number": original,
            "vehicle_number": replacement,
            "start_time": now,
            "end_time": None,
        }
        self._records.append(new)
        await self._store.async_save({"records": self._records})
        return dict(new)

    async def async_clear(self, *, station_id: int, original_vehicle_number: str) -> bool:
        original = normalize_unit(original_vehicle_number)
        now = datetime.now(timezone.utc).isoformat()
        changed = False
        for record in self._records:
            if (
                record["station_id"] == station_id
                and record.get("original_vehicle_number") == original
                and not record.get("end_time")
            ):
                record["end_time"] = now
                changed = True
        if changed:
            await self._store.async_save({"records": self._records})
        return changed
