"""Prealert safety and opt-in matching regression tests."""
from datetime import datetime, timezone
from types import SimpleNamespace

from custom_components.fireservicerota.p2000_prealerts import (
    build_prealert, configured_capcodes, matching_capcodes, is_fresh_live_event,
)


def event(*, capcodes=None, moment="2026-11-20T21:00:00+00:00", received=None):
    return SimpleNamespace(
        source="p2000_page",
        external_id="p2000_page:test",
        event_time=moment,
        received_at=received or moment,
        message="P1 Brand woning",
        priority=1,
        capcodes=capcodes if capcodes is not None else [{"capcode": "0611072"}],
    )


def test_explicit_capcodes_are_required():
    assert configured_capcodes("0611072, 0611073") == {"0611072", "0611073"}
    assert configured_capcodes("0611072;0611073") == {"0611072", "0611073"}
    assert configured_capcodes("") == set()
    assert configured_capcodes("0611072,invalid") == set()
    assert configured_capcodes("0611072,") == set()


def test_accepts_both_provider_capcode_field_names():
    assert matching_capcodes(event(capcodes=[{"code": "0611072"}]), {"0611072"}) == ["0611072"]
    assert matching_capcodes(event(), {"0611072"}) == ["0611072"]
    assert matching_capcodes(event(), {"0611073"}) == []


def test_generates_informational_event_not_personal_dispatch():
    now = datetime(2026, 11, 20, 21, 0, 20, tzinfo=timezone.utc)
    result = build_prealert(event(), {"0611072"}, now=now)
    assert result["status"] == "unconfirmed"
    assert result["personal_dispatch_confirmed"] is False


def test_drops_old_replayed_and_future_events():
    now = datetime(2026, 11, 20, 21, 10, tzinfo=timezone.utc)
    assert not is_fresh_live_event(event(), now=now)
    assert build_prealert(event(), {"0611072"}, now=now) is None
    assert build_prealert(event(moment="2026-11-20T21:11:00+00:00"), {"0611072"}, now=now) is None


def test_no_match_never_emits():
    now = datetime(2026, 11, 20, 21, 0, 20, tzinfo=timezone.utc)
    assert build_prealert(event(), {"0611073"}, now=now) is None
    assert build_prealert(event(moment=""), {"0611072"}, now=now) is None
