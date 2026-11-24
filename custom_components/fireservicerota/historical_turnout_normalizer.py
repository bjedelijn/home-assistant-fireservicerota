"""Prepare station-scoped observations from incident detail responses."""
from typing import Any

from .staffing_insights import _resolve_station
from .historical_turnout_store import _identifier, normalize_observation


def prepare_turnout_observation(payload: Any, incident_id: Any, groups: list,
                                authorized_station_ids: set, incident_station_ids: set) -> dict:
    """Fail closed on ambiguous group references or missing response lists.

    An explicit empty list is an observation, not proof of no physical turnout.
    Current group mappings do not establish historical membership validity.
    """
    expected = _identifier(incident_id)
    if expected is None or not isinstance(payload, dict) or _identifier(payload.get("id")) != expected:
        return {"status": "unexpected_incident"}
    allowed = {_identifier(v) for v in authorized_station_ids} - {None}
    relevant = {_identifier(v) for v in incident_station_ids} - {None}
    scope = allowed & relevant
    if not scope:
        return {"status": "outside_authorized_scope"}
    responses = payload.get("incident_responses")
    if not isinstance(responses, list):
        return {"status": "responses_unavailable"}
    known = {key: group for group in groups if isinstance(group, dict)
             if (key := _identifier(group.get("id"))) is not None}
    rows = []
    for response in responses:
        if not isinstance(response, dict):
            return {"status": "unexpected_response"}
        station = _resolve_station(response.get("group_id"), known)
        station_id = _identifier(station.get("station_id")) if station else None
        if station_id is None:
            return {"status": "unresolved_station"}
        if station_id not in allowed:
            continue
        if station_id not in scope:
            return {"status": "station_evidence_conflict"}
        rows.append({**{key: response.get(key) for key in (
            "membership_id", "user_id", "user_name", "status", "reported_status",
            "arrived_at_station", "on_duty")}, "station_id": station_id})
    try:
        clean = normalize_observation(rows)
    except ValueError:
        return {"status": "ambiguous_identity"}
    return {"status": "ready", "rows": clean, "station_scope": sorted(scope),
            "provider_response_count": len(responses)}
