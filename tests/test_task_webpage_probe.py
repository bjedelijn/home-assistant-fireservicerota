"""Tests for bounded OAuth-only BrandweerRooster task web page P2000 probing."""

import asyncio
from html import escape

import pytest

from custom_components.fireservicerota.task_webpage_probe import (
    MAX_TASK_WEBPAGE_BYTES,
    async_probe_task_webpage,
    extract_task_webpage_p2000,
    official_task_web_origin,
)


def make_html(
    *,
    station=194,
    task_name="TS-BT",
    p2000="042340",
    gms_station="HARDBG",
    gms_team="b-ts",
):
    # Intentionally resembles the real server-rendered page, but with
    # synthetic secrets. Never use real OAuth, session or person data here.
    return f"""<!DOCTYPE html><html lang="nl"><head>
<meta name="csrf-token" content="PRIVATE_CSRF_TOKEN"/>
<meta name="action-cable-url" content="wss://secret.example/PRIVATE_WEBSOCKET"/>
</head>
<body data-action="show" data-controller="tasks">
<a href="/groups/{station}/tasks?locale=nl">Taken</a>
<span>PRIVATE CREW NAME</span>
<div class="card" id="general-info">
<div class="card-body"><table>
<tr><th>Naam</th><td>{escape(task_name)}</td></tr>
<tr><th>GMS kazerne filter</th><td>{escape(gms_station)}</td></tr>
<tr><th>GMS ploeg soortcode filter</th><td>{escape(gms_team)}</td></tr>
<tr><th>Vereiste termen in P2000 bericht voor aanmaken incident</th>
<td>{escape(p2000)}</td></tr>
<tr><th>Uitgesloten termen in P2000 bericht voor aanmaken incident</th>
<td>Intrekken,041034</td></tr></table></div></div>
<div id="incidents">
<table><tr><th>Andere taak</th><td>049999</td></tr></table>
</div></body></html>"""


class FakeContent:
    def __init__(self, data):
        self.data = data

    async def iter_chunked(self, _maxsize):
        for index in range(0, len(self.data), 16384):
            yield self.data[index:index + 16384]


