"""Conservative, side-effect-free checks for vehicle replacement discrepancies.

Only a *verified* live BrandweerRooster vehicle assignment for a station/function
may be passed here. A task name, P2000 callsign, historic REST refresh or
inferred vehicle number is not sufficient evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .replacement_vehicles import normalize_unit


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None


def evaluate_replacement(
    record: dict,
    *,
    bwr_station_id: int,
    bwr_vehicle_number: str,
    bwr_event_time: str,
    bwr_incident_id: str | int,
    bwr_verified_live: bool,
    p2000_vehicle_numbers: list[str] | None = None,
    p2000_event_time: str | None = None,
    p2000_correlated: bool = False,
) -> dict:
    """Assess one *active* mapping. This function never modifies state.

    P2000 confirmation means a *correlated*, contemporary alert explicitly
    contains the original vehicle. The consumer must independently verify that
    the alert and BWR incident are the same dispatch; this function will not
    infer correlation from shared vehicle digits alone.
    """
    base = {
        "action": "ignore",
        "reason": "unverified",
        "incident_id": bwr_incident_id,
        "station_id": record.get("station_id"),
        "original_vehicle_number": record.get("original_vehicle_number"),
        "replacement_vehicle_number": record.get("vehicle_number"),
    }
    if not bwr_verified_live or record.get("end_time") or bwr_incident_id is None:
        return base
    try:
        if int(record["station_id"]) != int(bwr_station_id):
            return {**base, "reason": "different_station"}
        original = normalize_unit(record["original_vehicle_number"])
        replacement = normalize_unit(record["vehicle_number"])
        observed = normalize_unit(bwr_vehicle_number)
    except (ValueError, TypeError, KeyError):
        return {**base, "reason": "invalid_vehicle"}
    event_time = _instant(bwr_event_time)
    starts = _instant(record.get("start_time"))
    if event_time is None or starts is None or event_time < starts:
        return {**base, "reason": "historical_or_undated"}
    if observed == replacement:
        return {**base, "reason": "replacement_confirmed", "observed_vehicle_number": observed}
    if observed != original:
        return {
            **base,
            "action": "notify",
            "reason": "third_vehicle",
            "observed_vehicle_number": observed,
        }

    # A BWR original number alone is insufficient: it can be the configured
    # vehicle even when a replacement responds. Require independent P2000 data.
    ptime = _instant(p2000_event_time)
    if not p2000_correlated or ptime is None or abs((ptime - event_time).total_seconds()) > 180:
        return {
            **base, "action": "notify", "reason": "original_unconfirmed",
            "observed_vehicle_number": observed,
        }
    try:
        p_units = {normalize_unit(unit) for unit in (p2000_vehicle_numbers or [])}
    except (ValueError, TypeError):
        return {**base, "action": "notify", "reason": "p2000_invalid"}
    if original not in p_units:
        return {
            **base, "action": "notify", "reason": "p2000_mismatch",
            "observed_vehicle_number": observed,
        }
    return {
        **base,
        "action": "clear",
        "reason": "bwr_and_p2000_confirmed",
        "observed_vehicle_number": observed,
    }
