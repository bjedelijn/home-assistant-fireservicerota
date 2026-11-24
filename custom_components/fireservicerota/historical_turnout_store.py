"""Local historical turnout observations; not proof of physical departure."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from homeassistant.helpers.storage import Store


def _identifier(value: Any) -> str | None:
    if type(value) not in (str, int):
        return None
    value = str(value)
    return value if value.isascii() and value.isdigit() and len(value) <= 24 else None


def normalize_observation(rows: Any) -> list[dict]:
    """Accept normalized response rows only; never persist names or raw payloads."""
    if not isinstance(rows, list):
        raise ValueError("Expected response list")
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid response row")
        membership = _identifier(row.get("membership_id"))
        station = _identifier(row.get("station_id"))
        if membership is None or station is None:
            raise ValueError("Unresolved membership or station")
        key = (station, membership)
        if key in seen:
            raise ValueError("Ambiguous membership")
        seen.add(key)
        clean = {"membership_id": membership, "station_id": station,
                 "user_id": _identifier(row.get("user_id"))}
        for field in ("status", "reported_status"):
            value = row.get(field)
            clean[field] = value if isinstance(value, str) and value in {
                "acknowledged", "rejected", "expired", "dispatched",
                "shown_up", "no_show", "unknown"
            } else None
        for field in ("arrived_at_station", "on_duty"):
            value = row.get(field)
            clean[field] = value if type(value) is bool else None
        result.append(clean)
    return sorted(result, key=lambda row: (row["station_id"], row["membership_id"]))


class HistoricalTurnoutStore:
    """Connection-scoped observations with immutable first and latest snapshots."""

    def __init__(self, hass, entry_id: str):
        self._store = Store(hass, 1, f"fireservicerota.historical_turnout_{entry_id}")
        self._lock = asyncio.Lock()
        self._records = {}
        self._loaded = False

    async def async_load(self) -> None:
        async with self._lock:
            if self._loaded:
                return
            data = await self._store.async_load()
            self._records = data.get("records", {}) if isinstance(data, dict) else {}
            if not isinstance(self._records, dict):
                raise ValueError("Invalid historical turnout store")
            self._loaded = True

    async def async_observe(self, incident_id: Any, rows: Any, *, station_id: Any) -> bool:
        """Record a validated complete observation, including a known empty list.

        Caller must verify incident identity, completeness and authorized scope.
        A changed snapshot is an observed difference, not proof of manual correction.
        """
        identifier = _identifier(incident_id)
        if identifier is None:
            raise ValueError("Invalid incident ID")
        station = _identifier(station_id)
        if station is None:
            raise ValueError("Invalid station scope")
        clean = normalize_observation(rows)
        if any(row["station_id"] != station for row in clean):
            raise ValueError("Response outside station scope")
        identifier = f"{identifier}:{station}"
        async with self._lock:
            if not self._loaded:
                raise RuntimeError("Turnout store not loaded")
            previous = self._records.get(identifier)
            if previous and previous["latest"]["rows"] == clean:
                return False
            snapshot = {"observed_at": datetime.now(timezone.utc).isoformat(),
                        "rows": clean}
            if previous:
                record = {"first": previous["first"], "latest": snapshot,
                          "revisions": [*previous["revisions"], snapshot][-100:],
                          "discarded_revisions": previous.get("discarded_revisions", 0) + int(len(previous["revisions"]) >= 100)}
            else:
                record = {"first": snapshot, "latest": snapshot, "revisions": [], "discarded_revisions": 0}
            updated = {**self._records, identifier: record}
            await self._store.async_save({"records": updated})
            self._records = updated
            return True

    def status(self) -> dict:
        """Counts only; no personal identifiers in diagnostics."""
        return {"observed_incidents": len({key.split(":")[0] for key in self._records}),
                "observed_incident_stations": len(self._records),
                "discarded_revisions": sum(r.get("discarded_revisions", 0) for r in self._records.values()),
                "known_empty_incidents": sum(not r["latest"]["rows"] for r in self._records.values()),
                "observed_revisions": sum(len(r["revisions"]) for r in self._records.values()),
                "physical_departure_verified": False}
