"""Bounded, read-only P2000 task setting probe via the official web page.

The v2 task JSON endpoint omits P2000 filters seen on the server-rendered
BrandweerRooster task page. This one-shot diagnostic tests whether the existing
OAuth bearer token can also read that page, WITHOUT any browser session cookie.
Only allowlisted settings from the 'Algemeen' table are exposed. No raw HTML,
credentials, persons, response histories or automatic task-to-vehicle mapping.
"""

from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientTimeout

MAX_TASK_WEBPAGE_BYTES = 400_000
_OFFICIAL_HOST = "www.brandweerrooster.nl"
_VEHICLE_TERM = re.compile(r"0[0-9]{5}\Z")
_STATION_CODE = re.compile(r"[A-Z0-9_-]{1,24}\Z")
_TEAM_CODE = re.compile(r"[A-Za-z0-9_-]{1,24}\Z")
_LABEL_REQUIRED = "Vereiste termen in P2000 bericht voor aanmaken incident"
_LABEL_GMS_STATION = "GMS kazerne filter"
_LABEL_GMS_TEAM = "GMS ploeg soortcode filter"
_ALLOWED_LABELS = {
    "Naam", _LABEL_REQUIRED, _LABEL_GMS_STATION, _LABEL_GMS_TEAM,
}


def official_task_web_origin(raw_base_url: Any) -> str | None:
    """Refuse credentials to all hosts except the exact official HTTPS host."""
    if not isinstance(raw_base_url, str):
        return None
    value = raw_base_url.strip()
    if "://" not in value:
        value = "https://" + value
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != _OFFICIAL_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment
    ):
        return None
    return "https://" + _OFFICIAL_HOST


def classify_web_redirect(
    location: Any, *, station_id: str, task_id: str,
) -> str:
    """Classify a Location header without ever exposing its URL or query.

    This is intentionally a diagnostic only. Redirects are NEVER followed.
    In particular, Location may contain sensitive OAuth state or session data.
    """
    if not isinstance(location, str) or not location or len(location) > 2048:
        return "location_missing_or_unusable"
    try:
        target = urlsplit(location)
        if target.netloc and (
            target.scheme != "https"
            or target.hostname != _OFFICIAL_HOST
            or target.username is not None
            or target.password is not None
            or target.port not in (None, 443)
        ):
            return "external_or_untrusted_redirect"
    except ValueError:
        return "location_missing_or_unusable"

    path = target.path.rstrip("/")
    if path == f"/groups/{station_id}/tasks/{task_id}":
        return "same_task_page_redirect"
    if path in ("/users/sign_in", "/sign_in", "/login", "/sessions/new"):
        return "sign_in_redirect"
    if path.startswith(("/users/sign_in/", "/oauth/", "/auth/")):
        return "authentication_redirect"
    return "other_redirect"


def _numeric_required_terms(value: str | None) -> list[str]:
    """Only accept whole six-digit required terms, not numbers found in prose."""
    if not isinstance(value, str) or len(value) > 160:
        return []
    parts = [part for part in re.split(r"[,;\s]+", value.strip()) if part]
    if not 1 <= len(parts) <= 10:
        return []
    if not all(_VEHICLE_TERM.fullmatch(part) for part in parts):
        return []
    return sorted(set(parts))


