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
    def _expand(item: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the main alert plus provider-grouped related subitems."""
        out = [{k: v for k, v in item.items() if k != "subitems"}]
        subitems = item.get("subitems") or []
        if isinstance(subitems, list):
            out.extend(x for x in subitems if isinstance(x, dict))
        return out

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
        postcode = str(item.get("postcode") or "").strip() or None
        units = cls._extract_units(message)
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
            priority=1 if str(item.get("prio1") or "") == "1" else None,
            grip=cls._as_int(item.get("grip")),
            capcodes=[x for x in capcodes if isinstance(x, dict)],
            units=units,
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