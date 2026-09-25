"""Local Dutch fire-service vehicle registry derived from public Brandbase pages."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from html.parser import HTMLParser
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from aiohttp import ClientError, ClientTimeout
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

_BASE_URL = "https://brandbase.hetbrandweerforum.nl"
_REGION_INDEX_URL = f"{_BASE_URL}/voertuigen/regios/"
_CACHE_KEY = "fireservicerota.vehicle_registry_nl"
_CACHE_VERSION = 1
_REFRESH_INTERVAL = timedelta(days=7)
_MIN_REGION_LINKS = 20
_USER_AGENT = (
    "HomeAssistant-FireServiceRota-Extended/1.2.0 "
    "(+https://github.com/bjedelijn/home-assistant-fireservicerota)"
)

_NUMERIC_CALLSIGN_RE = re.compile(r"^(?P<region>\d{2})-(?P<number>\d{4})$")
_STATION_RE = re.compile(r"^(?P<code>\d{2}-[0-9A-Z]+)\s+(?P<name>.+)$", re.IGNORECASE)
_PLATE_SUFFIX_RE = re.compile(
    r"\s*\(([A-Z0-9]{1,3}-){2}[A-Z0-9]{1,3}\)\s*$", re.IGNORECASE
)

_TYPE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"tankautospuit", re.IGNORECASE), "TS"),
    (re.compile(r"hulpverleningsvoertuig", re.IGNORECASE), "HV"),
    (re.compile(r"autoladder", re.IGNORECASE), "AL"),
    (re.compile(r"hoogwerker", re.IGNORECASE), "HW"),
    (re.compile(r"watertankwagen|\btankwagen\b", re.IGNORECASE), "WT"),
    (re.compile(r"haakarmvoertuig", re.IGNORECASE), "HA"),
    (re.compile(r"personeels?/materiaal(?:voertuig|wagen)", re.IGNORECASE), "PM"),
    (re.compile(r"dienstbus", re.IGNORECASE), "DB"),
    (re.compile(r"brandweervaartuig|waterongevallenvaartuig", re.IGNORECASE), "BRV"),
    (re.compile(r"natuurbrand", re.IGNORECASE), "NBT"),
)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def _type_code(vehicle_type: str) -> str | None:
    for pattern, code in _TYPE_RULES:
        if pattern.search(vehicle_type):
            return code
    return None


def _p2000_code(callsign: str) -> str | None:
    match = _NUMERIC_CALLSIGN_RE.fullmatch(callsign.strip())
    if not match:
        return None
    return f"{match.group('region')}{match.group('number')}"


class _RegionIndexParser(HTMLParser):
    """Extract current vehicle-region links from the Brandbase region index."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        absolute = urljoin(_BASE_URL, href)
        path = urlparse(absolute).path.rstrip("/") + "/"
        if "/voertuigen/regio/" not in path or path.endswith("/archief/"):
            return
        tail = path.split("/voertuigen/regio/", 1)[1].strip("/")
        if not tail or tail == "archief":
            return
        self.urls.add(f"{_BASE_URL}{path}")


class _RegionPageParser(HTMLParser):
    """Parse one Brandbase current-vehicles region page."""

    def __init__(self, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.region_title: str | None = None
        self.station_heading: str | None = None
        self.vehicles: list[dict[str, Any]] = []
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._in_li = False
        self._li_text: list[str] = []
        self._li_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h3"}:
            self._capture = tag
            self._buffer = []
        elif tag == "li" and self.station_heading:
            self._in_li = True
            self._li_text = []
            self._li_href = None
        elif tag == "a" and self._in_li:
            self._li_href = dict(attrs).get("href") or self._li_href

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)
        if self._in_li:
            self._li_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture == tag:
            text = _clean_text("".join(self._buffer))
            if tag == "h1":
                self.region_title = text or self.region_title
            elif tag == "h3":
                self.station_heading = text or None
            self._capture = None
            self._buffer = []
            return

        if tag == "li" and self._in_li:
            text = _clean_text("".join(self._li_text))
            if text and self.station_heading:
                parsed = self._parse_vehicle(text, self.station_heading, self._li_href)
                if parsed:
                    self.vehicles.append(parsed)
            self._in_li = False
            self._li_text = []
            self._li_href = None

    def _parse_vehicle(
        self, text: str, station_heading: str, href: str | None
    ) -> dict[str, Any] | None:
        parts = text.split(" ", 1)
        if len(parts) != 2:
            return None
        callsign, description = parts[0].strip(), _clean_text(parts[1])
        if not callsign or "-" not in callsign or not description:
            return None

        # Preserve alphanumeric callsigns for diagnostics. P2000 lookup only
        # gets a six-digit key for the normal NN-NNNN callsign form.
        if not re.fullmatch(r"[0-9A-Z]+-[0-9A-Z-]+", callsign, re.IGNORECASE):
            return None

        station_match = _STATION_RE.match(station_heading)
        station_code = station_match.group("code") if station_match else None
        station_name = (
            _clean_text(station_match.group("name")) if station_match else station_heading
        )
        vehicle_type = _PLATE_SUFFIX_RE.sub("", description).strip()
        source_url = urljoin(_BASE_URL, href) if href else self.source_url

        return {
            "callsign": callsign,
            "p2000_code": _p2000_code(callsign),
            "station_code": station_code,
            "station": station_name,
            "vehicle_type": vehicle_type,
            "vehicle_type_code": _type_code(vehicle_type),
            "raw_description": description,
            "source": "brandbase",
            "source_url": source_url,
        }


