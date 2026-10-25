"""Private, bounded, opt-in storage for historical fairness proposal summaries.

No audit text, responses, OAuth credentials or unbounded history is written.
The Home Assistant .storage file is separate from entity attributes / Recorder.
"""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .historical_fairness import MAX_HISTORY_RECORDS


class HistoricalFairnessStorage:
    """Maintain small incident-level history per HA config entry."""

    def __init__(self, hass: Any, entry_id: str) -> None:
        self._store = Store(hass, 1, f"{DOMAIN}.historical_fairness_{entry_id}")
        self._records: dict[str, dict[str, Any]] | None = None
        self._lock = asyncio.Lock()

    async def _load_unlocked(self) -> dict[str, dict[str, Any]]:
        if self._records is None:
            data = await self._store.async_load()
            items = data.get("records", []) if isinstance(data, dict) else []
            self._records = {
                f"{record['station_id']}:{record['incident_id']}": record
                for record in items
                if isinstance(record, dict)
                and record.get("station_id") is not None
                and record.get("incident_id") is not None
            }
        return self._records

    async def async_list(self, station_id: int | str) -> list[dict[str, Any]]:
        """Read one station's retained summaries, newest observation first."""
        async with self._lock:
            records = await self._load_unlocked()
            return sorted(
                (
                    dict(item)
                    for item in records.values()
                    if str(item.get("station_id")) == str(station_id)
                ),
                key=lambda item: str(item.get("latest_proposal_at") or ""),
                reverse=True,
            )

    async def async_upsert(self, record: dict[str, Any]) -> dict[str, int]:
        """Replace one incident, retaining a maximum number of recent records."""
        if not isinstance(record, dict) or not record.get("people"):
            raise ValueError("refusing to persist empty historical fairness evidence")
        async with self._lock:
            records = await self._load_unlocked()
            key = f"{record['station_id']}:{record['incident_id']}"
            replaced = int(key in records)
            existing = records.get(key)
            updated = dict(record)
            if isinstance(existing, dict):
                saved = existing.get("saved_staffing_evidence")
                if (
                    isinstance(saved, dict)
                    and {str(v) for v in saved.get("incident_task_ids") or []}
                    == {str(v) for v in record.get("incident_task_ids") or []}
                ):
                    # A fairness-audit refresh must not silently discard a
                    # separately opted-in, timestamped private API snapshot.
                    updated["saved_staffing_evidence"] = saved
            records[key] = updated
            count_before = len(records)
            newest = sorted(
                records.items(),
                key=lambda item: str(item[1].get("latest_proposal_at") or ""),
                reverse=True,
            )[:MAX_HISTORY_RECORDS]
            self._records = dict(newest)
            await self._store.async_save({"records": list(self._records.values())})
            return {
                "replaced": replaced,
                "evicted": count_before - len(self._records),
                "total_retained": len(self._records),
            }


    async def async_save_staffing_evidence(
        self,
        station_id: int | str,
        incident_id: int | str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        """Attach opt-in numeric staffing evidence to an existing record only.

        The caller must first sanitize and validate the one-time GET evidence.
        Never creates an incident, changes candidate profiles or fetches data.
        """
        if not isinstance(evidence, dict) or evidence.get("version") != 1:
            raise ValueError("invalid private staffing evidence")
        requirements = evidence.get("crew_requirement_evidence")
        if not isinstance(requirements, list) or not requirements:
            raise ValueError("refusing to persist empty skill evidence")
        key = f"{station_id}:{incident_id}"
        async with self._lock:
            records = await self._load_unlocked()
            existing = records.get(key)
            if not isinstance(existing, dict) or not existing.get("people"):
                raise ValueError("cached fairness incident does not exist")
            original_tasks = {
                str(v) for v in existing.get("incident_task_ids") or []
            }
            updated_tasks = {
                str(v) for v in evidence.get("incident_task_ids") or []
            }
            if not original_tasks or original_tasks != updated_tasks:
                raise ValueError("cached incident task IDs do not match")

            updated = dict(existing)
            replaced = isinstance(
                existing.get("saved_staffing_evidence"), dict
            )
            updated["saved_staffing_evidence"] = evidence
            self._records = {**records, key: updated}
            await self._store.async_save({
                "records": list(self._records.values())
            })
            return {
                "saved": True,
                "replaced_previous_evidence": replaced,
                "incident_id": str(incident_id),
                "station_id": str(station_id),
                "stored_requirement_count": len(requirements),
                "checked_at": evidence.get("checked_at"),
            }

    async def async_delete_station(self, station_id: int | str) -> int:
        """Remove all locally stored historical proposal evidence for a station."""
        async with self._lock:
            records = await self._load_unlocked()
            new_records = {
                key: value for key, value in records.items()
                if str(value.get("station_id")) != str(station_id)
            }
            removed = len(records) - len(new_records)
            self._records = new_records
            if removed:
                await self._store.async_save({"records": list(new_records.values())})
            return removed
