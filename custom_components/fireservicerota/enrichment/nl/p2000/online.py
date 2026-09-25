"""Online P2000 provider using the public AlarmeringDroid feed."""
from __future__ import annotations

from datetime import datetime
import json
import logging
import re
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .model import P2000Event

_LOGGER = logging.getLogger(__name__)

_API_URL = "https://beta.alarmeringdroid.nl/api2/find/"
_VEHICLE_RE = re.compile(r"(?<!\d)\d{6}(?!\d)")
_POSTCODE_RE = re.compile(r"^[1-9][0-9]{3}\s?[A-Z]{2}$", re.IGNORECASE)
_FIRE_SERVICE_ID = "2"


class P2000OnlineProvider:
    """Fetch recent Dutch fire-service P2000 alerts."""

    source = "online"

    def __init__(self, hass) -> None:
        self._hass = hass
        self._session = async_get_clientsession(hass)
        self.last_poll_at: str | None = None
        self.last_poll_success: bool | None = None
        self.last_error: str | None = None
        self.last_result_count = 0

    async def async_fetch(self) -> list[P2000Event]:
        """Fetch and normalize the current set of fire-service alerts."""
        payload = json.dumps({"diensten": ["2"]}, separators=(",", ":"))
        url = f"{_API_URL}{payload}"
        self.last_poll_at = datetime.now().astimezone().isoformat()
        try:
            async with self._session.get(
                url,
                timeout=ClientTimeout(total=10),
                allow_redirects=False,
            ) as response:
                response.raise_for_status()
                raw = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            self.last_poll_success = False
            self.last_error = str(err)
            self.last_result_count = 0
            _LOGGER.warning("P2000 online feed unavailable: %s", err)
            return []

        meldingen = raw.get("meldingen") if isinstance(raw, dict) else None
        if not isinstance(meldingen, list):
            self.last_poll_success = False
            self.last_error = "Unexpected response: missing meldingen list"
            self.last_result_count = 0
            return []

        received_at = datetime.now().astimezone().isoformat()
        events: list[P2000Event] = []
        seen: set[str] = set()
        for item in meldingen:
            if not isinstance(item, dict):
                continue
            for candidate in self._expand(item):
                event = self._normalize(candidate, received_at)
                if event is None:
                    continue
                key = event.external_id or f"{event.event_time}|{event.message}"
                if key in seen:
                    continue
                seen.add(key)
                events.append(event)
        self.last_poll_success = True
        self.last_error = None
        self.last_result_count = len(events)
        return events

    @staticmethod
    def _is_fire_service_item(item: dict[str, Any]) -> bool:
        """Return True only for records explicitly marked as fire service.

        AlarmeringDroid exposes the service discipline as the per-record
        "dienst" value. The search itself is already restricted with
        diensten=["2"], but grouped incidents can still contain related
        subitems from another service. Re-check every expanded record before
        normalization so only fire-service records enter the P2000 buffer.
        """
        service = item.get("dienst")
        if isinstance(service, dict):
            service = service.get("id")
        return str(service or "").strip() == _FIRE_SERVICE_ID

    @classmethod
    def _expand(cls, item: dict[str, Any]) -> list[dict[str, Any]]:
        """Return only fire-service records from a provider-grouped incident."""
        candidates = [{k: v for k, v in item.items() if k != "subitems"}]
        subitems = item.get("subitems") or []
        if isinstance(subitems, list):
            candidates.extend(x for x in subitems if isinstance(x, dict))
        return [
            candidate
            for candidate in candidates
            if cls._is_fire_service_item(candidate)
        ]

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_city(value: Any, postcode: str | None) -> str | None:
        """Strip a duplicated postcode prefix from provider city values."""
        city = str(value or "").strip()
        if not city:
            return None

        if postcode:
            pattern = rf"^{re.escape(postcode)}\s+"
            city = re.sub(pattern, "", city, flags=re.IGNORECASE).strip()

        # Defensive fallback for provider values such as "4411BT  Rilland".
        city = re.sub(r"^[1-9][0-9]{3}\s?[A-Z]{2}\s+", "", city, flags=re.IGNORECASE).strip()
        return city or None

    @staticmethod
    def _extract_units(message: str) -> list[str]:
        """Extract six-digit Dutch appliance/unit numbers from P2000 text."""
        return sorted(set(_VEHICLE_RE.findall(message)))

    @staticmethod
    def _normalize_location_code(value: Any) -> tuple[str | None, str | None]:
        """Split a real Dutch postcode from provider-specific location references."""
        raw = str(value or "").strip()
        if not raw:
            return None, None
        if _POSTCODE_RE.fullmatch(raw):
            return raw.replace(" ", "").upper(), None
        return None, raw

    @staticmethod
    def _extract_talkgroups(item: dict[str, Any]) -> list[str]:
        """Extract provider talkgroup/radio-channel hints when present.

        AlarmeringDroid does not consistently expose this today, so accept a
        small set of possible keys without making the field mandatory.
        """
        values: list[str] = []
        for key in ("gespreksgroep", "gespreksgroepen", "talkgroup", "talkgroups",
                    "radio_channel", "radio_channels"):
            value = item.get(key)
            if value in (None, ""):
                continue
            if isinstance(value, (list, tuple, set)):
                values.extend(str(entry).strip() for entry in value if str(entry).strip())
            else:
                values.append(str(value).strip())
        return sorted(set(values))

    @classmethod
    def _normalize(
        cls, item: dict[str, Any], received_at: str
    ) -> P2000Event | None:
        message = str(item.get("melding") or "").strip()
        if not message:
            return None
        capcodes = item.get("capcodes") or []
        if not isinstance(capcodes, list):
            capcodes = []
        postcode, location_reference = cls._normalize_location_code(item.get("postcode"))
        units = cls._extract_units(message)
        talkgroups = cls._extract_talkgroups(item)
        event_time = cls._event_time(item)
        return P2000Event(
            source=cls.source,
            external_id=str(item.get("id")) if item.get("id") is not None else None,
            event_time=event_time,
            received_at=received_at,
            message=message,
            human_message=str(item.get("tekstmelding") or "").strip() or None,
            latitude=cls._as_float(item.get("lat", item.get("latitude"))),
            longitude=cls._as_float(item.get("lon", item.get("longitude"))),
            city=cls._normalize_city(item.get("plaats"), postcode),
            street=str(item.get("straat") or "").strip() or None,
            postcode=postcode,
            location_reference=location_reference,
            priority=1 if str(item.get("prio1") or "") == "1" else None,
            grip=cls._as_int(item.get("grip")),
            capcodes=[x for x in capcodes if isinstance(x, dict)],
            units=units,
            talkgroups=talkgroups,
        )

    @staticmethod
    def _event_time(item: dict[str, Any]) -> str | None:
        """Convert dd-mm + HH:MM provider fields into a local ISO timestamp."""
        date_text = str(item.get("datum") or "").strip()
        time_text = str(item.get("tijd") or "").strip().split(" - ", 1)[0]
        if not date_text or not time_text:
            return None
        now = datetime.now().astimezone()
        try:
            parsed = datetime.strptime(
                f"{date_text}-{now.year} {time_text}", "%d-%m-%Y %H:%M"
            ).replace(tzinfo=now.tzinfo)
        except ValueError:
            return None
        # Around New Year the provider date has no year. Avoid assigning a
        # December alert to the next year when Home Assistant is in January.
        if (parsed - now).total_seconds() > 86400:
            parsed = parsed.replace(year=parsed.year - 1)
        return parsed.isoformat()