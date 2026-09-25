"""Local RTL-SDR P2000 provider using MQTT from the Cyberjunky add-on."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.mqtt import ReceiveMessage
from homeassistant.core import callback

from .model import P2000Event

_LOGGER = logging.getLogger(__name__)
_VEHICLE_RE = re.compile(r"(?<!\\d)\\d{6}(?!\\d)")
_DEFAULT_TOPIC = "homeassistant/sensor/p2000_rtlsdr/2005/attributes"


class P2000RtlMqttProvider:
    """Receive locally decoded P2000 alerts from the RTL-SDR add-on."""

    source = "rtl"

    def __init__(self, hass, *, topic: str = _DEFAULT_TOPIC) -> None:
        self._hass = hass
        self._topic = str(topic or _DEFAULT_TOPIC).strip()
        self._pending: deque[P2000Event] = deque(maxlen=500)
        self._unsubscribe = None
        self._messages_received = 0
        self._last_message_at: str | None = None
        self._last_event: P2000Event | None = None

        # Keep the same diagnostics surface as polling providers so the
        # manager can expose both sources uniformly.
        self.last_poll_at: str | None = None
        self.last_poll_success: bool | None = None
        self.last_error: str | None = None
        self.last_result_count = 0
        self.provider_debug: dict[str, Any] = {
            "transport": "mqtt",
            "topic": self._topic,
            "subscribed": False,
            "pending_events": 0,
            "messages_received": 0,
            "last_message_at": None,
            "last_event": None,
        }

    async def async_start(self) -> None:
        """Subscribe directly to the RTL-SDR add-on MQTT attributes topic."""
        if self._unsubscribe is not None:
            return
        if not await mqtt.async_wait_for_mqtt_client(self._hass):
            self.last_poll_success = False
            self.last_error = "MQTT integration is not available"
            self._update_debug()
            _LOGGER.warning("P2000 RTL-SDR source unavailable: MQTT integration is not available")
            return

        try:
            self._unsubscribe = await mqtt.async_subscribe(
                self._hass, self._topic, self._message_received, qos=0
            )
        except Exception as err:
            self.last_poll_success = False
            self.last_error = str(err)
            self._update_debug()
            _LOGGER.warning("Could not subscribe to P2000 RTL-SDR MQTT topic %s: %s", self._topic, err)
            return

        self.last_poll_success = True
        self.last_error = None
        self._update_debug()

    async def async_stop(self) -> None:
        """Unsubscribe from MQTT."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._update_debug()

    @callback
    def _message_received(self, message: ReceiveMessage) -> None:
        """Normalize one MQTT attributes publication into a P2000 event."""
        received_at = datetime.now().astimezone().isoformat()
        try:
            payload = json.loads(message.payload)
        except (TypeError, ValueError, json.JSONDecodeError) as err:
            self.last_poll_success = False
            self.last_error = f"Invalid JSON payload: {err}"
            self._update_debug()
            return

        event = self._normalize(payload, received_at)
        if event is None:
            self._update_debug()
            return

        self._pending.append(event)
        self._last_event = event
        self._messages_received += 1
        self._last_message_at = received_at
        self.last_poll_success = True
        self.last_error = None
        self._update_debug()

    async def async_fetch(self) -> list[P2000Event]:
        """Drain events received since the previous manager cycle."""
        self.last_poll_at = datetime.now().astimezone().isoformat()
        events = list(self._pending)
        self._pending.clear()
        self.last_result_count = len(events)
        if self._unsubscribe is not None:
            self.last_poll_success = True
            self.last_error = None
        self._update_debug()
        return events

    def _update_debug(self) -> None:
        self.provider_debug = {
            "transport": "mqtt",
            "topic": self._topic,
            "subscribed": self._unsubscribe is not None,
            "pending_events": len(self._pending),
            "messages_received": self._messages_received,
            "last_message_at": self._last_message_at,
            "last_event": self._last_event.as_dict() if self._last_event else None,
        }

    @classmethod
    def _normalize(
        cls, payload: Any, received_at: str
    ) -> P2000Event | None:
        if not isinstance(payload, dict):
            return None

        discipline = str(payload.get("disciplines") or "").strip()
        if discipline and "brandweer" not in discipline.casefold():
            return None

        raw = str(payload.get("raw message") or "").strip()
        parts = raw.split("|") if raw.startswith("FLEX|") else []
        raw_timestamp = parts[1].strip() if len(parts) > 1 else ""
        group_id = str(payload.get("group id") or (parts[3].strip() if len(parts) > 3 else "")).strip()
        raw_capcodes = parts[4].strip() if len(parts) > 4 else ""
        message = parts[6].strip() if len(parts) > 6 else str(payload.get("tts") or "").strip()
        if not message:
            return None

        capcodes_value = payload.get("capcodes")
        if isinstance(capcodes_value, list):
            capcodes = [str(value).strip() for value in capcodes_value if str(value).strip()]
        elif capcodes_value not in (None, ""):
            capcodes = [value for value in re.split(r"[\\s,]+", str(capcodes_value)) if value]
        else:
            capcodes = [value for value in raw_capcodes.split() if value]

        event_time = cls._event_time(raw_timestamp)
        priority = cls._as_int(payload.get("priority"))
        latitude = cls._as_float(payload.get("latitude"))
        longitude = cls._as_float(payload.get("longitude"))
        units = sorted(set(_VEHICLE_RE.findall(message)))

        digest_input = "|".join((raw_timestamp, group_id, " ".join(capcodes), message))
        digest = hashlib.sha1(digest_input.encode("utf-8")).hexdigest()[:16]
        external_id = f"rtl:{raw_timestamp or received_at}:{group_id}:{digest}"

        return P2000Event(
            source="rtl",
            external_id=external_id,
            event_time=event_time,
            received_at=received_at,
            message=message,
            human_message=str(payload.get("tts") or "").strip() or None,
            latitude=latitude,
            longitude=longitude,
            city=str(payload.get("city") or "").strip() or None,
            street=str(payload.get("street") or "").strip() or None,
            postcode=str(payload.get("postal code") or "").strip() or None,
            location_reference=str(payload.get("address") or "").strip() or None,
            priority=priority,
            capcodes=[
                {"capcode": code, "omschrijving": None}
                for code in capcodes
            ],
            units=units,
            talkgroups=[],
        )

    @staticmethod
    def _event_time(value: str) -> str | None:
        """Convert the add-on FLEX UTC timestamp to timezone-aware ISO."""
        if not value:
            return None
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None
        return parsed.astimezone().isoformat()

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
