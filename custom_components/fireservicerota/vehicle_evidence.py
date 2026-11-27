"""Privacy-minimized inspection of BrandweerRooster vehicle fields.

A service can return this summary for a chosen incident without exposing
member names, responses, GPS, token information or the full incident body.
Finding a number here is diagnostics, *not* proof of vehicle deployment.
"""
from __future__ import annotations

from typing import Any
from .replacement_vehicles import normalize_unit

_VEHICLE_KEYS = frozenset({
    "vehicle_number", "vehicle_numbers", "vehicle_callsign",
    "callsign", "unit_number", "unit_numbers",
    "dispatched_vehicle", "dispatched_vehicles",
    "incident_vehicles", "vehicle_assignments",
    "vehicles", "voertuig", "voertuignummer",
})
_CONTEXT_KEYS = frozenset({"station_id", "group_id", "task_id", "vehicle_function"})
_MAX_DEPTH = 5
_MAX_NODES = 500
_MAX_RESULTS = 30


def incident_vehicle_evidence(incident: Any) -> dict:
    """Return names of likely vehicle fields, and only exact six-digit units.

    Do not use this diagnostic response to trigger replacement changes.
    """
    found: list[dict] = []
    visited = 0

    def walk(value: Any, path: str, depth: int) -> None:
        nonlocal visited
        visited += 1
        if visited > _MAX_NODES or depth > _MAX_DEPTH or len(found) >= _MAX_RESULTS:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str) or len(found) >= _MAX_RESULTS:
                    continue
                lower = key.lower()
                subpath = f"{path}.{key}" if path else key
                if lower in _VEHICLE_KEYS:
                    numbers: set[str] = set()

                    def collect(raw: Any) -> None:
                        if isinstance(raw, (str, int)):
                            try:
                                numbers.add(normalize_unit(str(raw)))
                            except ValueError:
                                pass
                        elif isinstance(raw, list):
                            for v in raw[:30]:
                                collect(v)
                        elif isinstance(raw, dict):
                            for field in ("vehicle_number", "callsign", "unit_number", "voertuignummer"):
                                if field in raw:
                                    collect(raw[field])

                    collect(item)
                    found.append({"path": subpath[:150], "unit_numbers": sorted(numbers)[:20]})
                if isinstance(item, (list, dict)):
                    walk(item, subpath, depth + 1)
        elif isinstance(value, list):
            for item in value[:30]:
                walk(item, path + "[]", depth + 1)

    walk(incident, "", 0)
    return {
        "incident_id": incident.get("id") if isinstance(incident, dict) else None,
        "vehicle_fields": found,
        "fields_found": len(found),
        "truncated": visited > _MAX_NODES or len(found) >= _MAX_RESULTS,
        "note": "Diagnostic evidence only; a callsign does not prove deployment.",
    }
