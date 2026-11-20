"""Optional p2000.page live WebSocket receiver (user-provided API subscription).

No shared feed, replay announcements, or API secrets in diagnostics.
The connection is kept in Home Assistant's process and receives only Brandweer.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Callable

from aiohttp import ClientError, WSMsgType, WSServerHandshakeError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .model import P2000Event

_LOGGER = logging.getLogger(__name__)
_WS_ENDPOINT = "wss://api.p2000.page/api-"
_UNIT_RE = re.compile(r"(?<![0-9])[0-9]{6}(?![0-9])")
_REGIONS_RE = re.compile(r"^(?:0[1-9]|1[0-9]|2[0-5])(?:~(?:0[1-9]|1[0-9]|2[0-5]))*$")
_MAX_QUEUE = 500
_STOP_CLOSE_CODES = {4401, 4403}
_RATE_LIMIT_CLOSE_CODE = 4429


def valid_regions(value: str) -> bool:
    """Only explicit Dutch P2000 safety region codes, not URL fragments."""
    return bool(_REGIONS_RE.fullmatch(str(value))) and len(str(value).split("~")) == len(set(str(value).split("~")))


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _json_text(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None
    return value


def normalize_page_event(item: Any, received_at: str) -> P2000Event | None:
    """Normalize one provider payload without assuming vehicles are complete."""
    if not isinstance(item, dict):
        return None
    if str(item.get("dienst", "")).strip().casefold() != "brandweer":
        return None
    uid = item.get("uid")
    message = item.get("melding")
    if not isinstance(uid, str) or not uid.strip() or not isinstance(message, str) or not message.strip():
        return None
    timestamp = item.get("timestamp")
    event_time = None
    try:
        if timestamp not in (None, ""):
            event_time = datetime.fromtimestamp(int(timestamp), timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    lat, lon = None, None
    raw_geo = str(item.get("latlong") or "").replace(";", ",").split(",")
    if len(raw_geo) == 2:
        lat, lon = _as_float(raw_geo[0]), _as_float(raw_geo[1])
        if lat is not None and not (-90 <= lat <= 90):
            lat = None
        if lon is not None and not (-180 <= lon <= 180):
            lon = None
    raw_capcodes = _json_text(item.get("capcodes_json"))
    capcodes = []
    if isinstance(raw_capcodes, list):
        for row in raw_capcodes[:100]:
            if isinstance(row, dict):
                capcodes.append(row)
            elif isinstance(row, (str, int)):
                capcodes.append({"code": str(row)})
    if not capcodes:
        capcodes = [{"code": value} for value in str(item.get("capcodes") or "").split()[:100]]
    raw_units = _json_text(item.get("voertuigen_json"))
    units = set(_UNIT_RE.findall(message))
    if isinstance(raw_units, list):
        for row in raw_units[:100]:
            if isinstance(row, dict):
                for field in ("nummer", "number", "voertuig", "unit"):
                    units.update(_UNIT_RE.findall(str(row.get(field) or "")))
            else:
                units.update(_UNIT_RE.findall(str(row)))
    priority = None
    try:
        value = item.get("prio")
        if value not in (None, ""):
            priority = int(value)
    except (TypeError, ValueError):
        pass
    grip = None
    try:
        value = item.get("grip")
        if value not in (None, ""):
            grip = int(value)
    except (TypeError, ValueError):
        pass
    return P2000Event(
        source="p2000_page",
        external_id=f"p2000_page:{uid.strip()}",
        event_time=event_time,
        received_at=received_at,
        message=message.strip(),
        human_message=message.strip(),
        latitude=lat,
        longitude=lon,
        city=str(item.get("plaats") or "").strip() or None,
        street=str(item.get("locatie") or "").strip() or None,
        priority=priority,
        grip=grip,
        capcodes=capcodes,
        units=sorted(units),
    )


class P2000PageWebsocketProvider:
    """Single, bounded and restartable WebSocket client for p2000.page."""

    source = "p2000_page"

    def __init__(self, hass, *, api_key: str, regions: str = "06", on_event: Callable[[], None] | None = None) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("p2000.page requires an API key")
        if not valid_regions(regions):
            raise ValueError("Invalid p2000.page region filter")
        self._session = async_get_clientsession(hass)
        self._api_key = api_key.strip()
        self._regions = regions
        self._on_event = on_event
        self._pending: deque[P2000Event] = deque(maxlen=_MAX_QUEUE)
        self._task: asyncio.Task | None = None
        self._ws = None
        self._seen: deque[str] = deque(maxlen=1000)
        self._seen_set: set[str] = set()
        self._stop = False
        self._received = 0
        self.last_poll_at: str | None = None
        self.last_poll_success: bool | None = None
        self.last_error: str | None = None
        self.last_result_count = 0
        self.provider_debug: dict[str, Any] = {}
        self._status("disconnected")

    def _status(self, connection: str) -> None:
        self.provider_debug = {
            "transport": "websocket",
            "connection": connection,
            "regions": self._regions,
            "service": "brandweer",
            "received_count": self._received,
            "pending_events": len(self._pending),
            "queue_capacity": _MAX_QUEUE,
            # Never include endpoint, API key, connection exception repr, or raw message.
        }

    def _accept(self, item: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        event = normalize_page_event(item, now)
        if event is None or event.external_id is None:
            return
        if event.external_id in self._seen_set:
            return
        if len(self._seen) == self._seen.maxlen:
            self._seen_set.discard(self._seen[0])
        self._seen.append(event.external_id)
        self._seen_set.add(event.external_id)
        self._pending.append(event)
        self._received += 1
        self._status("connected")
        if self._on_event is not None:
            self._on_event()

    async def async_start(self) -> None:
        if self._task is None or self._task.done():
            self._stop = False
            self._task = asyncio.create_task(self._run(), name="fireservicerota_p2000_page_ws")

    async def async_stop(self) -> None:
        self._stop = True
        if self._ws is not None:
            await self._ws.close()
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._status("stopped")

    async def _run(self) -> None:
        delay = 1
        url = f"{_WS_ENDPOINT}/r/{self._regions}/d/brandweer"
        # p2000.page documents X-Api-Key as an alternative to embedding it in the URL.
        headers = {"X-Api-Key": self._api_key}
        try:
            while not self._stop:
                close_code = None
                try:
                    async with self._session.ws_connect(
                        url, headers=headers, heartbeat=40,
                        max_msg_size=1024 * 1024,
                    ) as ws:
                        self._ws = ws
                        self.last_poll_success = True
                        self.last_error = None
                        self._status("connected")
                        delay = 1
                        async for message in ws:
                            if message.type == WSMsgType.TEXT:
                                try:
                                    envelope = json.loads(message.data)
                                except (TypeError, ValueError):
                                    continue
                                if not isinstance(envelope, dict):
                                    continue
                                kind = envelope.get("type")
                                if kind == "melding":
                                    self._accept(envelope.get("melding"))
                                elif kind == "laatste":
                                    # Replay is intentionally ignored: never announce history as live.
                                    continue
                                elif kind == "fout":
                                    self.last_poll_success = False
                                    self.last_error = "provider_error"
                            elif message.type in (WSMsgType.CLOSED, WSMsgType.ERROR, WSMsgType.CLOSE):
                                break
                        close_code = ws.close_code
                except asyncio.CancelledError:
                    raise
                except WSServerHandshakeError as err:
                    self.last_poll_success = False
                    if err.status in (401, 403):
                        self.last_error = "authorization_or_plan_denied"
                        self._status("configuration_error")
                        return
                    if err.status == 429:
                        delay = max(delay, 120)
                        self.last_error = "rate_limited"
                    else:
                        self.last_error = "connection_failed"
                except (ClientError, TimeoutError, OSError, ValueError):
                    # Do not log provider exception: URLs and auth details may be embedded.
                    self.last_poll_success = False
                    self.last_error = "connection_failed"
                finally:
                    self._ws = None
                    if self.last_error == "authorization_or_plan_denied":
                        self._status("configuration_error")
                    elif self.last_error == "rate_limited":
                        self._status("rate_limited")
                    else:
                        self._status("disconnected")
                if self._stop:
                    break
                if close_code in _STOP_CLOSE_CODES:
                    self.last_poll_success = False
                    self.last_error = "authorization_or_plan_denied"
                    self._status("configuration_error")
                    return
                if close_code == _RATE_LIMIT_CLOSE_CODE:
                    delay = max(delay, 120)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30) if delay < 120 else 120
        except asyncio.CancelledError:
            raise

    async def async_fetch(self) -> list[P2000Event]:
        """Drain ready WebSocket events for normal manager correlation."""
        self.last_poll_at = datetime.now(timezone.utc).isoformat()
        events = list(self._pending)
        self._pending.clear()
        self.last_result_count = len(events)
        self._status("connected" if self._ws is not None else "disconnected")
        return events