class FakeResponse:
    def __init__(self, status=200, body="", content_type="text/html; charset=utf-8"):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.content = FakeContent(body.encode("utf-8"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def execute(fake, *, url="https://www.brandweerrooster.nl",
            token="TEST_OAUTH_SECRET", station="194", task="7678",
            name="TS-BT"):
    return asyncio.run(async_probe_task_webpage(
        fake,
        base_url=url,
        access_token=token,
        station_id=station,
        task_id=task,
        task_name=name,
    ))


def test_realistic_html_extracts_exact_required_filter_and_gms():
    result = extract_task_webpage_p2000(
        make_html(), station_id="194", task_id="7678", task_name="TS-BT"
    )
    assert result["probe_status"] == "task_webpage_settings_readable"
    assert result["task_page_identity_verified"] is True
    assert result["task_station_breadcrumb_verified"] is True
    assert result["required_p2000_terms"] == ["042340"]
    assert result["vehicle_number"] == "042340"
    assert result["gms_station_filter"] == "HARDBG"
    assert result["gms_team_type_filter"] == "b-ts"
    assert result["mapping_source"] == "task_webpage_current_p2000_filter"
    assert result["operational_vehicle_dispatch_verified"] is False
    for secret in (
        "PRIVATE_CSRF_TOKEN", "PRIVATE_WEBSOCKET", "PRIVATE CREW NAME",
        "049999", "041034", "Intrekken", "secret.example",
    ):
        assert secret not in str(result)


def test_exact_origin_https_only():
    for good in (
        "https://www.brandweerrooster.nl",
        "https://www.brandweerrooster.nl/",
        "www.brandweerrooster.nl",
        "https://www.brandweerrooster.nl:443",
    ):
        assert official_task_web_origin(good) == "https://www.brandweerrooster.nl"
    for bad in (
        "http://www.brandweerrooster.nl",
        "https://evil.example",
        "https://www.brandweerrooster.nl.evil.example",
        "https://www.brandweerrooster.nl@evil.example",
        "https://admin@www.brandweerrooster.nl",
        "https://www.brandweerrooster.nl/api/v2",
        "https://www.brandweerrooster.nl?redirect=evil",
        "https://www.brandweerrooster.nl:5000",
        "ftp://www.brandweerrooster.nl",
        None, "", "https://www.brandweerrooster.nl:abc",
    ):
        assert official_task_web_origin(bad) is None


def test_request_is_one_get_with_oauth_only_and_no_redirects():
    session = FakeSession(FakeResponse(body=make_html()))
    result = execute(session)
    assert len(session.calls) == 1
    url, params = session.calls[0]
    assert url == "https://www.brandweerrooster.nl/groups/194/tasks/7678"
    assert params["params"] == {"locale": "nl"}
    assert params["headers"]["Authorization"] == "Bearer TEST_OAUTH_SECRET"
    assert params["headers"]["Accept"] == "text/html"
    assert params["allow_redirects"] is False
    assert "cookies" not in params
    assert result["http_status"] == 200
    assert result["probe_status"] == "task_webpage_settings_readable"
    assert result["vehicle_number"] == "042340"
    assert result["brandweerrooster_modified"] is False
    assert result["local_storage_modified"] is False
    assert result["raw_html_returned"] is False
    assert result["personal_data_returned"] is False
    assert "TEST_OAUTH_SECRET" not in str(result)


def test_login_redirect_stops_without_following():
    fake = FakeSession(FakeResponse(status=302, body=make_html()))
    result = execute(fake)
    assert len(fake.calls) == 1
    assert result["probe_status"] == "redirect_to_web_session_or_other_page"
    assert result["http_status"] == 302
    assert result["vehicle_number"] is None


@pytest.mark.parametrize("status,expected", [
    (401, "oauth_not_authorized_for_webpage"),
    (403, "oauth_not_authorized_for_webpage"),
    (404, "task_webpage_http_error"),
    (500, "task_webpage_http_error"),
])
def test_bad_http_status_sanitized(status, expected):
    fake = FakeSession(FakeResponse(status=status, body="PRIVATE SECRET"))
    result = execute(fake)
    assert result["probe_status"] == expected
    assert result["http_status"] == status
    assert "PRIVATE SECRET" not in str(result)


def test_login_page_with_http_200_is_not_treated_as_task_settings():
    fake = FakeSession(FakeResponse(body="<html><body>Inloggen</body></html>"))
    result = execute(fake)
    assert result["probe_status"] == "not_an_authorized_task_settings_page"
    assert result["vehicle_number"] is None


def test_wrong_station_breadcrumb_and_wrong_task_name_rejected():
    wrong_station = extract_task_webpage_p2000(
        make_html(station=500), station_id="194",
        task_id="7678", task_name="TS-BT"
    )
    assert wrong_station["vehicle_number"] is None
    assert wrong_station["task_page_identity_verified"] is False
    wrong_name = extract_task_webpage_p2000(
        make_html(task_name="TS"), station_id="194",
        task_id="7678", task_name="TS-BT"
    )
    assert wrong_name["probe_status"] == "task_name_identity_mismatch"
    assert wrong_name["vehicle_number"] is None


@pytest.mark.parametrize("value,expected", [
    ("042340", ["042340"]),
    ("042340, 042330", ["042330", "042340"]),
    ("042340 042330", ["042330", "042340"]),
    ("042340;042330", ["042330", "042340"]),
    ("P1 042340", []),
    ("042340 of 042330", []),
    ("Intrekken 042340", []),
    ("04234", []),
    ("0423400", []),
    ("", []),
])
def test_terms_are_strictly_whole_required_numeric_tokens(value, expected):
    result = extract_task_webpage_p2000(
        make_html(p2000=value), station_id="194",
        task_id="7678", task_name="TS-BT"
    )
    assert result["required_p2000_terms"] == expected
    if len(expected) != 1:
        assert result["vehicle_number"] is None


def test_ambiguous_duplicate_required_fields_never_guess():
    html = make_html().replace(
        "</table>",
        "<tr><th>Vereiste termen in P2000 bericht voor aanmaken incident</th>"
        "<td>042330</td></tr></table>",
        1,
    )
    result = extract_task_webpage_p2000(
        html, station_id="194", task_id="7678", task_name="TS-BT"
    )
    assert result["required_p2000_terms"] == []
    assert result["vehicle_number"] is None


def test_no_token_or_network_request_for_untrusted_base_or_missing_access_token():
    fake = FakeSession(FakeResponse(body=make_html()))
    result = execute(fake, url="https://brandweerrooster.nl.evil.example")
    assert result["probe_status"] == "untrusted_brandweerrooster_base_url"
    assert result["api_get_attempted"] is False
    assert fake.calls == []
    result = execute(fake, token=None)
    assert result["probe_status"] == "oauth_access_token_unavailable"
    assert result["api_get_attempted"] is False
    assert fake.calls == []


def test_wrong_response_type_or_large_page_does_not_return_html():
    fake = FakeSession(FakeResponse(
        body=make_html(), content_type="application/json"
    ))
    result = execute(fake)
    assert result["probe_status"] == "unexpected_webpage_content_type"
    assert result["vehicle_number"] is None

    oversized = "X" * (MAX_TASK_WEBPAGE_BYTES + 1000)
    fake = FakeSession(FakeResponse(body=oversized))
    result = execute(fake)
    assert result["probe_status"] == "task_webpage_too_large"
    assert result["vehicle_number"] is None
    assert "XXXXXXXX" not in str(result)


def test_webpage_settings_do_not_assume_actual_deployment():
    result = execute(FakeSession(FakeResponse(body=make_html())))
    assert result["operational_vehicle_dispatch_verified"] is False
    assert result["vehicle_mapping_status"] == "one_configured_required_numeric_term"
