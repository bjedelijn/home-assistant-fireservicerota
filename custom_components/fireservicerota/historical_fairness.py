"""Compact, identity-safe historical fairness evidence and role profiles.

Only the latest fairness proposal per distinct incident counts once. Proposal
labels must resolve uniquely to an API membership at one unambiguous station;
otherwise no person-level evidence is imported. Nothing is a proven turnout or
an estimate of the BrandweerRooster scheduling algorithm.
"""

from __future__ import annotations

import re
from typing import Any

MAX_HISTORY_RECORDS = 100


def _id(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    result = str(value).strip()
    return result if result and result.isdecimal() else None


def _label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _name_key(value: Any) -> str:
    return _label(value).casefold()


def select_retained_history_ids(
    history: list[dict[str, Any]], *, offset: int, limit: int,
) -> dict[str, Any]:
    """Select one bounded chronological page of Home Assistant's closed history."""
    if not isinstance(offset, int) or not 0 <= offset <= 24:
        raise ValueError("offset must be between 0 and 24")
    if not isinstance(limit, int) or not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    ids = [
        str(incident["id"])
        for incident in history
        if isinstance(incident, dict) and _id(incident.get("id")) is not None
    ]
    stop = offset + limit
    return {
        "ids": ids[offset:stop],
        "offset": offset,
        "available_retained_incidents": len(ids),
        "next_offset": min(stop, len(ids)) if stop < len(ids) else None,
    }


def summarize_incident_for_history(
    analysis: dict[str, Any], station_id: int | str,
) -> dict[str, Any]:
    """Convert one full audit response into minimal membership-linked evidence.

    A proposal without a station reference may only be attributed when every
    responding group belongs unambiguously to exactly the requested station.
    Matching by a display name is acceptable *only within that incident* when
    there is exactly one membership corresponding to that display name.
    """
    incident_id = _id(analysis.get("incident_id"))
    requested = _id(station_id)
    if not incident_id or not requested:
        raise ValueError("incident_id and station_id must be numeric")

    def skip(reason: str) -> dict[str, Any]:
        return {"incident_id": incident_id, "status": "skipped", "reason": reason}

    if analysis.get("audit_complete") is not True:
        return skip("audit_incomplete")
    if not analysis.get("fairness_suggestion_count"):
        return skip("no_fairness_proposals")
    latest = analysis.get("latest_fairness_suggestion")
    if not isinstance(latest, dict) or not isinstance(latest.get("members"), list):
        return skip("no_latest_suggestion")

    by_group = analysis.get("staffing_by_group") or {}
    responding = [
        group for group in by_group.get("groups") or []
        if isinstance(group, dict) and (group.get("response_count") or 0) > 0
    ]
    if not responding:
        return skip("no_response_station")
    station_ids = set()
    for group in responding:
        station = group.get("station") or {}
        candidate = _id(station.get("station_id"))
        if candidate is None:
            return skip("station_unresolved")
        station_ids.add(candidate)
    if station_ids != {requested}:
        return skip("multi_station_or_other_station")

    people: dict[str, set[tuple[str, str | None, str]]] = {}
    for group in responding:
        for person in group.get("response_people") or []:
            if not isinstance(person, dict):
                continue
            membership = _id(person.get("membership_id"))
            name = _label(person.get("user_name"))
            if membership is None or not name:
                continue
            key = _name_key(name)
            people.setdefault(key, set()).add(
                (membership, _id(person.get("user_id")), name)
            )

    identified: list[dict[str, str | None]] = []
    unmatched = 0
    ambiguous = 0
    seen: set[tuple[str, str]] = set()
    for suggested in latest["members"]:
        if not isinstance(suggested, dict):
            unmatched += 1
            continue
        name_key = _name_key(suggested.get("name"))
        role = _label(suggested.get("role"))
        matches = people.get(name_key, set())
        if not name_key or not role:
            unmatched += 1
        elif len(matches) > 1:
            ambiguous += 1
        elif len(matches) == 0:
            unmatched += 1
        else:
            membership, user_id, display_name = next(iter(matches))
            match_key = (membership, role)
            if match_key not in seen:
                identified.append(
                    {
                        "membership_id": membership,
                        "user_id": user_id,
                        "name": display_name,
                        "role": role,
                    }
                )
                seen.add(match_key)

    if not identified:
        return skip("no_unambiguous_membership_matches")

    return {
        "incident_id": incident_id,
        "status": "imported",
        "record": {
            "incident_id": incident_id,
            "station_id": requested,
            "latest_proposal_at": latest.get("at"),
            "proposal_snapshots_seen": analysis["fairness_suggestion_count"],
            "people": identified,
            "unmatched_proposal_seats": unmatched,
            "ambiguous_name_seats": ambiguous,
            "source": "complete_audit_latest_fairness_proposal",
        },
    }


def build_historical_role_preview(
    records: list[dict[str, Any]], station_id: int | str,
) -> dict[str, Any]:
    """Summarize historical candidates, with no fabricated probability/ranking."""
    requested = _id(station_id)
    if not requested:
        raise ValueError("station_id must be numeric")
    distinct: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or _id(record.get("station_id")) != requested:
            continue
        incident_id = _id(record.get("incident_id"))
        if incident_id is not None:
            distinct[incident_id] = record

    observed = sorted(
        distinct.values(), key=lambda r: str(r.get("latest_proposal_at") or ""),
        reverse=True,
    )
    roles: dict[str, dict[str, dict]] = {}
    skipped_unmatched = 0
    skipped_ambiguous = 0
    for record in observed:
        skipped_unmatched += int(record.get("unmatched_proposal_seats") or 0)
        skipped_ambiguous += int(record.get("ambiguous_name_seats") or 0)
        incident_roles: set[tuple[str, str]] = set()
        for item in record.get("people") or []:
            if not isinstance(item, dict):
                continue
            membership = _id(item.get("membership_id"))
            role = _label(item.get("role"))
            if not membership or not role:
                continue
            role_key = (role, membership)
            if role_key in incident_roles:
                continue
            incident_roles.add(role_key)
            group = roles.setdefault(role, {})
            candidate = group.setdefault(
                membership,
                {
                    "membership_id": membership,
                    "user_id": _id(item.get("user_id")),
                    "name": _label(item.get("name")),
                    "incidents_in_latest_proposal": 0,
                    "last_observed_at": None,
                },
            )
            candidate["incidents_in_latest_proposal"] += 1
            timestamp = record.get("latest_proposal_at")
            if timestamp and (
                candidate["last_observed_at"] is None
                or timestamp > candidate["last_observed_at"]
            ):
                candidate["last_observed_at"] = timestamp

    return {
        "station_id": requested,
        "distinct_incidents_with_complete_matched_audit": len(observed),
        "historical_roles": [
            {
                "role": role,
                # Descriptive frequency only; a repeatedly suggested member is
                # not necessarily more likely to be proposed *next time*.
                "candidates": sorted(
                    candidates.values(),
                    key=lambda c: (
                        str(c.get("last_observed_at") or ""),
                        str(c.get("name") or ""),
                    ),
                    reverse=True,
                ),
            }
            for role, candidates in sorted(roles.items())
        ],
        "historical_unmatched_proposal_seats": skipped_unmatched,
        "historical_ambiguous_name_seats": skipped_ambiguous,
        "prediction_status": "history_only_not_a_lineup_prediction",
        "current_duty_or_availability_checked": False,
        "actual_vehicle_crew_verified": False,
        "fairness_percentage_calculated": False,
        "interpretation": (
            "One latest fairness suggestion per unique incident was counted. "
            "Only uniquely matched membership IDs within a single-station "
            "incident contribute to each role. Historical proposal frequency "
            "is not a fairness percentage or a probability of being selected "
            "next. Current availability, vehicle requirements and scheduling "
            "policy have not been validated, so no crew is predicted."
        ),
    }
