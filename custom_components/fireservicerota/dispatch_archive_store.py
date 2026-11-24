"""Private, bounded-shape dispatch archive. Never saves raw BWR API payloads.

This store is deliberately separate from the operational 25-record cache and
fairness evidence. Import resumes from a persisted page checkpoint; only validated listing rows enter storage.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from homeassistant.helpers.storage import Store

from .dispatch_archive_analysis import summarize_indexed_incident_months

from .const import (
    CONF_DISPATCH_ARCHIVE_RETENTION,
    CONF_DISPATCH_ARCHIVE_DETAILS,
    CONF_DISPATCH_YEARLY_STATS,
    DISPATCH_RETENTION_OPTIONS,
)

_VERSION = 1
_ALLOWED_EVIDENCE = frozenset({"alerted", "reported_departure", "verified_departure", "unknown"})


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str) or len(value) > 50:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except ValueError:
        return None


def retention_cutoff(now: datetime, years: str) -> datetime | None:
    """UTC calendar-year cutoff, including leap-day handling."""
    if years not in DISPATCH_RETENTION_OPTIONS:
        raise ValueError("Unsupported retention")
    if years == "all":
        return None
    if now.tzinfo is None:
        raise ValueError("Aware date required")
    at = now.astimezone(timezone.utc)
    year = at.year - int(years)
    day = min(at.day, 28) if at.month == 2 else at.day
    return at.replace(year=year, day=day)


def normalize_archive_record(row: Any, *, include_details: bool) -> dict | None:
    """Allowlist only incident metadata, never crew, names or API response."""
    if not isinstance(row, dict):
        return None
    incident_id = row.get("incident_id")
    at = _date(row.get("occurred_at"))
    if not isinstance(incident_id, (str, int)) or isinstance(incident_id, bool):
        return None
    incident_id = str(incident_id)
    if not incident_id.isdecimal() or len(incident_id) > 24 or at is None:
        return None
    result: dict[str, Any] = {
        "incident_id": incident_id,
        "occurred_at": at.isoformat(),
    }
    if not include_details:
        return result
    title = row.get("title")
    if isinstance(title, str) and title.strip():
        result["title"] = title.strip()[:200]
    station = row.get("station_key")
    if isinstance(station, str) and 0 < len(station) <= 100:
        result["station_key"] = station
    priority = row.get("priority")
    if type(priority) is int and priority in {1, 2}:
        result["priority"] = priority
    for field in ("vehicle_keys", "specialisms"):
        values = row.get(field)
        if isinstance(values, list):
            result[field] = sorted({
                value.strip() for value in values
                if isinstance(value, str) and 0 < len(value.strip()) <= 50
            })[:40]
    evidence = row.get("evidence")
    if isinstance(evidence, str) and evidence in _ALLOWED_EVIDENCE:
        result["evidence"] = evidence
    return result


def prune_archive_records(
    records: list[dict], *, now: datetime, retention: str, include_details: bool
) -> list[dict]:
    """Deduplicate and apply retention without touching yearly aggregates."""
    cutoff = retention_cutoff(now, retention)
    output: dict[str, dict] = {}
    for record in records:
        normalized = normalize_archive_record(record, include_details=include_details)
        if normalized is None:
            continue
        if cutoff and _date(normalized["occurred_at"]) < cutoff:
            continue
        output[normalized["incident_id"]] = normalized
    return sorted(output.values(), key=lambda item: item["occurred_at"], reverse=True)


class DispatchArchiveStore:
    """Private HA storage for incident metadata and separate annual counts."""

    def __init__(self, hass, entry_id: str):
        self._store = Store(hass, _VERSION, f"fireservicerota.dispatch_archive_{entry_id}")
        self._lock = asyncio.Lock()
        self._records: list[dict] = []
        self._yearly: list[dict] = []
        self._loaded = False
        self._import = {"status": "not_started", "next_page": 1, "pages_processed": 0, "rows_seen": 0}

    async def async_load(self, options: dict) -> None:
        async with self._lock:
            data = await self._store.async_load()
            if not isinstance(data, dict):
                data = {}
            self._records = list(data.get("records", []))
            self._yearly = list(data.get("yearly", []))
            state = data.get("import")
            if isinstance(state, dict):
                self._import = {
                    "status": "interrupted" if state.get("status") == "running" else state.get("status", "not_started"),
                    "next_page": max(1, min(int(state.get("next_page", 1)), 5000)),
                    "pages_processed": max(0, int(state.get("pages_processed", 0))),
                    "rows_seen": max(0, int(state.get("rows_seen", 0))),
                }
            self._loaded = True
            await self._apply_options_locked(options)

    async def _apply_options_locked(self, options: dict) -> None:
        if not self._loaded:
            raise RuntimeError("Archive must be loaded first")
        retention = options.get(CONF_DISPATCH_ARCHIVE_RETENTION, "all")
        details = bool(options.get(CONF_DISPATCH_ARCHIVE_DETAILS, True))
        keep_stats = bool(options.get(CONF_DISPATCH_YEARLY_STATS, True))
        self._records = prune_archive_records(
            self._records, now=datetime.now(timezone.utc),
            retention=retention, include_details=details,
        )
        if not keep_stats:
            self._yearly = []
        await self._save_locked()

    async def async_apply_options(self, options: dict) -> None:
        async with self._lock:
            await self._apply_options_locked(options)

    async def async_upsert(self, records: list[dict], options: dict) -> int:
        """For future validated ingestion only; not called by current probe."""
        async with self._lock:
            if not self._loaded:
                raise RuntimeError("Archive must be loaded first")
            previous = {row["incident_id"]: row for row in self._records}
            new_records = dict(previous)
            for row in records:
                normalized = normalize_archive_record(
                    row,
                    include_details=bool(options.get(CONF_DISPATCH_ARCHIVE_DETAILS, True)),
                )
                if normalized:
                    new_records[normalized["incident_id"]] = normalized
            self._records = prune_archive_records(
                list(new_records.values()), now=datetime.now(timezone.utc),
                retention=options.get(CONF_DISPATCH_ARCHIVE_RETENTION, "all"),
                include_details=bool(options.get(CONF_DISPATCH_ARCHIVE_DETAILS, True)),
            )
            await self._save_locked()
            return len(set(item["incident_id"] for item in self._records) - previous.keys())

    async def async_update_import(self, status: str, *, reset: bool = False) -> None:
        """Persist a sanitized, non-sensitive import state transition."""
        if status not in {"running", "interrupted", "failed", "complete", "not_started"}:
            raise ValueError("Invalid import state")
        async with self._lock:
            if reset:
                self._import = {"status": "not_started", "next_page": 1, "pages_processed": 0, "rows_seen": 0}
            self._import["status"] = status
            await self._save_locked()

    async def async_commit_listing_page(self, records: list[dict], options: dict, *, page: int) -> None:
        """Atomically store one validated listing page and advance checkpoint."""
        if not 1 <= page <= 5000 or len(records) > 25:
            raise ValueError("Invalid listing page")
        async with self._lock:
            if self._import["next_page"] != page:
                raise ValueError("Unexpected import checkpoint")
            previous = {item["incident_id"]: item for item in self._records}
            include_details = bool(options.get(CONF_DISPATCH_ARCHIVE_DETAILS, True))
            for row in records:
                cleaned = normalize_archive_record(row, include_details=include_details)
                if cleaned is None:
                    raise ValueError("Unrecognized incident in listing page")
                previous[cleaned["incident_id"]] = cleaned
            self._records = prune_archive_records(
                list(previous.values()),
                now=datetime.now(timezone.utc),
                retention=options.get(CONF_DISPATCH_ARCHIVE_RETENTION, "all"),
                include_details=include_details,
            )
            self._import["next_page"] = page + 1
            self._import["pages_processed"] += 1
            self._import["rows_seen"] += len(records)
            self._import["status"] = "running"
            await self._save_locked()

    @property
    def import_next_page(self) -> int:
        return self._import["next_page"]

    @property
    def import_status(self) -> str:
        return self._import["status"]

    async def _save_locked(self) -> None:
        await self._store.async_save({
            "records": self._records,
            "yearly": self._yearly,
            "import": self._import,
        })

    async def async_detail_probe_ids(self, limit: int, offset: int = 0) -> list[str]:
        """Select local IDs only; never return them from a HA service.

        Spread samples over the indexed range instead of always selecting
        the latest records. No remote requests are performed here.
        """
        if type(limit) is not int or not 1 <= limit <= 3:
            raise ValueError("Probe limit must be between one and three")
        async with self._lock:
            if type(offset) is not int or offset < 0:
                raise ValueError("Invalid probe offset")
            records = self._records[offset:]
            total = len(records)
            if total == 0:
                return []
            positions = (
                [0] if limit == 1
                else [0, total - 1] if limit == 2
                else [0, (total - 1) // 2, total - 1]
            )
            return list(dict.fromkeys(
                records[position]["incident_id"]
                for position in positions
            ))

    async def async_index_summary(self, timezone_name: str) -> dict[str, Any]:
        """Analyze private archived metadata without BWR/network calls."""
        async with self._lock:
            return summarize_indexed_incident_months(
                self._records,
                timezone_name=timezone_name,
                listing_exhausted=self._import["status"] == "complete",
            )

    def status(self) -> dict[str, Any]:
        """Return only counts and dates; no operational identifiers."""
        return {
            "stored_incidents": len(self._records),
            "stored_yearly_series": len(self._yearly),
            "oldest_incident_date": (
                self._records[-1]["occurred_at"][:10] if self._records else None
            ),
            "newest_incident_date": (
                self._records[0]["occurred_at"][:10] if self._records else None
            ),
            "historical_import_implemented": True,
            "historical_import_status": self._import["status"],
            "next_page": self._import["next_page"],
            "pages_processed": self._import["pages_processed"],
            "rows_seen": self._import["rows_seen"],
        }
