"""Read-only BrandweerRooster audit/fairness inspection.

This endpoint is currently observed working with OAuth, but is not part of
pyfireservicerota's documented public API. Fetch only on explicit user action.
Suggestions and reported turnout must never be treated as verified attendance.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from .staffing_insights import build_staffing_by_group

AUDIT_ENDPOINT = "reporting/general_report/audit_log/data"
DEFAULT_MAX_PAGES = 5
MAX_PAGES = 20

ApiGet = Callable[[str, dict[str, Any] | None], Awaitable[Any]]


def _value(record: dict, field: str) -> Any:
    """Unwrap the audit report's value/formatted_value column wrapper."""
    item = record.get(field)
    return item.get("value") if isinstance(item, dict) else item


def _parse_suggestion(changes: Any) -> list[dict[str, str]] | None:
    """Parse a fairness suggestion; distinguish 'not present' from 'empty'."""
    if not isinstance(changes, str) or "Suggestion based on fairness" not in changes:
        return None

    members: list[dict[str, str]] = []
    for line in changes.splitlines():
        line = line.strip()
        if not line or line == "Suggestion based on fairness":
            continue
        parts = re.split(r"\s{2,}", line, maxsplit=1)
        if len(parts) == 2 and all(parts):
            members.append({"name": parts[0].strip(), "role": parts[1].strip()})
    return members



def _summarize_suggestions_by_role(
    suggestions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group proposal appearances by exact role; these are not fairness scores.

    A person may be proposed for more than one role across the incident.
    In particular, 'Manschap' and 'Aspirant Manschap' stay separate.
    """
    roles: dict[str, dict[str, Any]] = {}
    for suggestion in suggestions:
        for member in suggestion["members"]:
            role = member["role"].strip()
            name = member["name"].strip()
            if not role or not name:
                continue
            bucket = roles.setdefault(role, {"appearances": 0, "people": {}})
            bucket["appearances"] += 1
            people = bucket["people"]
            people[name] = people.get(name, 0) + 1

    latest_members = suggestions[-1]["members"] if suggestions else []
    return [
        {
            "role": role,
            "proposed_seat_appearances": entry["appearances"],
            "unique_proposed_people": len(entry["people"]),
            "latest_proposed_people": [
                member["name"]
                for member in latest_members
                if member["role"] == role
            ],
            "people": [
                {"name": name, "proposed_in_suggestions": count}
                for name, count in sorted(entry["people"].items())
            ],
        }
        for role, entry in sorted(roles.items())
    ]


def _api_snapshot(incident: Any) -> dict[str, Any]:
    """Expose only relevant structured REST fields, never the raw payload."""
    if not isinstance(incident, dict):
        return {"available": False, "responses": [], "skill_assignments": []}

    responses = []
    for response in incident.get("incident_responses") or []:
        if not isinstance(response, dict):
            continue
        responses.append(
            {
                "user_id": response.get("user_id"),
                "user_name": response.get("user_name"),
                "membership_id": response.get("membership_id"),
                "group_id": response.get("group_id"),
                "status": response.get("status"),
                "reported_status": response.get("reported_status"),
                "arrived_at_station": response.get("arrived_at_station"),
            }
        )

    assignments = []
    for assignment in incident.get("incident_skill_assignments") or []:
        if not isinstance(assignment, dict):
            continue
        assignments.append(
            {
                "user_id": assignment.get("user_id"),
                "membership_id": assignment.get("membership_id"),
                "skill_ids": list(assignment.get("skill_ids") or []),
            }
        )
    return {
        "available": True,
        "responses": responses,
        "skill_assignments": assignments,
    }


async def analyze_incident_fairness(
    api_get: ApiGet,
    incident_id: str | int,
    max_pages: int = DEFAULT_MAX_PAGES,
    groups: list[dict] | None = None,
) -> dict[str, Any]:
    """Read audit pages newest-first, then compare with API response snapshot.

    A returned 'fairness suggestion' is not a confirmed crew. API reported
    status is also *not* independent evidence of physical vehicle attendance.
    """
    incident_id = str(incident_id)
    if not incident_id.isdecimal():
        raise ValueError("incident_id must be a positive numeric identifier")
    if not isinstance(max_pages, int) or not 1 <= max_pages <= MAX_PAGES:
        raise ValueError(f"max_pages must be between 1 and {MAX_PAGES}")

    records: list[dict] = []
    seen_pages: set[tuple[Any, Any, Any]] = set()
    complete = False
    pagination_warning: str | None = None
    pages_fetched = 0
    for page in range(1, max_pages + 1):
        params: dict[str, Any] = {
            "object_ids": incident_id,
            "object_type": "incidents/activity_report",
            "elapsed_time": "true",
            "order": "desc",
            "debug": "false",
            "cols": "",
        }
        if page > 1:
            params["page"] = page

        payload = await api_get(AUDIT_ENDPOINT, params)
        if not isinstance(payload, list):
            raise ValueError("Audit API did not return a JSON list")
        pages_fetched += 1
        if not payload:
            complete = True
            break

        first = payload[0]
        if not isinstance(first, dict):
            raise ValueError("Audit API returned an unexpected record type")
        signature = (
            _value(first, "created_at"),
            _value(first, "audit_log_subject"),
            _value(first, "changes"),
        )
        if signature in seen_pages:
            pagination_warning = ("Audit API repeated an earlier page; "
                                  "history may be incomplete")
            break
        seen_pages.add(signature)

        records.extend(item for item in payload if isinstance(item, dict))
        # The report endpoint has returned page lengths below 100 even when
        # other records existed. Only an empty page proves the end of history.

    if not complete and pagination_warning is None:
        pagination_warning = "Audit page limit reached; history may be incomplete"

    suggestions: list[dict[str, Any]] = []
    status_changes: list[dict[str, Any]] = []
    for item in records:
        changes = _value(item, "changes")
        when = _value(item, "created_at")
        subject = _value(item, "audit_log_subject")
        members = _parse_suggestion(changes)
        if members is not None:
            suggestions.append({"at": when, "members": members})
        if isinstance(changes, str) and "Werkelijke opkomststatus" in changes:
            status_changes.append(
                {
                    "at": when,
                    "subject": subject,
                    "changed_by": _value(item, "whodunnit"),
                    "description": changes,
                }
            )

    suggestions.sort(key=lambda entry: entry.get("at") or "")
    status_changes.sort(key=lambda entry: entry.get("at") or "")

    # Reuse the integration's existing OAuth client. No POST, no persistence.
    incident = await api_get(f"incidents/{incident_id}", None)

    return {
        "incident_id": incident_id,
        "audit_records": len(records),
        "audit_pages_fetched": pages_fetched,
        "audit_complete": complete,
        "audit_pagination_warning": pagination_warning,
        "fairness_suggestion_count": len(suggestions),
        "latest_fairness_suggestion": suggestions[-1] if suggestions else None,
        "fairness_suggestions": suggestions,
        "fairness_by_role": _summarize_suggestions_by_role(suggestions),
        "audit_turnout_status_changes": status_changes,
        "api_snapshot": _api_snapshot(incident),
        "staffing_by_group": build_staffing_by_group(incident, groups),
        "caution": (
            "Fairness suggestions are automated proposals, not confirmed crew. "
            "Role appearance counts are not fairness percentages. "
            "Reported turnout is not independent proof of actual attendance."
        ),
    }
