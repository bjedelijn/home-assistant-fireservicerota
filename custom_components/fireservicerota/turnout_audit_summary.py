"""Bounded, anonymous evidence of retrospective turnout-status audit events.

Audit descriptions and actor/subject fields are untrusted private strings.
Only validated timestamps and aggregate counts leave this module. An audit
event alone cannot establish a manual correction or actual attendance.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .fairness_revision_summary import _safe_timestamp


def _date(raw: Any) -> datetime | None:
    normalized = _safe_timestamp(raw)
    if normalized is None:
        return None
    return datetime.fromisoformat(normalized)


def summarize_turnout_audit(analysis: dict[str, Any]) -> dict[str, Any]:
    """Return safe turnout-status audit event metadata only."""
    result: dict[str, Any] = {
        "audit_complete": analysis.get("audit_complete") is True,
        "audit_pagination_warning_present": bool(analysis.get("audit_pagination_warning")),
        "turnout_status_audit_events_seen": 0,
        "turnout_status_audit_timeline": [],
        "events_after_last_fairness_proposal": None,
        "first_turnout_status_event_at": None,
        "latest_turnout_status_event_at": None,
        "last_fairness_proposal_at": None,
        "audit_event_count_interpretation": "events_not_unique_people_or_confirmed_corrections",
        "manual_corrections_verified": False,
        "old_new_status_values_verified": False,
        "actual_vehicle_crew_verified": False,
        "comparison_status": "unavailable",
        "interpretation": (
            "Only observed turnout-status audit markers and timestamps. "
            "No proof of a manual correction, old/new status, actual turnout, "
            "fairness selection cause, or completeness without a full audit."
        ),
    }
    if not result["audit_complete"]:
        result["comparison_status"] = "audit_incomplete"
        return result

    changes = analysis.get("audit_turnout_status_changes")
    proposals = analysis.get("fairness_suggestions")
    if not isinstance(changes, list) or not isinstance(proposals, list):
        result["comparison_status"] = "invalid_audit_data"
        return result
    if len(changes) > 500 or len(proposals) > 500:
        result["comparison_status"] = "audit_event_limit_exceeded"
        return result

    dates: list[datetime] = []
    for event in changes:
        if not isinstance(event, dict):
            result["comparison_status"] = "invalid_audit_event"
            return result
        event_date = _date(event.get("at"))
        if event_date is None:
            result["comparison_status"] = "invalid_audit_timestamp"
            return result
        dates.append(event_date)

    proposal_dates: list[datetime] = []
    for event in proposals:
        if not isinstance(event, dict):
            result["comparison_status"] = "invalid_proposal_event"
            return result
        event_date = _date(event.get("at"))
        if event_date is None:
            result["comparison_status"] = "invalid_proposal_timestamp"
            return result
        proposal_dates.append(event_date)

    # Compare offsets as actual datetimes, not lexicographically sorted strings.
    dates.sort()
    last_proposal = max(proposal_dates) if proposal_dates else None
    result["turnout_status_audit_events_seen"] = len(dates)
    result["turnout_status_audit_timeline"] = [
        {"event_index": index + 1, "at": date.isoformat()}
        for index, date in enumerate(dates)
    ]
    if dates:
        result["first_turnout_status_event_at"] = dates[0].isoformat()
        result["latest_turnout_status_event_at"] = dates[-1].isoformat()
    if last_proposal is not None:
        result["last_fairness_proposal_at"] = last_proposal.isoformat()
        result["events_after_last_fairness_proposal"] = sum(
            date > last_proposal for date in dates
        )
    result["comparison_status"] = "audit_markers_observed"
    return result
