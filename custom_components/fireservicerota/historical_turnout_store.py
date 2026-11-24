"""Local historical turnout observations; not proof of physical departure."""
from __future__ import annotations

import asyncio
from collections import Counter
import re
from datetime import datetime, timezone
from typing import Any

from homeassistant.helpers.storage import Store


def _identifier(value: Any) -> str | None:
    if type(value) not in (str, int):
        return None
    value = str(value)
    return value if value.isascii() and value.isdigit() and len(value) <= 24 else None


def normalize_observation(rows: Any) -> list[dict]:
    """Accept normalized response rows only; retain only allowlisted fields, never raw payloads."""
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
        name = row.get("user_name")
        clean["user_name"] = " ".join(name.split())[:256] if isinstance(name, str) and name.strip() else None
        for field in ("status", "reported_status"):
            value = row.get(field)
            clean[field] = value if isinstance(value, str) and value in {
                "acknowledged", "rejected", "expired", "dispatched",
                "shown_up", "no_show", "unknown"
            } else None
        for field in ("arrived_at_station", "on_duty"):
            value = row.get(field)
            clean[field] = value if type(value) is bool else None
        skills = row.get("assigned_skill_ids")
        clean["assigned_skill_ids"] = sorted({v for x in skills if (v := _identifier(x)) is not None}) if isinstance(skills, list) else None
        codes = row.get("assigned_skill_codes")
        clean["assigned_skill_codes"] = {k: v[:80] for k, v in codes.items() if k in (clean["assigned_skill_ids"] or []) and isinstance(v, str)} if isinstance(codes, dict) else {}
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
            if previous:
                def operational(rows):
                    return [{k: v for k, v in row.items() if k not in {"user_name", "assigned_skill_ids", "assigned_skill_codes"}} for row in rows]
                if operational(previous["latest"]["rows"]) == operational(clean):
                    if previous["latest"]["rows"] == clean:
                        return False
                    # Metadata enrichment is not an operational turnout revision.
                    updated = {**self._records, identifier: {**previous,
                        "latest": {**previous["latest"], "rows": clean}}}
                    await self._store.async_save({"records": updated})
                    self._records = updated
                    return True
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

    async def async_restrict(self, allowed_incident_stations: set[tuple[str, str]]) -> int:
        """Remove records outside the current authorized, retained archive scope.

        Caller must establish that authorization and archive loading succeeded.
        Never call with an empty scope merely because a provider request failed.
        """
        allowed = {f"{incident}:{station}" for incident, station in allowed_incident_stations}
        async with self._lock:
            if not self._loaded:
                raise RuntimeError("Turnout store not loaded")
            updated = {key: value for key, value in self._records.items() if key in allowed}
            removed = len(self._records) - len(updated)
            if removed:
                await self._store.async_save({"records": updated})
                self._records = updated
            return removed

    def has_observation(self, incident_id: str, station_id: str) -> bool:
        if not self._loaded:
            raise RuntimeError("Turnout store not loaded")
        return f"{incident_id}:{station_id}" in self._records

    def skill_summary(self) -> dict:
        """Aggregate latest observations, without person or incident identifiers."""
        codes = Counter()
        combinations = Counter()
        by_station = {}
        by_status = {}
        without_skills = unknown = unresolved = 0
        for record in self._records.values():
            for row in record["latest"]["rows"]:
                ids = row.get("assigned_skill_ids")
                if ids is None:
                    unknown += 1
                    continue
                if not ids:
                    without_skills += 1
                    continue
                mapping = row.get("assigned_skill_codes") or {}
                labels = set()
                for skill in ids:
                    label = mapping.get(skill)
                    if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_ /+-]{0,31}", label):
                        unresolved += 1
                        continue
                    labels.add(label)
                if labels:
                    codes.update(labels)
                    combinations.update([" + ".join(sorted(labels))])
                    by_station.setdefault(row["station_id"], Counter()).update(labels)
                    by_status.setdefault(row.get("reported_status") or "unknown", Counter()).update(labels)
        return {"skill_code_counts": dict(codes),
                "skill_combinations": dict(combinations),
                "skill_codes_by_station": {k: dict(v) for k, v in by_station.items()},
                "skill_codes_by_reported_status": {k: dict(v) for k, v in by_status.items()},
                "rows_without_assigned_skills": without_skills,
                "rows_assignment_unknown": unknown,
                "unresolved_skill_references": unresolved,
                "vehicle_role_verified": False}

    def status(self) -> dict:
        """Counts only; no personal identifiers in diagnostics."""
        return {"observed_incidents": len({key.split(":")[0] for key in self._records}),
                "observed_incident_stations": len(self._records),
                "discarded_revisions": sum(r.get("discarded_revisions", 0) for r in self._records.values()),
                "known_empty_incidents": sum(not r["latest"]["rows"] for r in self._records.values()),
                "observed_revisions": sum(len(r["revisions"]) for r in self._records.values()),
                "latest_rows_with_name": sum(bool(row.get("user_name")) for r in self._records.values() for row in r["latest"]["rows"]),
                "latest_response_rows": sum(len(r["latest"]["rows"]) for r in self._records.values()),
                "latest_rows_with_assigned_skills": sum(bool(row.get("assigned_skill_ids")) for r in self._records.values() for row in r["latest"]["rows"]),
                "latest_rows_with_skill_codes": sum(bool(row.get("assigned_skill_codes")) for r in self._records.values() for row in r["latest"]["rows"]),
                "physical_departure_verified": False}
