"""Privacy-minimized comparison of an incident's fairness proposal revisions.

An audit proposal is a text snapshot, not a verified crew. No names, user IDs,
membership IDs, addresses, or full audit rows are retained or returned.
"""
from __future__ import annotations

from collections import Counter
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
    result["first_proposal_at"] = proposals[0].get("at")
    result["latest_proposal_at"] = proposals[-1].get("at")
    result["initial_role_counts"] = [
        {"role": role, "proposed_seats": count}
        for role, count in sorted(initial_roles.items())
    ]
    result["latest_role_counts"] = [
        {"role": role, "proposed_seats": count}
        for role, count in sorted(latest_roles.items())
    ]
    result["added_role_assignments"] = sum((latest - initial).values())
    result["removed_role_assignments"] = sum((initial - latest).values())
    result["distinct_revisions"] = sum(
        parsed[i][0] != parsed[i - 1][0] for i in range(1, len(parsed))
    )
    result["comparison_status"] = "textual_snapshots_compared"
    return result
