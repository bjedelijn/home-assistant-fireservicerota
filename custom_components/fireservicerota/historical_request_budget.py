"""Shared conservative budget for optional historical BWR requests.

Only calls explicitly routed through this gate are covered; operational
polling, websocket and other clients are outside its scope. This is a
self-imposed safety ceiling, NOT a known provider rate-limit.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import monotonic

from homeassistant.helpers.storage import Store

HISTORICAL_REQUESTS_PER_UTC_DAY = 40
HISTORICAL_MIN_REQUEST_INTERVAL_SECONDS = 2.0


class HistoricalRequestBudgetExceeded(Exception):
    """The local historical-request allowance has been exhausted."""


class HistoricalRequestBudget:
    """Persist attempts ahead of remote requests; no automatic retry."""

    def __init__(self, hass, entry_id: str) -> None:
        self._store = Store(hass, 1, f"fireservicerota.history_request_budget_{entry_id}")
        self._lock = asyncio.Lock()
        self._date = ""
        self._used = 0
        self._last_attempt_monotonic: float | None = None

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if isinstance(data, dict):
            date = data.get("utc_date")
            count = data.get("attempts", 0)
            self._date = date if isinstance(date, str) else ""
            self._used = (
                max(0, min(count, HISTORICAL_REQUESTS_PER_UTC_DAY))
                if type(count) is int else 0
            )
        self._rollover()

    def _rollover(self) -> None:
        date = datetime.now(timezone.utc).date().isoformat()
        if self._date != date:
            self._date = date
            self._used = 0

    def status(self) -> dict:
        self._rollover()
        return {
            "historical_budget_utc_date": self._date,
            "historical_attempts_used": self._used,
            "historical_attempts_remaining": max(
                0, HISTORICAL_REQUESTS_PER_UTC_DAY - self._used
            ),
            "historical_daily_attempt_cap": HISTORICAL_REQUESTS_PER_UTC_DAY,
            "historical_min_gap_seconds": HISTORICAL_MIN_REQUEST_INTERVAL_SECONDS,
            "provider_quota_known": False,
            "coverage": "archive_import_and_listing_probe_only",
        }

    async def async_get(self, client, endpoint: str, params: dict):
        """Reserve before sending; rate-limit shared historical calls per entry."""
        async with self._lock:
            self._rollover()
            if self._used >= HISTORICAL_REQUESTS_PER_UTC_DAY:
                raise HistoricalRequestBudgetExceeded()
            if self._last_attempt_monotonic is not None:
                remaining = (
                    HISTORICAL_MIN_REQUEST_INTERVAL_SECONDS
                    - (monotonic() - self._last_attempt_monotonic)
                )
                if remaining > 0:
                    await asyncio.sleep(remaining)
            # Save the attempt before network I/O; a crash cannot reset
            # an in-flight request's consumed budget.
            self._used += 1
            await self._store.async_save({
                "utc_date": self._date,
                "attempts": self._used,
            })
            self._last_attempt_monotonic = monotonic()
            return await client.async_api_get(endpoint, params)
