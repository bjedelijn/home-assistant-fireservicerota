"""Shared incident store for FireServiceRota Extended."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN as FIRESERVICEROTA_DOMAIN

HISTORY_LIMIT = 25
ACTIVE_INCIDENT_REFRESH_SECONDS = 120

END_TIME_KEYS = (
    "ended_at",
    "closed_at",
    "finished_at",
    "resolved_at",
    "completed_at",
    "cancelled_at",
    "canceled_at",
)
STATUS_KEYS = (
    "status",
    "state",
    "incident_status",
    "lifecycle_status",
    "lifecycle_state",
)
CLOSED_STATUS_VALUES = {
    "closed",
    "ended",
    "finished",
    "resolved",
    "completed",
    "cancelled",
    "canceled",
    "archived",
}
OPEN_STATUS_VALUES = {
    "active",
    "open",
    "ongoing",
    "running",
    "started",
    "new",
    "dispatched",
}
CLOSED_TRIGGER_VALUES = {
    "close",
    "closed",
    "end",
    "ended",
    "finish",
    "finished",
    "resolve",
    "resolved",
    "complete",
    "completed",
    "cancel",
    "cancelled",
    "canceled",
    "archive",
    "archived",
}


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an API timestamp into an aware datetime."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _timestamp(value: Any) -> float:
    """Return a sortable timestamp."""
    parsed = _parse_datetime(value)
    return parsed.timestamp() if parsed else 0.0


def _now_iso() -> str:
    """Return the current UTC time as ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


