"""Read-only scope audit for candidate roster source coverage.

The existing client's membership_index and membership_duty only represent the
authenticated user's discovered active memberships, NOT every firefighter at
a station. Cached groups are structural hints and are not proof of a complete
authorized live station roster. Return safe aggregate diagnostics only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _id(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        number = int(value)
        return str(number) if number > 0 else None
    return None


def assess_candidate_roster_source(
    station_id: int | str,
    *,
    groups: list[dict[str, Any]] | None,
    own_membership_index: Mapping[Any, Any] | None,
    own_membership_duty: Mapping[Any, Any] | None,
) -> dict[str, Any]:
    """Summarize source reach, never return a user/member identifier or name."""
    station = _id(station_id)
    if station is None:
        raise ValueError("station_id must be a positive numeric ID")
    station_found = False
    cached_station_members: set[str] = set()
    invalid_station_rows = 0
    conflicting_identity_links = 0
    links: dict[str, set[str | None]] = {}
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        group_id = _id(group.get("id"))
        ancestors = {
            value for raw in (group.get("ancestor_ids") or [])
            if (value := _id(raw)) is not None
        }
        is_station = group_id == station and group.get("type") == "station"
        is_related = (
            is_station or station in ancestors
            or _id(group.get("parent_group_id")) == station
        )
        if not is_related:
            continue
        if is_station:
            station_found = True
        for member in group.get("memberships") or []:
            if not isinstance(member, dict):
                invalid_station_rows += 1
                continue
            if member.get("status") != "active":
                continue
            member_id = _id(member.get("id"))
            if member_id is None:
                invalid_station_rows += 1
                continue
            cached_station_members.add(member_id)
            links.setdefault(member_id, set()).add(_id(member.get("user_id")))
    conflicting_identity_links = sum(
        len(values) > 1 or None in values for values in links.values()
    )
    own_ids = {
        value for key in (own_membership_index or {})
        if (value := _id(key)) is not None
    }
    duty_ids = {
        value for key in (own_membership_duty or {})
        if (value := _id(key)) is not None
    }
    overlap = own_ids.intersection(cached_station_members)
    return {
        "station_id": station,
        "source": "cached_groups_plus_authenticated_user_membership_index",
        "station_discovered": station_found,
        "cached_active_related_membership_count": len(cached_station_members),
        "cached_membership_identity_link_issues": conflicting_identity_links,
        "invalid_active_membership_rows": invalid_station_rows,
        "authenticated_user_membership_count": len(own_ids),
        "authenticated_user_duty_entries_count": len(duty_ids),
        "own_memberships_in_cached_station_groups": len(overlap),
        "own_memberships_with_cached_duty_at_station": len(overlap.intersection(duty_ids)),
        "current_station_full_roster_verified": False,
        "current_station_all_member_availability_verified": False,
        "current_station_all_member_skills_verified": False,
        "can_build_operational_prediction": False,
        "predicted_lineup": None,
        "required_next_source": (
            "authorized_current_complete_station_member_listing_with_verified_"
            "user_identity_per_membership_and_individual_schedule_and_skill_scope"
        ),
        "interpretation": (
            "The client membership_index and membership_duty cover this account's "
            "own affiliations only. Cached group membership entries are not a "
            "verified exhaustive live roster. Counts do not establish which "
            "individuals are on duty or eligible for the next task."
        ),
    }
