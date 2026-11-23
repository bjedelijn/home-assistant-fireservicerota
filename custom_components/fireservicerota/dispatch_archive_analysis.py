"""Local counts of indexed BWR incident records, NOT dispatch/turnout totals.

Do not equate BWR created_at with a confirmed alarm/turnout timestamp.
No member, station, incident ID, title or vehicle is emitted by this module.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


def summarize_indexed_incident_months(
    records: list[dict[str, Any]], *,
    timezone_name: str = "Europe/Amsterdam",
    listing_exhausted: bool = False,
) -> dict[str, Any]:
    """Produce local month buckets with explicit unverified coverage.

    A missing item means *no indexed record*, NOT a proven zero dispatches.
    This uses BWR-created timestamps, which may not be occurrence times.
    """
    tz = ZoneInfo(timezone_name)
    seen: set[str] = set()
    counts: dict[int, list[int]] = defaultdict(lambda: [0] * 12)
    rejected = 0
    for row in records:
        if not isinstance(row, dict):
            rejected += 1
            continue
        ident = row.get("incident_id")
        created = row.get("occurred_at")
        if not isinstance(ident, str) or not ident.isdecimal() or not isinstance(created, str):
            rejected += 1
            continue
        if ident in seen:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            rejected += 1
            continue
        if dt.tzinfo is None:
            rejected += 1
            continue
        local = dt.astimezone(tz)
        seen.add(ident)
        counts[local.year][local.month - 1] += 1

    return {
        "status": "indexed_bwr_records_only",
        "historical_list_exhausted": listing_exhausted,
        "archive_years_verified_complete": False,
        "confirmed_dispatch_statistics": False,
        "historical_fairness_evidence_available": False,
        "timezone": timezone_name,
        "date_field": "bwr_created_at",
        "indexed_unique_incidents": len(seen),
        "rejected_archive_rows": rejected,
        "years": [
            {
                "year": year,
                "months": monthly,
                "indexed_record_total": sum(monthly),
                "coverage": "unknown",
                "is_confirmed_full_year": False,
            }
            for year, monthly in sorted(counts.items(), reverse=True)
        ],
        "interpretation": (
            "Monthly values count locally indexed BWR records by created_at, "
            "not confirmed alerts, dispatches, vehicle departures or fairness "
            "events. Zero means no indexed records, not proof of no incidents. "
            "Historical completeness is unverified for every year."
        ),
    }