class IncidentStore:
    """Keep unique incidents by API id for active overview and history."""

    def __init__(self, hass: HomeAssistant, client, entry_id: str) -> None:
        """Initialize the incident store."""
        self._hass = hass
        self._client = client
        self._entry_id = entry_id
        self._incidents: dict[str, dict] = {}
        self._latest_incident_id: Any = None
        self._last_rest_refresh: dict[str, float] = {}
        self._refresh_lock = asyncio.Lock()

    @property
    def signal(self) -> str:
        """Return the dispatcher signal used by the overview sensors."""
        return f"{FIRESERVICEROTA_DOMAIN}_{self._entry_id}_incident_store_update"

    @property
    def latest_incident_id(self):
        """Return the most recently received live incident id."""
        return self._latest_incident_id

    def _notify(self) -> None:
        """Notify overview/history sensors that the store changed."""
        async_dispatcher_send(self._hass, self.signal)

    @staticmethod
    def _key(incident_id: Any) -> str:
        """Return a stable dictionary key for an incident id."""
        return str(incident_id)

    @staticmethod
    def _lifecycle_fields(data: dict) -> dict:
        """Expose scalar lifecycle-looking REST fields for safe diagnostics."""
        fields = {}
        for key, value in data.items():
            lowered = str(key).lower()
            lifecycle_like = (
                lowered in STATUS_KEYS
                or lowered in END_TIME_KEYS
                or lowered in {
                    "created_at",
                    "updated_at",
                    "active",
                    "closed",
                    "ended",
                    "finished",
                    "resolved",
                    "completed",
                    "cancelled",
                    "canceled",
                }
                or any(
                    token in lowered
                    for token in (
                        "status",
                        "state",
                        "closed",
                        "ended",
                        "finish",
                        "resolved",
                        "complete",
                        "cancel",
                    )
                )
            )
            if lifecycle_like and (
                value is None or isinstance(value, (str, int, float, bool))
            ):
                fields[key] = value
        return fields

    @staticmethod
    def _first_value(data: dict, keys: tuple[str, ...]) -> Any:
        """Return the first present, non-empty value from a key list."""
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                return value
        return None

    def _compact_snapshot(
        self,
        data: dict,
        previous: dict | None,
        source: str,
        default_active: bool | None,
    ) -> dict:
        """Build a compact, dashboard-friendly incident snapshot."""
        previous = previous or {}
        snapshot = dict(previous)

        for key in (
            "id",
            "body",
            "trigger",
            "created_at",
            "updated_at",
            "prio",
            "type",
            "responder_mode",
            "can_respond_until",
            "task_ids",
            "previous_task_ids",
            "new_task_ids",
            "resolved_tasks",
            "resolved_stations",
            "responses_by_station",
            "first_seen_at",
            "last_seen_at",
        ):
            if key in data and data[key] is not None:
                value = data[key]
                if isinstance(value, list):
                    value = list(value)
                snapshot[key] = value

        address = data.get("address")
        if isinstance(address, dict):
            snapshot["address"] = {
                key: address.get(key)
                for key in (
                    "latitude",
                    "longitude",
                    "address_type",
                    "formatted_address",
                )
                if address.get(key) is not None
            }
        else:
            flat_address = {
                key: data.get(key)
                for key in (
                    "latitude",
                    "longitude",
                    "address_type",
                    "formatted_address",
                )
                if data.get(key) is not None
            }
            if flat_address:
                snapshot["address"] = flat_address

        previous_lifecycle = previous.get("lifecycle_fields")
        lifecycle = dict(previous_lifecycle) if isinstance(previous_lifecycle, dict) else {}
        restored_lifecycle = data.get("lifecycle_fields")
        if isinstance(restored_lifecycle, dict):
            lifecycle.update(restored_lifecycle)
        lifecycle.update(self._lifecycle_fields(data))
        if lifecycle:
            snapshot["lifecycle_fields"] = lifecycle

        ended_at = self._first_value(data, END_TIME_KEYS)
        if ended_at is None:
            ended_at = self._first_value(lifecycle, END_TIME_KEYS)
        if ended_at is None:
            ended_at = data.get("incident_ended_at")
        if ended_at is None:
            ended_at = previous.get("incident_ended_at")

        raw_status = self._first_value(data, STATUS_KEYS)
        if raw_status is None:
            raw_status = self._first_value(lifecycle, STATUS_KEYS)

        active = previous.get("incident_active")
        lifecycle_known = bool(previous.get("lifecycle_known", False))
        explicit_lifecycle = False
        if source == "restore" and isinstance(data.get("incident_active"), bool):
            active = data["incident_active"]
        if source == "restore" and isinstance(data.get("lifecycle_known"), bool):
            lifecycle_known = data["lifecycle_known"]

        if ended_at is not None:
            active = False
            lifecycle_known = True
            explicit_lifecycle = True
        else:
            status_text = str(raw_status).strip().lower() if raw_status is not None else ""
            if status_text in CLOSED_STATUS_VALUES:
                active = False
                lifecycle_known = True
                explicit_lifecycle = True
            elif status_text in OPEN_STATUS_VALUES:
                active = True
                lifecycle_known = True
                explicit_lifecycle = True

            if isinstance(data.get("active"), bool):
                active = data["active"]
                lifecycle_known = True
                explicit_lifecycle = True

            for key in (
                "closed",
                "ended",
                "finished",
                "resolved",
                "completed",
                "cancelled",
                "canceled",
            ):
                if data.get(key) is True:
                    active = False
                    lifecycle_known = True
                    explicit_lifecycle = True
                    break

            trigger = str(data.get("trigger") or "").strip().lower()
            if trigger in CLOSED_TRIGGER_VALUES:
                active = False
                lifecycle_known = True
            elif (
                source == "websocket"
                and trigger in {"new", "update"}
                and not explicit_lifecycle
            ):
                # A websocket update means the incident is live only when the
                # payload does not itself contain an explicit lifecycle state.
                # For example, BrandweerRooster can send trigger=update together
                # with state=finished; finished must win in that case.
                active = True

        if active is None and default_active is not None:
            active = default_active
        if active is None and source == "websocket":
            active = True
        if active is None:
            active = True

        snapshot["incident_active"] = bool(active)
        snapshot["lifecycle_known"] = lifecycle_known
        snapshot["incident_status"] = (
            str(raw_status)
            if raw_status not in (None, "")
            else ("active" if active else "closed")
        )
        if ended_at is not None:
            snapshot["incident_ended_at"] = ended_at
        elif active:
            snapshot.pop("incident_ended_at", None)

        snapshot.setdefault("first_seen_at", _now_iso())
        if source != "restore":
            snapshot["last_seen_at"] = _now_iso()
        else:
            snapshot.setdefault("last_seen_at", snapshot.get("first_seen_at"))
        snapshot["last_source"] = source
        return snapshot

    def _prune(self) -> None:
        """Keep all active incidents and a bounded number of closed incidents."""
        closed = [
            (key, value)
            for key, value in self._incidents.items()
            if value.get("incident_active") is False
        ]
        closed.sort(
            key=lambda item: _timestamp(
                item[1].get("incident_ended_at")
                or item[1].get("updated_at")
                or item[1].get("created_at")
                or item[1].get("first_seen_at")
            ),
            reverse=True,
        )
        for key, _ in closed[HISTORY_LIMIT:]:
            self._incidents.pop(key, None)
            self._last_rest_refresh.pop(key, None)

    def upsert(
        self,
        data: dict,
        *,
        source: str,
        default_active: bool | None = None,
        notify: bool = True,
    ) -> dict | None:
        """Insert or update one incident without creating duplicate history rows."""
        incident_id = data.get("id")
        if incident_id is None:
            return None

        key = self._key(incident_id)
        previous = self._incidents.get(key)
        snapshot = self._compact_snapshot(data, previous, source, default_active)
        self._incidents[key] = snapshot

        if source == "websocket":
            self._latest_incident_id = incident_id
        elif self._latest_incident_id is None:
            self._latest_incident_id = incident_id

        self._prune()
        if notify:
            self._notify()
        return snapshot

    def restore(self, incidents: list, *, active: bool) -> None:
        """Restore incident snapshots from a RestoreEntity attribute."""
        changed = False
        for incident in incidents:
            if not isinstance(incident, dict) or incident.get("id") is None:
                continue
            restored = dict(incident)
            restored["incident_active"] = active
            self.upsert(
                restored,
                source="restore",
                default_active=active,
                notify=False,
            )
            changed = True
        if changed:
            self._notify()

    def get_raw(self, incident_id: Any) -> dict | None:
        """Return the internal compact snapshot for one incident."""
        if incident_id is None:
            return None
        snapshot = self._incidents.get(self._key(incident_id))
        return dict(snapshot) if snapshot else None

    @staticmethod
    def _public_snapshot(snapshot: dict) -> dict:
        """Return a copy with live duration and convenient address fields."""
        public = dict(snapshot)
        address = public.get("address")
        if isinstance(address, dict):
            for key in (
                "latitude",
                "longitude",
                "address_type",
                "formatted_address",
            ):
                if address.get(key) is not None:
                    public[key] = address[key]

        start = _parse_datetime(public.get("created_at"))
        if start is not None:
            if public.get("incident_active"):
                end = datetime.now(timezone.utc)
            else:
                end = _parse_datetime(public.get("incident_ended_at"))
            if end is not None:
                public["duration_seconds"] = max(0, int((end - start).total_seconds()))
            else:
                public["duration_seconds"] = None
        else:
            public["duration_seconds"] = None
        return public

    def get_public(self, incident_id: Any) -> dict | None:
        """Return one public snapshot."""
        raw = self.get_raw(incident_id)
        return self._public_snapshot(raw) if raw else None

    @property
    def active_incidents(self) -> list[dict]:
        """Return all currently active/ongoing incidents, newest first."""
        incidents = [
            self._public_snapshot(snapshot)
            for snapshot in self._incidents.values()
            if snapshot.get("incident_active") is not False
        ]
        return sorted(
            incidents,
            key=lambda item: _timestamp(item.get("created_at") or item.get("first_seen_at")),
            reverse=True,
        )

    @property
    def history(self) -> list[dict]:
        """Return closed incidents, each incident id only once, newest first."""
        incidents = [
            self._public_snapshot(snapshot)
            for snapshot in self._incidents.values()
            if snapshot.get("incident_active") is False
        ]
        return sorted(
            incidents,
            key=lambda item: _timestamp(
                item.get("incident_ended_at")
                or item.get("updated_at")
                or item.get("created_at")
                or item.get("first_seen_at")
            ),
            reverse=True,
        )[:HISTORY_LIMIT]

    def mark_rest_refreshed(self, incident_id: Any) -> None:
        """Record when an incident was last refreshed through REST."""
        if incident_id is not None:
            self._last_rest_refresh[self._key(incident_id)] = time.monotonic()

    async def async_refresh_active(self) -> None:
        """Periodically refresh active incidents so API closure is detected."""
        if not self.active_incidents:
            return

        async with self._refresh_lock:
            now = time.monotonic()
            changed = False
            for public in list(self.active_incidents):
                incident_id = public.get("id")
                if incident_id is None:
                    continue
                key = self._key(incident_id)
                if now - self._last_rest_refresh.get(key, 0) < ACTIVE_INCIDENT_REFRESH_SECONDS:
                    continue

                incident = await self._client.async_get_incident(incident_id)
                self._last_rest_refresh[key] = time.monotonic()
                if not isinstance(incident, dict):
                    continue

                existing = self.get_raw(incident_id) or {"id": incident_id}
                merged = dict(existing)
                merged.update(incident)
                for preserve in ("trigger", "previous_task_ids", "new_task_ids"):
                    if preserve not in incident and preserve in existing:
                        merged[preserve] = existing[preserve]

                enriched = self._client.enrich_incident_data(merged)
                self.upsert(enriched, source="rest", notify=False)
                changed = True

            if changed:
                self._notify()
