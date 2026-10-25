"""Privacy-safe extraction of task P2000 configuration from web-rendered HTML.

BrandweerRooster's /api/v2/tasks/{id} currently omits the required P2000
message terms. The task *web page* contains them as server-rendered HTML.
This parser reads only the General Settings table; never emits raw HTML,
cookies, CSRF tokens, websocket tokens or unrelated page data.

A separate opt-in service tests whether OAuth bearer authentication also
works for this web page. Browser session cookies are never requested.
"""

from __future__ import annotations

from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urlsplit

MAX_HTML_BYTES = 400_000

_NUM = re.compile(r"^0[0-9]{5}$")
_SHORT_CODE = re.compile(r"^[A-Za-z0-9_-]{1,24}$")
_NAME = re.compile(r"^[A-Za-z0-9 ._()/-]{1,50}$")
_REQUIRED_LABEL = "Vereiste termen in P2000 bericht voor aanmaken incident"
_GMS_STATION = "GMS kazerne filter"
_GMS_TEAM = "GMS ploeg soortcode filter"


class _TaskGeneralTableParser(HTMLParser):
    """Capture bounded th/td pairs only inside the task's general-info card."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._div_depth = 0
        self._general_depth: int | None = None
        self._in_row = False
        self._cell_tag: str | None = None
        self._cell_text = ""
        self._cells: list[tuple[str, str]] = []
        self._rows_seen = 0
        self.fields: dict[str, list[str]] = {}
        self.task_page_marker = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == "body":
            self.task_page_marker = (
                attrs_map.get("data-controller") == "tasks"
                and attrs_map.get("data-action") == "show"
            )
        if tag == "div":
            self._div_depth += 1
            if attrs_map.get("id") == "general-info":
                self._general_depth = self._div_depth
        if self._general_depth is None or self._rows_seen >= 120:
            return
        if tag == "tr":
            self._in_row = True
            self._cells = []
        if tag in ("th", "td") and self._in_row:
            self._cell_tag = tag
            self._cell_text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag in ("th", "td") and self._in_row and self._cell_tag == tag:
            text = " ".join(self._cell_text.split())[:200]
            self._cells.append((tag, text))
            self._cell_tag = None
            self._cell_text = ""
        if tag == "tr" and self._in_row:
            self._in_row = False
            self._rows_seen += 1
            headings = [value for kind, value in self._cells if kind == "th"]
            values = [value for kind, value in self._cells if kind == "td"]
            if len(headings) == 1 and len(values) == 1:
                name = headings[0]
                if name in {"Naam", _REQUIRED_LABEL, _GMS_STATION, _GMS_TEAM}:
                    self.fields.setdefault(name, []).append(values[0])
            self._cells = []
        if tag == "div":
            if self._general_depth == self._div_depth:
                self._general_depth = None
            self._div_depth = max(0, self._div_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._cell_tag and len(self._cell_text) < 250:
            self._cell_text += data[:250]


def _one_value(fields: dict[str, list[str]], key: str) -> str | None:
    values = fields.get(key, [])
    if len(values) != 1:
        return None
    return values[0]


def _required_numbers(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [part.strip() for part in re.split(r"[,;\\s]+", value) if part.strip()]
    if len(parts) > 10 or not all(_NUM.fullmatch(part) for part in parts):
        return []
    return sorted(set(parts))


def parse_task_webpage_html(
    html: str,
    *,
    station_id: int | str,
    task_id: int | str,
    expected_task_name: str,
) -> dict[str, Any]:
    """Return only allowlisted task settings, never arbitrary HTML content."""
    base = {
        "station_id": str(station_id),
        "task_id": str(task_id),
        "task_name": expected_task_name,
        "probe_status": "not_a_verified_task_page",
        "html_task_page_marker": False,
        "task_name_matches_index": False,
        "required_p2000_vehicle_terms": [],
        "vehicle_number": None,
        "vehicle_mapping_status": "unverified",
        "gms_station_filter": None,
        "gms_team_type_filter": None,
        "settings_source": "server_rendered_task_webpage_general_info",
        "personal_data_returned": False,
        "raw_html_returned": False,
        "web_session_tokens_returned": False,
        "operational_vehicle_dispatch_verified": False,
    }
    if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_HTML_BYTES:
        return {**base, "probe_status": "html_absent_or_too_large"}
    parser = _TaskGeneralTableParser()
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, AssertionError):
        return {**base, "probe_status": "html_parse_failed"}
    base["html_task_page_marker"] = parser.task_page_marker
    if not parser.task_page_marker:
        return base

    name = _one_value(parser.fields, "Naam")
    base["task_name_matches_index"] = (
        isinstance(name, str)
        and _NAME.fullmatch(name) is not None
        and name == expected_task_name
    )
    if not base["task_name_matches_index"]:
        return {**base, "probe_status": "html_task_identity_mismatch"}

    required = _one_value(parser.fields, _REQUIRED_LABEL)
    station = _one_value(parser.fields, _GMS_STATION)
    team = _one_value(parser.fields, _GMS_TEAM)
    base["gms_station_filter"] = (
        station if station and _SHORT_CODE.fullmatch(station) else None
    )
    base["gms_team_type_filter"] = (
        team if team and _SHORT_CODE.fullmatch(team) else None
    )
    numbers = _required_numbers(required)
    base["required_p2000_vehicle_terms"] = numbers
    base["vehicle_number"] = numbers[0] if len(numbers) == 1 else None
    base["vehicle_mapping_status"] = (
        "one_configured_p2000_required_term"
        if len(numbers) == 1
        else "multiple_configured_p2000_required_terms"
        if len(numbers) > 1
        else "no_unambiguous_p2000_required_term"
    )
    base["probe_status"] = "task_html_settings_readable"
    return base


def task_web_url_allowed(raw_base_url: Any) -> bool:
    """Never send an OAuth token to any host other than the official BWR site."""
    if not isinstance(raw_base_url, str):
        return False
    candidate = raw_base_url.strip()
    if not candidate.startswith(("https://", "http://")):
        candidate = "https://" + candidate
    parts = urlsplit(candidate)
    return (
        parts.scheme == "https"
        and parts.hostname == "www.brandweerrooster.nl"
        and parts.username is None
        and parts.password is None
        and parts.port in (None, 443)
        and parts.path in ("", "/")
        and not parts.query and not parts.fragment
    )
