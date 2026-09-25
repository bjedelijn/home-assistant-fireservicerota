"""Coordinate optional P2000 enrichment for Dutch incidents."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import math
import re
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.storage import Store

from .model import P2000Event
from .escalation import build_escalation_summary
from .online import P2000OnlineProvider
from .rtl import P2000RtlMqttProvider
from .source_timing import build_source_timing
from .station_hints import build_station_and_unit_hints
from ..vehicle_registry import BrandbaseVehicleRegistry

_LOGGER = logging.getLogger(__name__)

_MATCH_RADIUS_METERS = 1500
_MATCH_WINDOW_BEFORE = timedelta(minutes=15)
_MATCH_WINDOW_AFTER = timedelta(hours=3)
_GROUP_RADIUS_METERS = 250
_GROUP_WINDOW = timedelta(minutes=90)
_BUFFER_RETENTION = timedelta(minutes=60)
_GROUP_CLOSE_GRACE = timedelta(minutes=10)
_GROUP_END_CLUSTER = timedelta(minutes=15)
_PERSISTENT_MATCH_LIMIT = 25
_PERSISTENT_STORAGE_VERSION = 1
_SOURCE_LABELS = {
    "online": "P2000 online",
    "rtl": "P2000 via ether",
}
_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "brandweer", "melding", "prio", "p", "br", "bon", "naar", "voor", "met",
    "aan", "de", "het", "een", "bij", "in", "op", "van", "en", "te",
}


class P2000EnrichmentManager:
    """Continuously buffer P2000 alerts and enrich BrandweerRooster incidents."""

    def __init__(
        self,
        hass,
        incident_store,
        *,
        scan_interval: int = 30,
        source: str = "online",
        rtl_topic: str | None = None,
    ) -> None:
        self._hass = hass
        self._incident_store = incident_store
        self._scan_interval = max(30, int(scan_interval))
        selected = str(source or "online").strip().lower()
        self._providers = []
        if selected in {"online", "both"}:
            self._providers.append(P2000OnlineProvider(hass))
        if selected in {"rtl", "both"}:
            kwargs = {"topic": rtl_topic} if rtl_topic else {}
            self._providers.append(P2000RtlMqttProvider(hass, **kwargs))
        self._vehicle_registry = BrandbaseVehicleRegistry(hass)
        self._task: asyncio.Task | None = None
        self._first_received: dict[str, str] = {}
        self._buffer: dict[str, P2000Event] = {}
        self._persistent_matches: dict[str, dict[str, Any]] = {}
        self._persistent_store: Store | None = None
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
    def recent_events(self) -> list[dict[str, Any]]:
        """Return the newest shared-buffer events for source diagnostics."""
        ordered = sorted(
            self._buffer.values(),
            key=lambda item: self._event_timestamp(item).timestamp(),
            reverse=True,
        )
        recent = []
        for event in ordered[:20]:
            item = event.as_dict()
            item["source_label"] = _SOURCE_LABELS.get(event.source, event.source)
            recent.append(item)
        return recent

    @property
    def persistent_matches(self) -> list[dict[str, Any]]:
        """Return bounded persistent practical-incident P2000 matches."""
        return sorted(
            [dict(item) for item in self._persistent_matches.values()],
            key=lambda item: str(item.get("last_updated") or ""), reverse=True
        )[:_PERSISTENT_MATCH_LIMIT]

    def restore_matches(
        self, matches: list[dict[str, Any]], *, notify: bool = True
    ) -> None:
        """Restore persistent P2000 matches from integration storage."""
        self._persistent_matches = {
            str(item["group_id"]): dict(item)
            for item in matches
            if isinstance(item, dict) and item.get("group_id") not in (None, "")
        }
        keep = self.persistent_matches
        self._persistent_matches = {str(item["group_id"]): item for item in keep}
        if notify:
            self._notify()

    def _persistent_storage_data(self) -> dict[str, Any]:
        """Return the full bounded persistent match payload for HA storage."""
        return {"matches": self.persistent_matches}

    def _schedule_persistent_save(self) -> None:
        """Coalesce persistent match writes outside the state machine/recorder."""
        if self._persistent_store is not None:
            self._persistent_store.async_delay_save(
                self._persistent_storage_data, 5
            )

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
                "provider_debug": getattr(provider, "provider_debug", {}),
            }
        return {
            "enabled": True,
            "sources": [provider.source for provider in self._providers],
            "source_labels": {
                provider.source: _SOURCE_LABELS.get(provider.source, provider.source)
                for provider in self._providers
            },
            "scan_interval_seconds": self._scan_interval,
            "buffer_retention_minutes": self.buffer_retention_minutes,
            "buffered_events": self.buffer_size,
            "persistent_match_groups": len(self._persistent_matches),
            "last_poll_at": self._last_poll_at,
            "last_poll_success": self._last_poll_success,
            "last_poll_result_count": self._last_poll_result_count,
            "last_event": self.last_event,
            "recent_events": self.recent_events,
            "providers": providers,
            "vehicle_registry": self._vehicle_registry.status,
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

    async def async_start(self, config_entry) -> None:
        """Start continuous P2000 reception as a config-entry background task."""
        if self._task is None or self._task.done():
            await self._vehicle_registry.async_load()
            self._vehicle_registry.schedule_refresh_if_due()

            if self._persistent_store is None:
                self._persistent_store = Store(
                    self._hass,
                    _PERSISTENT_STORAGE_VERSION,
                    f"fireservicerota.p2000_matches.{config_entry.entry_id}",
                )
                stored = await self._persistent_store.async_load()
                if isinstance(stored, dict):
                    matches = stored.get("matches")
                    if isinstance(matches, list):
                        self.restore_matches(matches, notify=False)

            config_entry.async_on_unload(
                self._hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STOP,
                    self._async_handle_homeassistant_stop,
                )
            )

            for provider in self._providers:
                starter = getattr(provider, "async_start", None)
                if starter is not None:
                    await starter()

            self._stopping = False
            self._task = config_entry.async_create_background_task(
                self._hass,
                self._run(),
                name="fireservicerota_p2000_enrichment",
            )

    async def _async_handle_homeassistant_stop(self, _event) -> None:
        """Stop polling before Home Assistant reaches final-writes shutdown."""
        await self.async_stop()

    async def async_stop(self) -> None:
        """Stop the enrichment loop and persist the latest bounded matches."""
        self._stopping = True
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        for provider in self._providers:
            stopper = getattr(provider, "async_stop", None)
            if stopper is not None:
                try:
                    await stopper()
                except Exception:
                    _LOGGER.exception("Could not stop P2000 provider %s", provider.source)

        if self._persistent_store is not None:
            await self._persistent_store.async_save(self._persistent_storage_data())

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
        self._vehicle_registry.schedule_refresh_if_due()
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
        # BrandweerRooster can expose multiple technical incident ids for one
        # practical incident. Group those ids first, then attach one shared
        # P2000 timeline while preserving each original API incident separately.
        buffered = list(self._buffer.values())
        incidents = self._correlation_incidents()
        for group in self._incident_groups(incidents):
            incident_ids = [
                incident.get("id")
                for incident in group
                if incident.get("id") is not None
            ]
            if not incident_ids:
                continue

            primary = min(
                group,
                key=lambda incident: self._incident_timestamp(incident).timestamp(),
            )
            primary_id = primary.get("id")
            group_meta = {
                "group_id": str(primary_id),
                "primary_incident_id": primary_id,
                "incident_ids": incident_ids,
                "member_count": len(incident_ids),
                "practical_incident": len(incident_ids) > 1,
            }
            for incident_id in incident_ids:
                self._incident_store.apply_incident_group(incident_id, group_meta)

            group_end = self._group_operational_end(group)
            if group_end is not None:
                ended_at, source_ids = group_end
                self._incident_store.apply_group_operational_end(
                    incident_ids, ended_at=ended_at, source_incident_ids=source_ids
                )

            matched_by_key: dict[str, P2000Event] = {}
            for incident in group:
                for event in self._events_from_enrichment(incident.get("p2000_enrichment")):
                    matched_by_key[self._event_key(event)] = event
            for event in buffered:
                if any(self._matches(incident, event) for incident in group):
                    matched_by_key[self._event_key(event)] = event
            matched = list(matched_by_key.values())
            if not matched:
                continue

            enrichment = self._build_enrichment(matched, incidents=group)
            enrichment["incident_group_id"] = str(primary_id)
            enrichment["incident_ids"] = incident_ids
            for incident in group:
                incident_id = incident.get("id")
                if incident_id is None:
                    continue
                existing = incident.get("p2000_enrichment")
                if self._same_enrichment(existing, enrichment):
                    continue
                self._incident_store.apply_p2000_enrichment(incident_id, enrichment)

            self._remember_persistent_match(group_meta, enrichment, incidents=group)

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

    @staticmethod
    def _event_from_dict(data: Any) -> P2000Event | None:
        if not isinstance(data, dict) or not data.get("message"):
            return None
        return P2000Event(
            source=str(data.get("source") or "persisted"),
            external_id=str(data["external_id"]) if data.get("external_id") not in (None, "") else None,
            event_time=data.get("event_time"),
            received_at=str(data.get("received_at") or data.get("event_time") or datetime.now().astimezone().isoformat()),
            message=str(data.get("message")),
            human_message=data.get("human_message"),
            latitude=P2000EnrichmentManager._as_float(data.get("latitude")),
            longitude=P2000EnrichmentManager._as_float(data.get("longitude")),
            city=data.get("city"), street=data.get("street"), postcode=data.get("postcode"),
            location_reference=data.get("location_reference"), priority=data.get("priority"),
            grip=data.get("grip"), capcodes=list(data.get("capcodes") or []),
            units=[str(x) for x in (data.get("units") or [])],
            talkgroups=[str(x) for x in (data.get("talkgroups") or [])],
        )

    @classmethod
    def _events_from_enrichment(cls, enrichment: Any) -> list[P2000Event]:
        if not isinstance(enrichment, dict):
            return []
        return [
            event for event in (cls._event_from_dict(item) for item in enrichment.get("messages") or [])
            if event is not None
        ]

    def _remember_persistent_match(
        self,
        group_meta: dict[str, Any],
        enrichment: dict[str, Any],
        *,
        incidents: list[dict[str, Any]] | None = None,
    ) -> None:
        group_id = str(group_meta.get("group_id") or "").strip()
        if not group_id:
            return
        ids = {str(x) for x in (group_meta.get("incident_ids") or [])}
        overlap = [
            key for key,item in self._persistent_matches.items()
            if key == group_id or ids.intersection(str(x) for x in (item.get("incident_ids") or []))
        ]
        events = {}
        for key in overlap:
            old = self._persistent_matches.get(key) or {}
            ids.update(str(x) for x in (old.get("incident_ids") or []))
            for event in self._events_from_enrichment(old.get("p2000_enrichment")):
                events[self._event_key(event)] = event
        for event in self._events_from_enrichment(enrichment):
            events[self._event_key(event)] = event
        rebuilt = self._build_enrichment(
            list(events.values()), incidents=incidents or []
        )
        rebuilt["incident_group_id"] = group_id
        rebuilt["incident_ids"] = sorted(ids)
        for key in overlap:
            self._persistent_matches.pop(key, None)
        self._persistent_matches[group_id] = {
            "group_id": group_id,
            "primary_incident_id": group_meta.get("primary_incident_id"),
            "incident_ids": sorted(ids),
            "member_count": len(ids),
            "practical_incident": len(ids) > 1,
            "p2000_enrichment": rebuilt,
            "last_updated": datetime.now().astimezone().isoformat(),
        }
        keep = self.persistent_matches
        self._persistent_matches = {str(x["group_id"]): x for x in keep}
        self._schedule_persistent_save()

    @classmethod
    def _group_operational_end(cls, group: list[dict[str, Any]]) -> tuple[str, list[Any]] | None:
        """Infer a practical end only from authoritative BWR end times."""
        if len(group) < 2:
            return None
        closed = []
        for incident in group:
            raw = incident.get("end_time")
            if raw in (None, "") and incident.get("ended_at_source") == "api":
                raw = incident.get("incident_ended_at")
            ended = cls._parse_datetime(raw)
            if ended is not None:
                closed.append((incident, ended))
        if not closed:
            return None
        primary = min(group, key=lambda x: cls._incident_timestamp(x).timestamp())
        primary_closed = next(((i,e) for i,e in closed if str(i.get("id")) == str(primary.get("id"))), None)
        times = [e for _,e in closed]
        clustered = len(times) >= 2 and max(times) - min(times) <= _GROUP_END_CLUSTER
        if primary_closed is None and not clustered:
            return None
        ended = max(times) if clustered else primary_closed[1]
        if datetime.now().astimezone() < ended + _GROUP_CLOSE_GRACE:
            return None
        return ended.isoformat(), [i.get("id") for i,_ in closed if i.get("id") is not None]

    def _correlation_incidents(self) -> list[dict[str, Any]]:
        """Return active plus recently closed incidents relevant to the buffer."""
        combined: dict[str, dict[str, Any]] = {}
        for incident in self._incident_store.active_incidents:
            if incident.get("id") is not None:
                combined[str(incident["id"])] = incident

        cutoff = datetime.now().astimezone() - (_MATCH_WINDOW_AFTER + _BUFFER_RETENTION)
        for incident in self._incident_store.history:
            if incident.get("id") is None:
                continue
            if (
                self._incident_timestamp(incident) < cutoff
                and not incident.get("p2000_enrichment")
                and not incident.get("incident_group")
            ):
                continue
            combined.setdefault(str(incident["id"]), incident)
        return list(combined.values())

    @classmethod
    def _incident_groups(
        cls, incidents: list[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]:
        """Return connected groups of BWR ids representing one practical incident."""
        remaining = list(incidents)
        groups: list[list[dict[str, Any]]] = []
        while remaining:
            group = [remaining.pop(0)]
            changed = True
            while changed:
                changed = False
                for candidate in list(remaining):
                    if any(cls._same_practical_incident(member, candidate) for member in group):
                        group.append(candidate)
                        remaining.remove(candidate)
                        changed = True
            groups.append(group)
        return groups

    @classmethod
    def _same_practical_incident(
        cls, left: dict[str, Any], right: dict[str, Any]
    ) -> bool:
        """Determine whether two BWR API ids belong to one practical incident."""
        left_time = cls._incident_timestamp(left)
        right_time = cls._incident_timestamp(right)
        if abs(left_time - right_time) > _GROUP_WINDOW:
            return False

        left_lat = cls._incident_coordinate(left, "latitude")
        left_lon = cls._incident_coordinate(left, "longitude")
        right_lat = cls._incident_coordinate(right, "latitude")
        right_lon = cls._incident_coordinate(right, "longitude")

        coordinate_match = False
        very_close = False
        if None not in (left_lat, left_lon, right_lat, right_lon):
            distance = cls._distance_meters(left_lat, left_lon, right_lat, right_lon)
            if distance > _GROUP_RADIUS_METERS:
                return False
            coordinate_match = True
            very_close = distance <= 100

        left_address = cls._normalized_address(left)
        right_address = cls._normalized_address(right)
        exact_address = bool(left_address and left_address == right_address)

        left_location_tokens = cls._tokens(left_address)
        right_location_tokens = cls._tokens(right_address)
        location_overlap = len(left_location_tokens & right_location_tokens) >= 2

        if not (coordinate_match or exact_address or location_overlap):
            return False

        left_channels = cls._channel_values(left.get("radio_channels"))
        right_channels = cls._channel_values(right.get("radio_channels"))
        if left_channels and right_channels and left_channels & right_channels:
            return True

        left_text = cls._tokens(str(left.get("body") or ""))
        right_text = cls._tokens(str(right.get("body") or ""))
        if len(left_text & right_text) >= 2:
            return True

        # Exact address or a very small coordinate delta is sufficient when
        # technical BWR calls are close in time but wording changes on escalation.
        return exact_address or very_close

    @classmethod
    def _incident_timestamp(cls, incident: dict[str, Any]) -> datetime:
        """Return the best available start timestamp for grouping."""
        parsed = cls._parse_datetime(incident.get("start_time") or incident.get("created_at"))
        return parsed or datetime.now().astimezone()

    @classmethod
    def _incident_coordinate(cls, incident: dict[str, Any], key: str) -> float | None:
        value = incident.get(key)
        if value is None and isinstance(incident.get("address"), dict):
            value = incident["address"].get(key)
        return cls._as_float(value)

    @staticmethod
    def _normalized_address(incident: dict[str, Any]) -> str:
        value = incident.get("formatted_address")
        if value is None and isinstance(incident.get("address"), dict):
            value = incident["address"].get("formatted_address")
        return " ".join(str(value or "").lower().split())

    @staticmethod
    def _channel_values(value: Any) -> set[str]:
        """Normalize BWR radio-channel/talkgroup values without assuming schema."""
        result: set[str] = set()
        if value in (None, ""):
            return result
        if isinstance(value, dict):
            for item in value.values():
                result.update(P2000EnrichmentManager._channel_values(item))
            return result
        if isinstance(value, (list, tuple, set)):
            for item in value:
                result.update(P2000EnrichmentManager._channel_values(item))
            return result
        text = str(value).strip().lower()
        if text:
            result.add(text)
        return result

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

    def _build_enrichment(
        self,
        events: list[P2000Event],
        *,
        incidents: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ordered = sorted(events, key=P2000EnrichmentManager._event_timestamp)
        unit_candidates_raw = sorted(
            {unit for event in ordered for unit in event.units}
        )
        talkgroups = sorted({group for event in ordered for group in event.talkgroups})
        capcodes: dict[str, str | None] = {}
        for event in ordered:
            for item in event.capcodes:
                code = str(item.get("capcode") or "").strip()
                if not code:
                    continue
                description = str(item.get("omschrijving") or "").strip() or None
                capcodes.setdefault(code, description)

        station_hints, unit_details = build_station_and_unit_hints(ordered)
        registry_details = self._vehicle_registry.resolve_units(unit_candidates_raw)
        vehicle_by_unit = {
            str(item.get("unit")): item
            for item in registry_details
            if isinstance(item, dict)
        }

        confirmed_units: list[str] = []
        unresolved_unit_candidates: list[str] = []
        vehicle_details: list[dict[str, Any]] = []

        for detail in unit_details:
            unit = str(detail.get("unit") or "")
            registry = vehicle_by_unit.get(unit)
            if registry:
                detail["vehicle_registry"] = registry

            registry_confirmed = bool(registry and registry.get("resolved"))
            capcode_confirmed = bool(
                detail.get("station_confidence") == "high"
                and detail.get("station_reason") == "unit_suffix_match"
            )

            confirmed = registry_confirmed or capcode_confirmed
            detail["vehicle_confirmed"] = confirmed

            if registry_confirmed:
                detail["vehicle_confirmation_source"] = "brandbase_cache"
                detail["vehicle_confirmation_reason"] = "vehicle_registry_exact"

                # Preserve any P2000/capcode-derived station evidence for
                # diagnostics, while the exact callsign lookup becomes the
                # canonical vehicle -> station identity.
                if detail.get("station_name") is not None:
                    detail["p2000_station_name"] = detail.get("station_name")
                    detail["p2000_station_source"] = detail.get("station_source")
                    detail["p2000_station_confidence"] = detail.get(
                        "station_confidence"
                    )
                    detail["p2000_station_reason"] = detail.get("station_reason")

                detail["station_name"] = registry.get("station")
                detail["station_source"] = "brandbase_cache"
                detail["station_confidence"] = "high"
                detail["station_reason"] = "vehicle_registry_exact"
                detail["callsign"] = registry.get("callsign")
                detail["region_code"] = registry.get("region_code")
                detail["region"] = registry.get("region")
                detail["station_code"] = registry.get("station_code")
                detail["vehicle_type"] = registry.get("vehicle_type")
                detail["vehicle_type_code"] = registry.get("vehicle_type_code")

                vehicle_record = dict(registry)
                vehicle_record["confirmed"] = True
                vehicle_details.append(vehicle_record)
            elif capcode_confirmed:
                detail["vehicle_confirmation_source"] = "p2000_capcode"
                detail["vehicle_confirmation_reason"] = "unit_suffix_match"
                vehicle_details.append(
                    {
                        "unit": unit,
                        "confirmed": True,
                        "resolved": False,
                        "source": "p2000_capcode",
                        "confidence": "high",
                        "station": detail.get("station_name"),
                        "vehicle_type": None,
                        "vehicle_type_code": None,
                        "candidates": [],
                    }
                )
            else:
                detail["vehicle_confirmation_source"] = None
                detail["vehicle_confirmation_reason"] = None

            if confirmed:
                confirmed_units.append(unit)
            else:
                unresolved_unit_candidates.append(unit)

        units = sorted(set(confirmed_units))
        unresolved_unit_candidates = sorted(set(unresolved_unit_candidates))
        vehicle_details.sort(key=lambda item: str(item.get("unit") or ""))

        escalation = build_escalation_summary(ordered)
        source_timing = build_source_timing(
            ordered,
            incidents or [],
            online_poll_interval_seconds=self._scan_interval,
        )
        messages = [event.as_dict() for event in ordered[:20]]
        return {
            "enabled": True,
            "country": "NL",
            "sources": sorted({event.source for event in ordered}),
            "matched": True,
            "message_count": len(ordered),
            "messages": messages,
            "unit_candidates_raw": unit_candidates_raw,
            "units": units,
            "unresolved_unit_candidates": unresolved_unit_candidates,
            "vehicles": vehicle_details,
            "talkgroups": talkgroups,
            "capcodes": [
                {"capcode": code, "description": description}
                for code, description in sorted(capcodes.items())
            ][:100],
            "station_hints": station_hints,
            "unit_details": unit_details,
            "source_timing": source_timing,
            **escalation,
            "last_updated": datetime.now().astimezone().isoformat(),
        }