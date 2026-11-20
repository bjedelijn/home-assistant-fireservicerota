"""Pure checks for optional early P2000 alerts.

An early alert is information, NOT a personal BrandweerRooster dispatch.
It must never bypass the user's existing Home Assistant night/TTS conditions.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

_CAPCODE_RE = re.compile(r"^[0-9]{7}$")


def configured_capcodes(value: str) -> set[str]:
    """Return an explicit list of seven-digit capcodes (fail closed)."""
    values = [v.strip() for v in str(value or "").replace(";", ",").split(",")]
    if not values or any(not _CAPCODE_RE.fullmatch(v) for v in values):
        return set()
    return set(values)


def matching_capcodes(event: Any, selected: set[str]) -> list[str]:
    """Read either normalized API 'capcode' or p2000.page 'code' fields."""
    if not selected:
        return []
    found = set()
    for row in getattr(event, "capcodes", []) or []:
        if isinstance(row, dict):
            code = str(row.get("capcode") or row.get("code") or "").strip()
            if code in selected:
                found.add(code)
    return sorted(found)


def is_fresh_live_event(event: Any, *, now: datetime | None = None) -> bool:
    """Reject stale/replayed alerts, future timestamps and missing times."""
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        return False
    received = getattr(event, "received_at", None)
    event_time = getattr(event, "event_time", None)
    if not isinstance(received, str) or not isinstance(event_time, str):
        return False
    try:
        recv = datetime.fromisoformat(received.replace("Z", "+00:00"))
        occurred = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
    except ValueError:
        return False
    if recv.tzinfo is None or occurred.tzinfo is None:
        return False
    age = (observed - occurred).total_seconds()
    transport_delay = (recv - occurred).total_seconds()
    return -15 <= age <= 120 and -15 <= transport_delay <= 120


def build_prealert(event: Any, capcodes: set[str], *, now: datetime | None = None) -> dict | None:
    """Return a safe, informational event payload or None."""
    match = matching_capcodes(event, capcodes)
    if not match or not is_fresh_live_event(event, now=now):
        return None
    if not getattr(event, "external_id", None):
        return None
    return {
        "source": getattr(event, "source", None),
        "external_id": event.external_id,
        "event_time": event.event_time,
        "received_at": event.received_at,
        "message": event.message,
        "priority": getattr(event, "priority", None),
        "capcodes": match,
        "status": "unconfirmed",
        "personal_dispatch_confirmed": False,
    }
