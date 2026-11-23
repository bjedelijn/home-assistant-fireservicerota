"""Privacy-minimized comparison of an incident's fairness proposal revisions.

An audit proposal is a text snapshot, not a verified crew. No names, user IDs,
membership IDs, addresses, or full audit rows are retained or returned.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def _proposal_tokens(proposal: dict[str, Any]) -> tuple[Counter, dict[str, int], bool]:
    rows = proposal.get("members")
    if not isinstance(rows, list) or len(rows) > 100:
        return Counter(), {}, False
    tokens: Counter = Counter()
    roles: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            return Counter(), {}, False
        name = row.get("name")
        role = row.get("role")
        if not isinstance(name, str) or not isinstance(role, str):
            return Counter(), {}, False
        name, role = " ".join(name.split()).casefold(), " ".join(role.split())
        if not name or not role or len(name) > 200 or len(role) > 80:
            return Counter(), {}, False
        # Temporary strings, never returned, logged or persisted.
        tokens[(name, role)] += 1
        roles[role] = roles.get(role, 0) + 1
    return tokens, roles, True


def _safe_timestamp(raw: Any) -> str | None:
    """Accept actual ISO timestamps only, never arbitrary audit strings."""
    if not isinstance(raw, str) or len(raw) > 50:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.isoformat()


# Only these generic role labels may leave the private audit context.
# Never echo arbitrary source labels, even in otherwise anonymous responses.
_SAFE_ROLES = {
    "aspirant manschap": "Aspirant Manschap",
    "bevelvoerder": "Bevelvoerder",
    "chauffeur": "Chauffeur",
    "manschap": "Manschap",
    "bediener redvoertuig": "Bediener Redvoertuig",
    "chauffeur redvoertuig": "Chauffeur Redvoertuig",
}
_OTHER_ROLE = "overig"


def _public_role(role: str) -> str:
    return _SAFE_ROLES.get(role.casefold().strip(), _OTHER_ROLE)


def _public_role_counts(raw: dict[str, int]) -> list[dict[str, Any]]:
    totals: dict[str, int] = {}
    for role, count in raw.items():
        label = _public_role(role)
        totals[label] = totals.get(label, 0) + count
    return [
        {"role": role, "proposed_seats": count}
        for role, count in sorted(totals.items())
    ]


def _role_change_counts(previous: Counter, current: Counter) -> list[dict[str, Any]]:
    """Aggregate anonymous additions/removals by fixed public role vocabulary."""
    removed = previous - current
    added = current - previous
    totals: dict[str, dict[str, int]] = {}
    for delta, field in (
        (added, "added_role_assignments"),
        (removed, "removed_role_assignments"),
    ):
        for (_name, private_role), count in delta.items():
            role = _public_role(private_role)
            row = totals.setdefault(
                role, {"added_role_assignments": 0, "removed_role_assignments": 0}
            )
            row[field] += count
    return [{"role": role, **counts} for role, counts in sorted(totals.items())]

def summarize_proposal_revisions(analysis: dict[str, Any]) -> dict[str, Any]:
    """Report counts only; never infer correctness, availability or actual crew."""
    result = {
        "audit_complete": analysis.get("audit_complete") is True,
        "audit_pagination_warning_present": bool(analysis.get("audit_pagination_warning")),
        "proposal_snapshots_seen": 0,
        "first_proposal_at": None,
        "latest_proposal_at": None,
        "initial_role_counts": [],
        "latest_role_counts": [],
        "added_role_assignments": None,
        "removed_role_assignments": None,
        "distinct_revisions": None,
        "net_role_assignment_changes": [],
        "transition_role_change_totals": [],
        "revision_timeline": [],
        "comparison_status": "unavailable",
        "current_duty_verified": False,
        "historical_eligibility_verified": False,
        "physical_vehicle_crew_verified": False,
        "selection_reason_verified": False,
        "interpretation": (
            "Textual proposed role changes only; no evidence of why a person was "
            "selected, of fairness weighting, or of actual attendance."
        ),
    }
    suggestions = analysis.get("fairness_suggestions")
    if not isinstance(suggestions, list):
        return result
    result["proposal_snapshots_seen"] = len(suggestions)
    if not result["audit_complete"]:
        result["comparison_status"] = "audit_incomplete"
        return result
    if not suggestions or len(suggestions) > 500:
        result["comparison_status"] = "no_proposals_or_limit_exceeded"
        return result
    proposals = sorted(
        suggestions,
        key=lambda row: str(row.get("at") or "") if isinstance(row, dict) else "",
    )
    if any(not isinstance(row, dict) for row in proposals):
        result["comparison_status"] = "invalid_proposals"
        return result
    parsed = [_proposal_tokens(row) for row in proposals]
    if not all(valid for _tokens, _roles, valid in parsed):
        result["comparison_status"] = "invalid_proposal_members"
        return result
    initial, initial_roles, _ = parsed[0]
    latest, latest_roles, _ = parsed[-1]
    safe_times = [_safe_timestamp(item.get("at")) for item in proposals]
    if any(at is None for at in safe_times):
        result["comparison_status"] = "invalid_proposal_timestamp"
        return result
    result["first_proposal_at"] = safe_times[0]
    result["latest_proposal_at"] = safe_times[-1]
    result["initial_role_counts"] = _public_role_counts(initial_roles)
    result["latest_role_counts"] = _public_role_counts(latest_roles)
    result["added_role_assignments"] = sum((latest - initial).values())
    result["removed_role_assignments"] = sum((initial - latest).values())
    result["distinct_revisions"] = sum(
        parsed[i][0] != parsed[i - 1][0] for i in range(1, len(parsed))
    )
    result["net_role_assignment_changes"] = _role_change_counts(initial, latest)
    cumulative: dict[str, dict[str, int]] = {}
    transitions = []
    for index in range(1, len(parsed)):
        before = parsed[index - 1][0]
        after = parsed[index][0]
        if before == after:
            continue
        changes = _role_change_counts(before, after)
        for change in changes:
            role = change["role"]
            counts = cumulative.setdefault(
                role, {"added_role_assignments": 0, "removed_role_assignments": 0}
            )
            counts["added_role_assignments"] += change["added_role_assignments"]
            counts["removed_role_assignments"] += change["removed_role_assignments"]
        transitions.append(
            {
                "proposal_index": index + 1,
                "at": safe_times[index],
                "changes_by_role": changes,
            }
        )
    result["transition_role_change_totals"] = [
        {"role": role, **counts} for role, counts in sorted(cumulative.items())
    ]
    result["revision_timeline"] = transitions
    result["comparison_status"] = "textual_snapshots_compared"
    return result