class BrandbaseVehicleRegistry:
    """Cache and resolve Dutch fire-service vehicles without bundling source data."""

    def __init__(self, hass) -> None:
        self._hass = hass
        self._session = async_get_clientsession(hass)
        self._store = Store(hass, _CACHE_VERSION, _CACHE_KEY)
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None
        self._cache: dict[str, Any] = {
            "schema_version": _CACHE_VERSION,
            "source": "brandbase",
            "updated_at": None,
            "regions": {},
            "vehicles": {},
        }
        self.last_attempt: str | None = None
        self.last_success: bool | None = None
        self.last_error: str | None = None
        self.last_region_count = 0
        self.last_vehicle_count = 0

    async def async_load(self) -> None:
        """Load the local Home Assistant storage cache."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._cache = stored
        self.last_region_count = len(self._cache.get("regions") or {})
        self.last_vehicle_count = sum(
            len(items) for items in (self._cache.get("vehicles") or {}).values()
            if isinstance(items, list)
        )

    @property
    def refresh_due(self) -> bool:
        """Return True when the local cache should be refreshed."""
        updated = _parse_dt(self._cache.get("updated_at"))
        if updated is None:
            return True
        now = datetime.now().astimezone()
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=now.tzinfo)
        return now - updated >= _REFRESH_INTERVAL

    def schedule_refresh_if_due(self) -> None:
        """Schedule a background refresh without delaying P2000 processing."""
        if not self.refresh_due:
            return
        if self._refresh_task is not None and not self._refresh_task.done():
            return
        self._refresh_task = self._hass.async_create_task(self.async_refresh())

    @property
    def status(self) -> dict[str, Any]:
        """Return compact cache diagnostics."""
        return {
            "source": "brandbase",
            "source_url": _REGION_INDEX_URL,
            "cache_mode": "home_assistant_storage",
            "refresh_interval_days": int(_REFRESH_INTERVAL.total_seconds() // 86400),
            "updated_at": self._cache.get("updated_at"),
            "last_attempt": self.last_attempt,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "region_count": self.last_region_count,
            "vehicle_count": self.last_vehicle_count,
            "refresh_due": self.refresh_due,
        }

    async def _fetch_text(self, url: str) -> str:
        headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        async with self._session.get(
            url,
            headers=headers,
            timeout=ClientTimeout(total=20),
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
            return await response.text(errors="replace")

    async def _region_urls(self) -> list[str]:
        html = await self._fetch_text(_REGION_INDEX_URL)
        parser = _RegionIndexParser()
        parser.feed(html)
        urls = sorted(parser.urls)
        if len(urls) < _MIN_REGION_LINKS:
            raise ValueError(
                f"Brandbase region index yielded only {len(urls)} current region links"
            )
        return urls

    @staticmethod
    def _region_key(url: str) -> str:
        tail = urlparse(url).path.rstrip("/").split("/")[-1]
        prefix = tail.split("-", 1)[0]
        return prefix if prefix.isdigit() else tail

    async def async_refresh(self) -> bool:
        """Refresh all current Brandbase region pages into local HA storage."""
        async with self._lock:
            self.last_attempt = _now_iso()
            try:
                urls = await self._region_urls()
            except (ClientError, TimeoutError, ValueError) as err:
                self.last_success = False
                self.last_error = str(err)
                _LOGGER.warning("Brandbase vehicle index refresh failed: %s", err)
                return False

            previous_regions = self._cache.get("regions") or {}
            refreshed_regions: dict[str, dict[str, Any]] = {}
            successful = 0
            errors: list[str] = []

            for url in urls:
                key = self._region_key(url)
                try:
                    html = await self._fetch_text(url)
                    parser = _RegionPageParser(url)
                    parser.feed(html)
                    records = self._dedupe_records(parser.vehicles)
                    if not records:
                        raise ValueError("no vehicle records parsed")
                    refreshed_regions[key] = {
                        "name": parser.region_title,
                        "source_url": url,
                        "updated_at": self.last_attempt,
                        "vehicles": records,
                    }
                    successful += 1
                except (ClientError, TimeoutError, ValueError) as err:
                    errors.append(f"{key}: {err}")
                    old = previous_regions.get(key)
                    if isinstance(old, dict):
                        refreshed_regions[key] = old
                await asyncio.sleep(0.15)

            # On a first install, avoid replacing an empty cache with a tiny or
            # challenge/interstitial-derived partial result.
            if successful < _MIN_REGION_LINKS and not previous_regions:
                self.last_success = False
                self.last_error = (
                    f"only {successful} Brandbase regions refreshed successfully"
                )
                return False

            vehicles = self._build_index(refreshed_regions)
            self._cache = {
                "schema_version": _CACHE_VERSION,
                "source": "brandbase",
                "updated_at": self.last_attempt,
                "regions": refreshed_regions,
                "vehicles": vehicles,
            }
            await self._store.async_save(self._cache)

            self.last_region_count = len(refreshed_regions)
            self.last_vehicle_count = sum(len(items) for items in vehicles.values())
            self.last_success = successful == len(urls)
            self.last_error = "; ".join(errors[:5]) if errors else None
            if errors:
                _LOGGER.warning(
                    "Brandbase vehicle cache refreshed partially: %s/%s regions; %s",
                    successful,
                    len(urls),
                    self.last_error,
                )
            else:
                _LOGGER.info(
                    "Brandbase vehicle cache refreshed: %s regions, %s vehicle keys",
                    self.last_region_count,
                    len(vehicles),
                )
            return True

    @staticmethod
    def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Collapse duplicate plate/detail entries while preserving ambiguities."""
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for raw in records:
            record = dict(raw)
            callsign = str(record.get("callsign") or "").upper()
            station = str(record.get("station") or "").casefold()
            if not callsign:
                continue
            key = (callsign, station)
            current = grouped.get(key)
            if current is None:
                grouped[key] = record
                continue
            current_desc = str(current.get("raw_description") or "")
            new_desc = str(record.get("raw_description") or "")
            current_has_plate = bool(_PLATE_SUFFIX_RE.search(current_desc))
            new_has_plate = bool(_PLATE_SUFFIX_RE.search(new_desc))
            if current_has_plate and not new_has_plate:
                grouped[key] = record
        return sorted(
            grouped.values(),
            key=lambda item: (
                str(item.get("callsign") or ""),
                str(item.get("station") or "").casefold(),
            ),
        )

    @staticmethod
    def _build_index(regions: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = {}
        for region_key, region in regions.items():
            for raw in region.get("vehicles") or []:
                if not isinstance(raw, dict):
                    continue
                p2000 = str(raw.get("p2000_code") or "").strip()
                if not p2000:
                    continue
                record = dict(raw)
                record["region_code"] = region_key.zfill(2) if region_key.isdigit() else region_key
                record["region"] = region.get("name")
                index.setdefault(p2000, []).append(record)
        for records in index.values():
            records.sort(
                key=lambda item: (
                    str(item.get("station") or "").casefold(),
                    str(item.get("vehicle_type") or "").casefold(),
                )
            )
        return index

    def resolve_unit(self, unit: str) -> dict[str, Any]:
        """Resolve one six-digit P2000 appliance number from the local cache."""
        key = re.sub(r"\D", "", str(unit or ""))
        candidates = [
            dict(item)
            for item in (self._cache.get("vehicles") or {}).get(key, [])
            if isinstance(item, dict)
        ]
        if not candidates:
            return {
                "unit": str(unit),
                "resolved": False,
                "source": "brandbase_cache",
                "confidence": None,
                "candidates": [],
            }

        unique = {
            (
                item.get("callsign"),
                item.get("station"),
                item.get("vehicle_type"),
            )
            for item in candidates
        }
        resolved = len(unique) == 1
        result: dict[str, Any] = {
            "unit": str(unit),
            "resolved": resolved,
            "source": "brandbase_cache",
            "confidence": "high" if resolved else "medium",
            "candidates": candidates,
        }
        if resolved:
            chosen = candidates[0]
            result.update(
                {
                    "callsign": chosen.get("callsign"),
                    "region_code": chosen.get("region_code"),
                    "region": chosen.get("region"),
                    "station_code": chosen.get("station_code"),
                    "station": chosen.get("station"),
                    "vehicle_type": chosen.get("vehicle_type"),
                    "vehicle_type_code": chosen.get("vehicle_type_code"),
                    "source_url": chosen.get("source_url"),
                }
            )
        return result

    def resolve_units(self, units: list[str]) -> list[dict[str, Any]]:
        """Resolve a list of P2000 appliance numbers from memory."""
        return [self.resolve_unit(unit) for unit in units]
