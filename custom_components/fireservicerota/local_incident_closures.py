"""Durable local overrides for manually closed incidents, never provider writes."""
from __future__ import annotations

from datetime import datetime
from homeassistant.helpers.storage import Store

LIMIT = 1000


def _key(value):
    if isinstance(value, bool):
        return None
    value = str(value)
    return value if value.isascii() and value.isdecimal() and 1 <= len(value) <= 32 else None


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.isoformat() if parsed.tzinfo is not None else None


class LocalIncidentClosures:
    """Store only IDs and closure timestamps privately in Home Assistant."""

    def __init__(self, hass, entry_id):
        self._store = Store(hass, 1, f"fireservicerota.manual_closures_{entry_id}")
        self._rows = {}

    async def async_load(self):
        data = await self._store.async_load()
        raw = data.get("closures") if isinstance(data, dict) else None
        if isinstance(raw, dict):
            for item, when in list(raw.items())[:LIMIT]:
                key, timestamp = _key(item), _timestamp(when)
                if key is not None and timestamp is not None:
                    self._rows[key] = timestamp

    def get(self, incident_id):
        key = _key(incident_id)
        return self._rows.get(key) if key is not None else None

    def record(self, incident_id, when):
        key, timestamp = _key(incident_id), _timestamp(when)
        if key is None or timestamp is None:
            return False
        if key not in self._rows and len(self._rows) >= LIMIT:
            raise ValueError("Local incident closure limit reached")
        changed = self._rows.get(key) != timestamp
        self._rows[key] = timestamp
        return changed

    def forget(self, incident_id):
        key = _key(incident_id)
        return self._rows.pop(key, None) is not None if key is not None else False

    async def async_save(self):
        await self._store.async_save({"closures": dict(self._rows)})
