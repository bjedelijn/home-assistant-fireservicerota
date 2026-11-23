"""Bounded opt-in daily selection of already cached historical incident audits.

No network requests here. No incident IDs in public results or logs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _dt(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or len(raw) > 50:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.astimezone(timezone.utc) if value.tzinfo else None


def select_turnout_rechecks(
    records: list[dict[str, Any]],
    now: datetime,
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Choose at most two due, cached incidents; no broad API discovery."""
    if now.tzinfo is None:
        raise ValueError("timezone-aware now required")
    if not 1 <= limit <= 3:
        raise ValueError("limit must be between one and three")
    now = now.astimezone(timezone.utc)
    due: list[tuple[datetime, datetime, dict[str, Any]]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        incident = record.get("incident_id")
        proposal = _dt(record.get("latest_proposal_at"))
        if not isinstance(incident, str) or not incident.isdecimal() or proposal is None:
            continue
        age = now - proposal
        if not timedelta(days=1) <= age <= timedelta(days=45):
            continue
        review = record.get("turnout_audit_review") or {}
        if not isinstance(review, dict):
            review = {}
        last = _dt(review.get("checked_at"))
        cadence = timedelta(days=1 if age <= timedelta(days=14) else 7)
        if last is not None and now - last < cadence:
            continue
        # Prioritize never-reviewed incidents; otherwise the oldest review.
        sort_date = last or datetime.min.replace(tzinfo=timezone.utc)
        due.append((sort_date, proposal, record))
    return [record for _last, _proposal, record in sorted(
        due, key=lambda item: (item[0], item[1])
    )[:limit]]
