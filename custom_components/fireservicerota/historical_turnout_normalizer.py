"""Prepare station-scoped observations from incident detail responses."""
from typing import Any
import re

from .staffing_insights import _resolve_station
from .historical_turnout_store import _identifier, normalize_observation


def normalize_requirement_evidence(payload: dict) -> list | None:
    """Preserve provider counts without inferring station or vehicle scope."""
    warnings = payload.get("warning_statuses")
    if not isinstance(warnings, list):
        return None
    def token(value):
        return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_ /+-]{0,63}", value) else None
    def count(value):
        return value if type(value) is int and value >= 0 else None
    result = []
    for warning in warnings:
        if not isinstance(warning, dict) or not isinstance(warning.get("skill_statuses"), list):
            return None
        skills = []
        for skill in warning["skill_statuses"]:
            if not isinstance(skill, dict) or _identifier(skill.get("skill_id")) is None:
                return None
            members = skill.get("available_memberships")
            skills.append({
                "skill_id": _identifier(skill["skill_id"]),
                "short_code": token(skill.get("short_code")),
                "minimum": count(skill.get("minimum")),
                "buffer": count(skill.get("buffer")),
                "assigned_count": count(skill.get("assigned_count")),
                "available_reference_count": len(members) if isinstance(members, list) else None,
                "level": token(skill.get("level")),
            })
        result.append({"service_level": token(warning.get("service_level")),
                       "scope_verified": False, "skills": skills})
    return result


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
    assignments = payload.get("incident_skill_assignments")
    codes = {}
    for warning in payload.get("warning_statuses") or []:
        if not isinstance(warning, dict):
            continue
        for skill in warning.get("skill_statuses") or []:
            if isinstance(skill, dict) and (key := _identifier(skill.get("skill_id"))) is not None:
                label = skill.get("short_code")
                if isinstance(label, str) and label:
                    codes.setdefault(key, set()).add(label)
    # Positive membership evidence only; absence is not proof of no qualifications.
    available = {}
    warnings = payload.get("warning_statuses")
    for warning in warnings if isinstance(warnings, list) else []:
        if not isinstance(warning, dict):
            continue
        skills = warning.get("skill_statuses")
        for skill in skills if isinstance(skills, list) else []:
            if not isinstance(skill, dict):
                continue
            skill_id = _identifier(skill.get("skill_id"))
            members = skill.get("available_memberships")
            if skill_id is None or not isinstance(members, list):
                continue
            for member in members:
                if not isinstance(member, dict):
                    continue
                membership = _identifier(member.get("membership_id", member.get("id")))
                if membership is None:
                    continue
                matches = [response for response in responses if _identifier(response.get("membership_id")) == membership]
                if len(matches) != 1:
                    continue
                if member.get("user_id") is not None and _identifier(member.get("user_id")) != _identifier(matches[0].get("user_id")):
                    continue
                available.setdefault(membership, set()).add(skill_id)
    for row in rows:
        ids = available.get(_identifier(row.get("membership_id")))
        if ids:
            row["available_skill_ids"] = sorted(ids)
            row["available_skill_codes"] = {key: next(iter(codes[key])) for key in ids if len(codes.get(key, set())) == 1}
    if isinstance(assignments, list):
        for row in rows:
            membership = _identifier(row.get("membership_id"))
            user = _identifier(row.get("user_id"))
            if membership is None or user is None:
                continue
            matches = [response for response in responses if _identifier(response.get("membership_id")) == membership]
            if len(matches) != 1:
                continue
            ids = set()
            for assignment in assignments:
                if not isinstance(assignment, dict) or _identifier(assignment.get("membership_id")) != membership or _identifier(assignment.get("user_id")) != user:
                    continue
                skills = assignment.get("skill_ids")
                if isinstance(skills, list):
                    ids.update(v for x in skills if (v := _identifier(x)) is not None)
            row["assigned_skill_ids"] = sorted(ids)
            row["assigned_skill_codes"] = {key: next(iter(codes[key])) for key in ids if len(codes.get(key, set())) == 1}
    try:
        clean = normalize_observation(rows)
    except ValueError:
        return {"status": "ambiguous_identity"}
    return {"status": "ready", "rows": clean, "station_scope": sorted(scope),
            "provider_response_count": len(responses),
            "requirement_evidence": normalize_requirement_evidence(payload)}