class _TaskPageParser(HTMLParser):
    """Read only specific table cells in the top-level task general-info card."""

    def __init__(self, expected_station_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self._station_id = expected_station_id
        self.is_task_show_page = False
        self.station_breadcrumb_matches = False
        self._div_depth = 0
        self._general_depth: int | None = None
        self._row_active = False
        self._rows_seen = 0
        self._cell: str | None = None
        self._cell_text = ""
        self._row_cells: list[tuple[str, str]] = []
        self.fields: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == "body":
            self.is_task_show_page = (
                attrs_map.get("data-controller") == "tasks"
                and attrs_map.get("data-action") == "show"
            )
        if tag == "a":
            href = attrs_map.get("href")
            if isinstance(href, str):
                target = urlsplit(href)
                if target.path == f"/groups/{self._station_id}/tasks":
                    self.station_breadcrumb_matches = True
        if tag == "div":
            self._div_depth += 1
            if attrs_map.get("id") == "general-info":
                self._general_depth = self._div_depth
        if self._general_depth is None or self._rows_seen >= 100:
            return
        if tag == "tr":
            self._row_active = True
            self._row_cells = []
        if tag in ("th", "td") and self._row_active and self._cell is None:
            self._cell = tag
            self._cell_text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag in ("th", "td") and self._row_active and self._cell == tag:
            self._row_cells.append((tag, " ".join(self._cell_text.split())[:200]))
            self._cell = None
            self._cell_text = ""
        if tag == "tr" and self._row_active:
            self._row_active = False
            self._rows_seen += 1
            labels = [value for kind, value in self._row_cells if kind == "th"]
            values = [value for kind, value in self._row_cells if kind == "td"]
            if len(labels) == 1 and len(values) == 1 and labels[0] in _ALLOWED_LABELS:
                self.fields.setdefault(labels[0], []).append(values[0])
            self._row_cells = []
        if tag == "div":
            if self._general_depth == self._div_depth:
                self._general_depth = None
                self._row_active = False
                self._cell = None
            self._div_depth = max(0, self._div_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._cell is not None and len(self._cell_text) < 240:
            self._cell_text += data[:240]


def _unique_field(fields: dict[str, list[str]], label: str) -> str | None:
    values = fields.get(label) or []
    return values[0] if len(values) == 1 else None


def extract_task_webpage_p2000(
    html: str,
    *,
    station_id: str,
    task_id: str,
    task_name: str,
) -> dict[str, Any]:
    """Parse a verified single-task web page; return only safe filter values."""
    result = {
        "station_id": station_id,
        "task_id": task_id,
        "task_name": task_name,
        "probe_status": "not_an_authorized_task_settings_page",
        "task_page_identity_verified": False,
        "task_station_breadcrumb_verified": False,
        "gms_station_filter": None,
        "gms_team_type_filter": None,
        "required_p2000_terms": [],
        "vehicle_number": None,
        "vehicle_mapping_status": "unverified",
        "mapping_source": None,
        "raw_html_returned": False,
        "personal_data_returned": False,
        "operational_vehicle_dispatch_verified": False,
    }
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_TASK_WEBPAGE_BYTES:
        return {**result, "probe_status": "html_missing_or_too_large"}
    parser = _TaskPageParser(station_id)
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, AssertionError, TypeError):
        return {**result, "probe_status": "html_parse_failed"}
    result["task_station_breadcrumb_verified"] = parser.station_breadcrumb_matches
    if not parser.is_task_show_page or not parser.station_breadcrumb_matches:
        return result
    name = _unique_field(parser.fields, "Naam")
    if name != task_name:
        return {**result, "probe_status": "task_name_identity_mismatch"}
    result["task_page_identity_verified"] = True

    station = _unique_field(parser.fields, _LABEL_GMS_STATION)
    team = _unique_field(parser.fields, _LABEL_GMS_TEAM)
    if station and _STATION_CODE.fullmatch(station):
        result["gms_station_filter"] = station
    if team and _TEAM_CODE.fullmatch(team):
        result["gms_team_type_filter"] = team

    numbers = _numeric_required_terms(
        _unique_field(parser.fields, _LABEL_REQUIRED)
    )
    result["required_p2000_terms"] = numbers
    if len(numbers) == 1:
        result["vehicle_number"] = numbers[0]
        result["vehicle_mapping_status"] = "one_configured_required_numeric_term"
        result["mapping_source"] = "task_webpage_current_p2000_filter"
    elif len(numbers) > 1:
        result["vehicle_mapping_status"] = "multiple_required_numeric_terms"
    else:
        result["vehicle_mapping_status"] = "no_unambiguous_required_numeric_term"
    result["probe_status"] = "task_webpage_settings_readable"
    return result


async def async_probe_task_webpage(
    session: Any,
    *,
    base_url: str,
    access_token: str | None,
    station_id: str,
    task_id: str,
    task_name: str,
) -> dict[str, Any]:
    """One GET with OAuth to the fixed official host; no redirects or cookies."""
    base = {
        "station_id": station_id,
        "task_id": task_id,
        "task_name": task_name,
        "probe_status": "not_attempted",
        "api_get_attempted": False,
        "http_status": None,
        "redirect_destination_type": None,
        "authentication_method": "existing_oauth_bearer_only",
        "source": "one_authenticated_server_rendered_task_webpage_GET",
        "required_p2000_terms": [],
        "vehicle_number": None,
        "vehicle_mapping_status": "unverified",
        "mapping_source": None,
        "gms_station_filter": None,
        "gms_team_type_filter": None,
        "task_page_identity_verified": False,
        "task_station_breadcrumb_verified": False,
        "raw_html_returned": False,
        "personal_data_returned": False,
        "operational_vehicle_dispatch_verified": False,
        "brandweerrooster_modified": False,
        "local_storage_modified": False,
    }
    origin = official_task_web_origin(base_url)
    if origin is None:
        return {**base, "probe_status": "untrusted_brandweerrooster_base_url"}
    if not isinstance(access_token, str) or not access_token:
        return {**base, "probe_status": "oauth_access_token_unavailable"}
    if not (
        station_id.isdecimal() and task_id.isdecimal()
        and len(station_id) <= 15 and len(task_id) <= 15
    ):
        return {**base, "probe_status": "invalid_task_identifiers"}

    url = f"{origin}/groups/{station_id}/tasks/{task_id}"
    base["api_get_attempted"] = True
    try:
        async with session.get(
            url,
            params={"locale": "nl"},
            headers={
                "Accept": "text/html",
                "Authorization": f"Bearer {access_token}",
            },
            timeout=ClientTimeout(total=10),
            allow_redirects=False,
        ) as response:
            base["http_status"] = int(response.status)
            if 300 <= response.status <= 399:
                base["redirect_destination_type"] = classify_web_redirect(
                    response.headers.get("Location"),
                    station_id=station_id,
                    task_id=task_id,
                )
                return {**base, "probe_status": "redirect_to_web_session_or_other_page"}
            if response.status in (401, 403):
                return {**base, "probe_status": "oauth_not_authorized_for_webpage"}
            if response.status != 200:
                return {**base, "probe_status": "task_webpage_http_error"}
            content_type = response.headers.get("Content-Type", "").lower()
            if not (
                content_type.startswith("text/html")
                or content_type.startswith("application/xhtml+xml")
            ):
                return {**base, "probe_status": "unexpected_webpage_content_type"}

            # Streaming read with a hard cap; never buffer unlimited provider HTML.
            body = bytearray()
            async for part in response.content.iter_chunked(16384):
                body.extend(part)
                if len(body) > MAX_TASK_WEBPAGE_BYTES:
                    return {**base, "probe_status": "task_webpage_too_large"}
    except (ClientError, asyncio.TimeoutError, OSError, ValueError):
        return {**base, "probe_status": "task_webpage_request_failed"}

    try:
        html = body.decode("utf-8")
    except UnicodeDecodeError:
        return {**base, "probe_status": "task_webpage_invalid_encoding"}
    return {
        **base,
        **extract_task_webpage_p2000(
            html, station_id=station_id, task_id=task_id, task_name=task_name
        ),
    }
