"""Read-only, privacy-minimized BWR task and P2000 appliance diagnostics.

No personal information, roster rows, addresses or raw incident payloads leave
this helper. Task identifiers describe BWR operational work, not physical turnout.
"""
from __future__ import annotations

from typing import Any

from .replacement_vehicles import normalize_unit


def _identifier(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    text = str(value).strip() if isinstance(value, (str, int)) else ""
    return text if text.isdecimal() and len(text) <= 12 else None


def task_evidence(incident: dict, task_index: dict) -> dict:
    """Inspect incident task identifiers and cached station-scoped task labels."""
    ids = []
    for value in (incident.get("task_ids") or [])[:20] if isinstance(incident.get("task_ids"), list) else []:
        ident = _identifier(value)
        if ident and ident not in ids:
            ids.append(ident)
    resolved = []
    for ident in ids:
        matches = [
            row for key, rows in (task_index or {}).items()
            if _identifier(key) == ident and isinstance(rows, list)
            for row in rows[:40] if isinstance(row, dict)
        ]
        safe = []
        for row in matches:
            station = _identifier(row.get("station_id"))
            name = row.get("name")
            if station and isinstance(name, str) and 0 < len(name) <= 60:
                safe.append((station, name))
        unique = sorted(set(safe))
        resolved.append({
            "task_id": ident,
            "station_tasks": [
                {"station_id": station, "task_name": name}
                for station, name in unique[:10]
            ],
            "resolution": "current_station_task_index" if unique else "unresolved",
        })
    requirements = incident.get("crew_requirements")
    count = len(requirements) if isinstance(requirements, list) else None
    return {
        "task_ids": ids,
        "task_count": len(ids),
        "resolved_tasks": resolved,
        "crew_requirements_present": requirements is not None,
        "crew_requirement_groups": count,
        "note": "Current task metadata does not prove historical configuration, dispatch or crew assignment.",
    }


def matched_p2000_evidence(matches: list, incident_id: Any) -> dict:
    """Use only a previously correlated match containing this exact BWR incident."""
    target = _identifier(incident_id)
    if not target:
        return {"status": "invalid_incident_id", "units": [], "sources": []}
    found = []
    for row in matches[:100] if isinstance(matches, list) else []:
        if not isinstance(row, dict):
            continue
        ids = {_identifier(i) for i in (row.get("incident_ids") or [])[:30]}
        if target not in ids:
            continue
        data = row.get("p2000_enrichment")
        if isinstance(data, dict):
            found.append(data)
    if not found:
        return {"status": "no_retained_correlation", "units": [], "sources": []}
    units = set()
    sources = set()
    for data in found:
        for unit in (data.get("units") or [])[:30]:
            try:
                units.add(normalize_unit(str(unit)))
            except (TypeError, ValueError):
                pass
        sources.update(
            s for s in (data.get("sources") or [])[:10]
            if s in {"p2000_page", "rtl", "online"}
        )
    return {
        "status": "correlated_p2000_alert",
        "units": sorted(units),
        "sources": sorted(sources),
        "note": "P2000 callsigns identify alerted units, not actual deployment or BWR task-to-vehicle assignment.",
    }
