"""Identity-free structural report for a single, bounded history listing GET."""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _date(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 50:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.isoformat() if dt.tzinfo else None


def summarize_history_listing(payload: Any) -> dict[str, Any]:
    """Return strictly bounded metadata, never raw incident rows or user fields."""
    result: dict[str, Any] = {
        "read_only": True,
        "source": "bwr_incidents_list_probe",
        "incident_ids_returned": False,
        "personal_or_post_details_returned": False,
        "date_filter_supported": None,
        "pagination_verified": False,
        "history_complete": False,
        "status": "unrecognized_listing_shape",
        "items_inspected": 0,
        "earliest_visible_at": None,
        "latest_visible_at": None,
    }
    if isinstance(payload, list):
        rows = payload
        result["shape"] = "list"
    elif isinstance(payload, dict):
        rows = payload.get("data")
        result["shape"] = "data_envelope" if isinstance(rows, list) else "unrecognized"
    else:
        return result
    if not isinstance(rows, list):
        return result
    # Never traverse unbounded responses or inspect person/member fields.
    if len(rows) > 50:
        result["status"] = "response_exceeded_probe_limit"
        return result
    result["status"] = "listing_shape_observed"
    result["items_inspected"] = len(rows)
    dates = []
    for row in rows:
        if not isinstance(row, dict):
            result["status"] = "unexpected_row_shape"
            return result
        for key in ("start_time", "created_at", "occurred_at"):
            date = _date(row.get(key))
            if date is not None:
                dates.append(date)
                break
    # Date strings can have different offsets; parse to compare instants.
    if dates:
        ordered = sorted(dates, key=lambda s: datetime.fromisoformat(s).timestamp())
        result["earliest_visible_at"] = ordered[0]
        result["latest_visible_at"] = ordered[-1]
    return result
