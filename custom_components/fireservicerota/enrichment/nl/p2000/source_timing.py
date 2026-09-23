"""Build comparable Home Assistant arrival timing for practical incidents."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _p2000_source_key(source: str) -> tuple[str, str]:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(source or "").strip().lower()).strip("_")
    if normalized in {"online", "internet"}:
        return "p2000_online", "polling"
    if normalized in {"rtl", "rtl_sdr", "rtlsdr"}:
        return "p2000_rtl", "rtl_sdr"
    return f"p2000_{normalized or 'unknown'}", normalized or "unknown"


def build_source_timing(
    events: list[Any],
    incidents: list[dict[str, Any]],
    *,
    online_poll_interval_seconds: int | None = None,
) -> dict[str, Any]:
    """Compare when Home Assistant first observed BWR and each P2000 provider."""
    sources: dict[str, dict[str, Any]] = {}

    # BrandweerRooster is represented once for the complete practical group.
    bwr_observed: list[tuple[datetime, dict[str, Any]]] = []
    bwr_source_times: list[tuple[datetime, dict[str, Any]]] = []
    for incident in incidents:
        observed = _parse_datetime(incident.get("first_seen_at"))
        if observed is not None:
            bwr_observed.append((observed, incident))
        source_time = _parse_datetime(
            incident.get("start_time") or incident.get("created_at")
        )
        if source_time is not None:
            bwr_source_times.append((source_time, incident))

    if bwr_observed:
        observed_at, observed_incident = min(bwr_observed, key=lambda item: item[0])
        source_time = None
        source_incident = None
        if bwr_source_times:
            source_time, source_incident = min(
                bwr_source_times, key=lambda item: item[0]
            )
        first_seen_source = str(
            observed_incident.get("first_seen_source") or ""
        ).strip().lower()
        transport = (
            "websocket"
            if first_seen_source == "websocket"
            else "rest"
            if first_seen_source == "rest"
            else "unknown"
        )
        sources["brandweerrooster"] = {
            "observed_at": _iso(observed_at),
            "source_time": _iso(source_time),
            "transport": transport,
            "incident_id": observed_incident.get("id"),
            "source_incident_id": (
                source_incident.get("id") if source_incident is not None else None
            ),
        }

    # Keep every P2000 transport separate. received_at is the local HA arrival
    # timestamp; event_time is provider/source metadata and is not used to pick
    # the fastest source.
    grouped: dict[str, list[Any]] = {}
    source_meta: dict[str, tuple[str, str]] = {}
    for event in events:
        key, transport = _p2000_source_key(getattr(event, "source", ""))
        grouped.setdefault(key, []).append(event)
        source_meta[key] = (str(getattr(event, "source", "") or ""), transport)

    for key, source_events in grouped.items():
        observed_candidates = [
            (_parse_datetime(getattr(event, "received_at", None)), event)
            for event in source_events
        ]
        observed_candidates = [
            item for item in observed_candidates if item[0] is not None
        ]
        if not observed_candidates:
            continue
        observed_at, observed_event = min(
            observed_candidates, key=lambda item: item[0]
        )

        source_candidates = [
            (_parse_datetime(getattr(event, "event_time", None)), event)
            for event in source_events
        ]
        source_candidates = [item for item in source_candidates if item[0] is not None]
        source_time = (
            min(source_candidates, key=lambda item: item[0])[0]
            if source_candidates
            else None
        )
        provider_source, transport = source_meta[key]
        item = {
            "observed_at": _iso(observed_at),
            "source_time": _iso(source_time),
            "transport": transport,
            "provider_source": provider_source,
            "external_id": getattr(observed_event, "external_id", None),
        }
        if key == "p2000_online" and online_poll_interval_seconds is not None:
            item["poll_interval_seconds"] = int(online_poll_interval_seconds)
        sources[key] = item

    observed_sources: list[tuple[datetime, str]] = []
    for key, item in sources.items():
        observed = _parse_datetime(item.get("observed_at"))
        if observed is not None:
            observed_sources.append((observed, key))

    first_detected_source = None
    first_detected_at = None
    if observed_sources:
        first_detected_at, first_detected_source = min(
            observed_sources, key=lambda item: (item[0], item[1])
        )
        for key, item in sources.items():
            observed = _parse_datetime(item.get("observed_at"))
            item["delta_from_first_ms"] = (
                int(round((observed - first_detected_at).total_seconds() * 1000))
                if observed is not None
                else None
            )

    source_time_candidates: list[tuple[datetime, str]] = []
    for key, item in sources.items():
        source_time = _parse_datetime(item.get("source_time"))
        if source_time is not None:
            source_time_candidates.append((source_time, key))

    earliest_source_time = None
    earliest_source_time_source = None
    if source_time_candidates:
        earliest_source_time, earliest_source_time_source = min(
            source_time_candidates, key=lambda item: (item[0], item[1])
        )
        for item in sources.values():
            source_time = _parse_datetime(item.get("source_time"))
            item["source_time_delta_from_earliest_ms"] = (
                int(round((source_time - earliest_source_time).total_seconds() * 1000))
                if source_time is not None
                else None
            )

    return {
        "comparison_basis": "home_assistant_observed_at",
        "first_detected_source": first_detected_source,
        "first_detected_at": _iso(first_detected_at),
        "earliest_source_time_source": earliest_source_time_source,
        "earliest_source_time": _iso(earliest_source_time),
        "sources": sources,
    }
