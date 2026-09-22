"""Coordinate optional P2000 enrichment for Dutch incidents."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import math
import re
from typing import Any

from .model import P2000Event
from .online import P2000OnlineProvider

_LOGGER = logging.getLogger(__name__)

_MATCH_RADIUS_METERS = 1500
_MATCH_WINDOW_BEFORE = timedelta(minutes=15)
_MATCH_WINDOW_AFTER = timedelta(hours=3)
_BUFFER_RETENTION = timedelta(minutes=60)
_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "brandweer", "melding", "prio", "p", "br", "bon", "naar", "voor", "met",
    "aan", "de", "het", "een", "bij", "in", "op", "van", "en", "te",
}


class P2000EnrichmentManager:
    """Continuously buffer P2000 alerts and enrich BrandweerRooster incidents."""

    def __init__(self, hass, incident_store, *, scan_interval: int = 30) -> None:
        self._hass = hass
        self._incident_store = incident_store
        self._scan_interval = max(30, int(scan_interval))
        self._providers = [P2000OnlineProvider(hass)]
        self._task: asyncio.Task | None = None
        self._first_received: dict[str, str] = {}
        self._buffer: dict[str, P2000Event] = {}
        self._listeners: list[Callable[[], None]] = []
        self._stopping = False
        self._last_poll_at: str | None = None
        self._last_poll_success: bool | None = None
        self._last_poll_result_count = 0

    @property
    def scan_interval(self) -> int:
        """Return the configured online polling interval."""
        return self._scan_interval

    @property
    def buffer_retention_minutes(self) -> int:
        """Return P2000 ring-buffer retention in minutes."""
        return int(_BUFFER_RETENTION.total_seconds() // 60)

    @property
    def buffer_size(self) -> int:
        """Return the number of unique recent P2000 messages in memory."""
        return len(self._buffer)

    @property
    def last_event(self) -> dict[str, Any] | None:
        """Return the newest buffered P2000 event."""
        if not self._buffer:
            return None
        event = max(
            self._buffer.values(),
            key=lambda item: self._event_timestamp(item).timestamp(),
        )
        return event.as_dict()

    @property
    def status(self) -> dict[str, Any]:
        """Return compact diagnostics without exposing the full ring buffer."""
        providers = {}
        for provider in self._providers:
            providers[provider.source] = {
                "last_poll_at": provider.last_poll_at,
                "last_poll_success": provider.last_poll_success,
                "last_error": provider.last_error,
                "last_result_count": provider.last_result_count,
            }
        return {
            "enabled": True,
            "sources": [provider.source for provider in self._providers],
            "scan_interval_seconds": self._scan_interval,
            "buffer_retention_minutes": self.buffer_retention_minutes,
            "buffered_events": self.buffer_size,
            "last_poll_at": self._last_poll_at,
            "last_poll_success": self._last_poll_success,
            "last_poll_result_count": self._last_poll_result_count,
            "last_event": self.last_event,
            "providers": providers,
        }

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a status listener and return an unsubscribe callback."""
        self._listeners.append(listener)

        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    def _notify(self) -> None:
        """Notify P2000 status entities after a poll/buffer update."""
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.exception("P2000 status listener failed")

    async def async_start(self) -> None:
        """Start continuous P2000 reception while enrichment is enabled."""
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = self._hass.async_create_task(self._run())

    async def async_stop(self) -> None:
        """Stop the enrichment loop."""
        self._stopping = True
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        """Continuously poll P2000 so alerts preceding BWR are retained."""
        try:
            while not self._stopping:
                await self._async_poll_once()
                await asyncio.sleep(self._scan_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Unexpected error in P2000 enrichment loop")

    async def _async_poll_once(self) -> None:
        """Fetch providers, update the ring buffer, then correlate active incidents."""
        events: list[P2000Event] = []
        provider_results: list[bool] = []

        for provider in self._providers:
            try:
                fetched = await provider.async_fetch()
            except Exception:
                _LOGGER.exception("P2000 provider %s failed", provider.source)
                provider_results.append(False)
                continue

            provider_results.append(provider.last_poll_success is not False)
            for event in fetched:
                key = self._event_key(event)
                first = self._first_received.setdefault(key, event.received_at)
                event.received_at = first
                self._buffer[key] = event
                events.append(event)

        self._prune_buffer()
        self._last_poll_at = datetime.now().astimezone().isoformat()
        self._last_poll_success = bool(provider_results) and all(provider_results)
        self._last_poll_result_count = len(events)

        # Correlate against the complete recent buffer, not only this poll.
        # This is what lets a P2000 alert arrive before BrandweerRooster.
        buffered = list(self._buffer.values())
        for incident in self._incident_store.active_incidents:
            incident_id = incident.get("id")
            if incident_id is None:
                continue

            matched = [event for event in buffered if self._matches(incident, event)]
            if not matched:
                continue

            enrichment = self._build_enrichment(matched)
            existing = incident.get("p2000_enrichment")
            if self._same_enrichment(existing, enrichment):
                continue
            self._incident_store.apply_p2000_enrichment(incident_id, enrichment)

        self._notify()

    def _prune_buffer(self) -> None:
        """Drop P2000 events older than the configured rolling retention."""
        cutoff = datetime.now().astimezone() - _BUFFER_RETENTION
        expired = [
            key
            for key, event in self._buffer.items()
            if self._event_timestamp(event) < cutoff
        ]
        for key in expired:
            self._buffer.pop(key, None)
            self._first_received.pop(key, None)

    @classmethod
    def _event_timestamp(cls, event: P2000Event) -> datetime:
        """Return the best timestamp for ring-buffer age and ordering."""
        parsed = cls._parse_datetime(event.event_time)
        if parsed is not None:
            return parsed
        parsed = cls._parse_datetime(event.received_at)
        if parsed is not None:
            return parsed
        return datetime.now().astimezone()

    @staticmethod
    def _event_key(event: P2000Event) -> str:
        return event.external_id or f"{event.event_time}|{event.message}"

    @staticmethod
    def _same_enrichment(existing: Any, new: dict[str, Any]) -> bool:
        """Ignore last_updated when deciding whether incident data changed."""
        if not isinstance(existing, dict):
            return False
        old_compare = dict(existing)
        new_compare = dict(new)
        old_compare.pop("last_updated", None)
        new_compare.pop("last_updated", None)
        return old_compare == new_compare

    @classmethod
    def _matches(cls, incident: dict[str, Any], event: P2000Event) -> bool:
        if not cls._time_matches(incident, event):
            return False

        incident_lat = cls._as_float(incident.get("latitude"))
        incident_lon = cls._as_float(incident.get("longitude"))
        if incident_lat is not None and incident_lon is not None:
            if event.latitude is not None and event.longitude is not None:
                return cls._distance_meters(
                    incident_lat, incident_lon, event.latitude, event.longitude
                ) <= _MATCH_RADIUS_METERS

        incident_text = " ".join(
            str(value or "")
            for value in (
                incident.get("body"),
                incident.get("formatted_address"),
                (incident.get("address") or {}).get("formatted_address")
                if isinstance(incident.get("address"), dict)
                else "",
            )
        )
        event_text = " ".join(
            x for x in (event.message, event.human_message, event.street, event.city) if x
        )
        left = cls._tokens(incident_text)
        right = cls._tokens(event_text)
        common = left & right

        # A street/city match is stronger than generic incident wording.
        explicit = cls._tokens(" ".join(x for x in (event.street, event.city) if x))
        if explicit and left & explicit:
            return True
        return len(common) >= 2

    @staticmethod
    def _time_matches(incident: dict[str, Any], event: P2000Event) -> bool:
        if not event.event_time:
            return True
        start = P2000EnrichmentManager._parse_datetime(
            incident.get("start_time") or incident.get("created_at")
        )
        event_time = P2000EnrichmentManager._parse_datetime(event.event_time)
        if start is None or event_time is None:
            return True
        return start - _MATCH_WINDOW_BEFORE <= event_time <= start + _MATCH_WINDOW_AFTER

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in _WORD_RE.findall(text)
            if len(token) >= 3 and token.lower() not in _STOPWORDS and not token.isdigit()
        }

    @staticmethod
    def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371000.0
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _build_enrichment(events: list[P2000Event]) -> dict[str, Any]:
        ordered = sorted(events, key=P2000EnrichmentManager._event_timestamp)
        units = sorted({unit for event in ordered for unit in event.units})
        capcodes: dict[str, str | None] = {}
        for event in ordered:
            for item in event.capcodes:
                code = str(item.get("capcode") or "").strip()
                if not code:
                    continue
                description = str(item.get("omschrijving") or "").strip() or None
                capcodes.setdefault(code, description)

        messages = [event.as_dict() for event in ordered[:20]]
        escalation_words = ("middel br", "grote br", "zeer grote br", "grip")
        escalation_detected = len(ordered) > 1 or any(
            any(word in event.message.lower() for word in escalation_words)
            for event in ordered
        )
        return {
            "enabled": True,
            "country": "NL",
            "sources": sorted({event.source for event in ordered}),
            "matched": True,
            "message_count": len(ordered),
            "messages": messages,
            "units": units,
            "capcodes": [
                {"capcode": code, "description": description}
                for code, description in sorted(capcodes.items())
            ][:100],
            "escalation_detected": escalation_detected,
            "last_updated": datetime.now().astimezone().isoformat(),
        }
