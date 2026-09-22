"""Coordinate optional P2000 enrichment for Dutch incidents."""
from __future__ import annotations

import asyncio
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
_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "brandweer", "melding", "prio", "p", "br", "bon", "naar", "voor", "met",
    "aan", "de", "het", "een", "bij", "in", "op", "van", "en", "te",
}


class P2000EnrichmentManager:
    """Poll P2000 providers and enrich active BrandweerRooster incidents."""

    def __init__(self, hass, incident_store, *, scan_interval: int = 30) -> None:
        self._hass = hass
        self._incident_store = incident_store
        self._scan_interval = max(30, int(scan_interval))
        self._providers = [P2000OnlineProvider(hass)]
        self._task: asyncio.Task | None = None
        self._first_received: dict[str, str] = {}
        self._stopping = False

    async def async_start(self) -> None:
        """Start the enrichment loop."""
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
        """Poll while Home Assistant keeps this config entry loaded."""
        try:
            while not self._stopping:
                if self._incident_store.active_incidents:
                    await self._async_poll_once()
                await asyncio.sleep(self._scan_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Unexpected error in P2000 enrichment loop")

    async def _async_poll_once(self) -> None:
        events: list[P2000Event] = []
        for provider in self._providers:
            try:
                fetched = await provider.async_fetch()
            except Exception:
                _LOGGER.exception("P2000 provider %s failed", provider.source)
                continue
            for event in fetched:
                key = self._event_key(event)
                first = self._first_received.setdefault(key, event.received_at)
                event.received_at = first
                events.append(event)

        if not events:
            return

        for incident in self._incident_store.active_incidents:
            incident_id = incident.get("id")
            if incident_id is None:
                continue
            matched = [event for event in events if self._matches(incident, event)]
            if not matched:
                continue
            enrichment = self._build_enrichment(matched)
            self._incident_store.apply_p2000_enrichment(incident_id, enrichment)

    @staticmethod
    def _event_key(event: P2000Event) -> str:
        return event.external_id or f"{event.event_time}|{event.message}"

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
        ordered = sorted(events, key=lambda event: event.event_time or event.received_at)
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
