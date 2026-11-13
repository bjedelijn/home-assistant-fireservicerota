"""Fail-closed presentation labels for task-based firefighter fairness views.

No static task-to-vehicle registry: P2000 filter terms are not proof of a
physical deployment. The caller must separately validate a current unique
station/task/vehicle association. This module never fetches or changes data.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_NUMBER = re.compile(r"0[0-9]{5}\Z")


def _id(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        n = int(value)
        return str(n) if n > 0 else None
    return None


def _unit(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    compact = value.strip().replace("-", "")
    return compact if _NUMBER.fullmatch(compact) else None


def _label(unit: str) -> str:
    return unit[:2] + "-" + unit[2:]


def describe_task_vehicle(
    *,
    station_id: int | str,
    task_id: int | str,
    task_name: str,
    verified_mapping: Mapping[str, Any] | None = None,
    active_replacements: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a human-readable display label from *verified* source context.

    A task P2000 required-word filter alone is not a verified mapping.
    `verified_mapping` must be constructed by a later reviewed adapter
    from a current station-scoped authoritative task/vehicle mapping.
    `active_replacements` must come from the local ReplacementVehicleStore.
    """
    station, task = _id(station_id), _id(task_id)
    name = task_name.strip() if isinstance(task_name, str) else ""
    if station is None or task is None or not name or len(name) > 40:
        raise ValueError("Station, task and a short task name required")
    # Never display arbitrary user strings inside an incident-facing label.
    if not re.fullmatch(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 _/-]{0,39}", name):
        raise ValueError("Task name contains unsupported characters")

    base = {
        "station_id": station,
        "task_id": task,
        "task_name": name,
        "display_label": name,
        "original_vehicle_number": None,
        "display_vehicle_number": None,
        "vehicle_mapping_verified": False,
        "replacement_applied": False,
        "display_status": "task_only_vehicle_unverified",
    }
    if not isinstance(verified_mapping, Mapping):
        return base

    if (
        _id(verified_mapping.get("station_id")) != station
        or _id(verified_mapping.get("task_id")) != task
        or verified_mapping.get("verified_current") is not True
        or verified_mapping.get("unique_task_vehicle_association") is not True
        or verified_mapping.get("source") != "verified_current_station_task_vehicle"
    ):
        return base

    original = _unit(verified_mapping.get("vehicle_number"))
    if original is None:
        return base

    matches = []
    if active_replacements is not None:
        if not isinstance(active_replacements, Sequence) or isinstance(active_replacements, (str, bytes)):
            return {**base, "display_status": "replacement_input_invalid"}
        for record in active_replacements:
            if not isinstance(record, Mapping):
                return {**base, "display_status": "replacement_input_invalid"}
            if (
                _id(record.get("station_id")) == station
                and _unit(record.get("original_vehicle_number")) == original
                and not record.get("end_time")
            ):
                candidate = _unit(record.get("vehicle_number"))
                if candidate is None or candidate == original:
                    return {**base, "display_status": "replacement_input_invalid"}
                matches.append(candidate)

    if len(matches) > 1:
        return {**base, "display_status": "ambiguous_active_replacement"}

    effective = matches[0] if matches else original
    label = name + " " + _label(effective)
    return {
        **base,
        "display_label": label,
        "original_vehicle_number": _label(original),
        "display_vehicle_number": _label(effective),
        "vehicle_mapping_verified": True,
        "replacement_applied": bool(matches),
        "display_status": "verified_replacement" if matches else "verified_original_vehicle",
    }
