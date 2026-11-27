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


def summarize_history_listing_scan(pages: list[Any], *, start_page: int = 1) -> dict[str, Any]:
    """Report bounded page continuity without exposing incident identities."""
    if not 1 <= len(pages) <= 5 or not 1 <= start_page <= 500:
        raise ValueError("invalid page range")
    summaries = [summarize_history_listing(page) for page in pages]
    result: dict[str, Any] = {
        "read_only": True,
        "incident_ids_returned": False,
        "personal_or_post_details_returned": False,
        "history_complete": False,
        "date_filter_supported": None,
        "pages_requested": len(pages),
        "start_page": start_page,
        "next_start_page": start_page + len(pages),
        "per_page_requested": 25,
        "per_page_effective": max((p["items_inspected"] for p in summaries), default=0),
        "total_items_observed": sum(p["items_inspected"] for p in summaries),
        "pages": [
            {
                "page": start_page + index - 1,
                "status": item["status"],
                "items_inspected": item["items_inspected"],
                "earliest_visible_at": item["earliest_visible_at"],
                "latest_visible_at": item["latest_visible_at"],
            }
            for index, item in enumerate(summaries, 1)
        ],
        "pagination_verified": False,
        "distinct_incident_count": None,
        "overlapping_incident_count": None,
        "status": "unverified",
        "stopped_on_unexpected_response": False,
    }
    if any(item["status"] != "listing_shape_observed" for item in summaries):
        result["status"] = "unrecognized_page_shape"
        result["stopped_on_unexpected_response"] = True
        return result
    reference_keys = ("task_ids", "tasks", "incident_tasks", "station_id", "station_ids", "group_id", "group_ids", "incident_responses")
    result["reference_field_counts"] = dict.fromkeys(reference_keys, 0)
    result["reference_nonempty_counts"] = dict.fromkeys(reference_keys, 0)
    seen: set[str] = set()
    overlaps = 0
    for payload in pages:
        rows = payload if isinstance(payload, list) else payload["data"]
        local: set[str] = set()
        for row in rows:
            for key in reference_keys:
                if key in row:
                    result["reference_field_counts"][key] += 1
                    if row[key] not in (None, "", [], {}):
                        result["reference_nonempty_counts"][key] += 1
            identifier = row.get("id")
            if isinstance(identifier, bool) or not isinstance(identifier, (str, int)):
                result["status"] = "identifiers_not_comparable"
                return result
            identifier = str(identifier)
            if not identifier.isdecimal() or len(identifier) > 24 or identifier in local:
                result["status"] = "identifiers_not_comparable"
                return result
            local.add(identifier)
        overlaps += len(seen & local)
        seen.update(local)
    result["distinct_incident_count"] = len(seen)
    result["overlapping_incident_count"] = overlaps
    result["pagination_verified"] = (
        len(pages) > 1 and overlaps == 0
        and all(item["items_inspected"] > 0 for item in summaries)
    )
    result["status"] = "distinct_pages_observed" if result["pagination_verified"] else "overlap_or_empty_pages"
    return result
