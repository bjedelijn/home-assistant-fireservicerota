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


def compare_history_listing_pages(first: Any, second: Any) -> dict[str, Any]:
    """Compare two bounded page results privately; never echo IDs or raw data."""
    a = summarize_history_listing(first)
    b = summarize_history_listing(second)
    result: dict[str, Any] = {
        "status": "pagination_unverified",
        "read_only": True,
        "incident_ids_returned": False,
        "personal_or_post_details_returned": False,
        "history_complete": False,
        "date_filter_supported": None,
        "pages_requested": 2,
        "page_1": a,
        "page_2": b,
        "pagination_verified": False,
        "overlapping_incident_count": None,
        "distinct_incident_count": None,
        "page_2_older_than_page_1": None,
    }
    if a["status"] != "listing_shape_observed" or b["status"] != "listing_shape_observed":
        result["status"] = "unrecognized_page_shape"
        return result

    def rows(payload: Any) -> list:
        return payload if isinstance(payload, list) else payload["data"]

    def ids(payload: Any) -> set[str] | None:
        values: list[str] = []
        for row in rows(payload):
            item = row.get("id")
            if isinstance(item, bool) or not isinstance(item, (int, str)):
                return None
            ident = str(item)
            if not ident.isdecimal() or len(ident) > 24:
                return None
            values.append(ident)
        return set(values) if len(values) == len(set(values)) else None

    ids1, ids2 = ids(first), ids(second)
    if ids1 is None or ids2 is None:
        result["status"] = "identifiers_not_comparable"
        return result
    result["overlapping_incident_count"] = len(ids1 & ids2)
    result["distinct_incident_count"] = len(ids1 | ids2)
    if a["earliest_visible_at"] and b["latest_visible_at"]:
        before = datetime.fromisoformat(b["latest_visible_at"])
        after = datetime.fromisoformat(a["earliest_visible_at"])
        result["page_2_older_than_page_1"] = before <= after
    # Distinct page contents confirm pagination behaviour, but not archival
    # depth, complete backfill coverage or source sorting guarantees.
    if ids2 and ids1 != ids2 and not (ids1 & ids2):
        result["pagination_verified"] = True
        result["status"] = "distinct_pages_observed"
    elif not ids2:
        result["status"] = "second_page_empty"
    else:
        result["status"] = "repeated_or_overlapping_pages"
    return result
