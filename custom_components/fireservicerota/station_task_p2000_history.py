"""Bounded station-wide preview of historical P2000 terms per task.

This module only reuses the conservative one-task incident association result.
It never promotes co-occurrence into a verified configured P2000 filter or a
physical response. Conflicts between tasks are surfaced rather than silently
treated as distinct vehicle mappings. Results are all privacy-sanitized and
no incident bodies, members, addresses or other API details are returned.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .task_p2000_history import analyze_task_p2000_history

_MAX_STATION_TASKS = 40
_MAX_TOP_TERMS_PER_TASK = 3
_ALLOWED_GRADES = {
    "strong_historical_candidate",
    "tentative_historical_candidate",
}


def _numeric(value: Any) -> str | None:
    """Convert non-bool integer or digit-string IDs into a bounded string."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    value = str(value)
    if value.isdecimal() and value.isascii() and 1 <= len(value) <= 15:
        return value
    return None


def preview_station_task_p2000_history(
    station_id: int | str,
    task_index: dict[Any, Any],
    incidents: list[dict[str, Any]],
    *,
    retained_count: int,
    explicitly_requested_ids: list[str] | None = None,
    api_ids_read: list[str] | None = None,
    api_ids_failed: list[str] | None = None,
) -> dict[str, Any]:
    """Summarize all currently indexed tasks for one authorized station.

    No API calls are made from this pure function. A distinct upstream service
    checks station authorization and optionally fetches an explicit list of
    incident details. It must never pass more than 25 retained + 10 explicit.
    """
    station = _numeric(station_id)
    if station is None:
        raise ValueError("A numeric station ID is required")
    matches = set()
    for raw_task_id, entries in (task_index or {}).items():
        task_id = _numeric(raw_task_id)
        if task_id is None or not isinstance(entries, list):
            continue
        for item in entries:
            if (
                isinstance(item, dict)
                and _numeric(item.get("id")) == task_id
                and _numeric(item.get("station_id")) == station
            ):
                matches.add(task_id)
                break
    task_ids = sorted(matches, key=int)
    selected_ids = task_ids[:_MAX_STATION_TASKS]
    results = []
    for task_id in selected_ids:
        report = analyze_task_p2000_history(
            station,
            task_id,
            task_index,
            incidents,
            retained_count=retained_count,
            explicitly_requested_ids=explicitly_requested_ids,
            api_ids_read=api_ids_read,
            api_ids_failed=api_ids_failed,
        )
        score = report["candidate_heuristic_score"]
        candidate_term = report["candidate_p2000_term"]
        results.append({
            "task_id": report["task_id"],
            "task_name": report["task_name"],
            "probe_status": report["probe_status"],
            "candidate_p2000_term": candidate_term,
            "candidate_evidence_grade": report["candidate_evidence_grade"],
            "candidate_heuristic_score": score,
            "target_task_incidents": report["target_task_incidents"],
            "single_task_incidents": report["target_single_task_incidents"],
            "multi_task_incidents": report["target_multi_task_incidents"],
            "top_terms": [
                {
                    "p2000_term": item["p2000_term"],
                    "incidents_with_task_and_term": item[
                        "incidents_with_task_and_term"
                    ],
                    "single_task_incidents_with_term": item[
                        "single_task_incidents_with_term"
                    ],
                    "single_task_single_term_incidents": item[
                        "single_task_single_term_incidents"
                    ],
                    "coverage_percent": item["coverage_percent"],
                }
                for item in report["candidate_terms"][:_MAX_TOP_TERMS_PER_TASK]
            ],
            "candidate_conflict": False,
            "conflicting_task_ids": [],
            "review_status": "no_supported_unique_candidate",
        })

    # Distinct station tasks can genuinely share configured message terms.
    # Highlight that conflict and require human review rather than guessing.
    indexed_by_code: dict[str, list[str]] = {}
    for item in results:
        number = item["candidate_p2000_term"]
        if number and item["candidate_evidence_grade"] in _ALLOWED_GRADES:
            indexed_by_code.setdefault(number, []).append(item["task_id"])

    for item in results:
        number = item["candidate_p2000_term"]
        if number is None:
            continue
        conflicting = [
            task_id
            for task_id in indexed_by_code.get(number, [])
            if task_id != item["task_id"]
        ]
        item["conflicting_task_ids"] = sorted(conflicting, key=int)
        item["candidate_conflict"] = bool(conflicting)
        if conflicting:
            item["review_status"] = "candidate_shared_by_multiple_station_tasks"
        elif item["candidate_evidence_grade"] == "strong_historical_candidate":
            item["review_status"] = "strong_candidate_for_manual_verification"
        else:
            item["review_status"] = "tentative_candidate_for_manual_verification"

    grades = Counter(item["candidate_evidence_grade"] for item in results)
    return {
        "station_id": station,
        "probe_status": "station_historical_task_p2000_preview",
        "source": "retained_closed_incidents_plus_optional_explicit_api_details",
        "retained_closed_incidents_available": max(0, retained_count),
        "explicit_incident_ids_requested": list(
            explicitly_requested_ids or []
        )[:10],
        "api_incident_ids_read": list(api_ids_read or [])[:10],
        "api_incident_ids_failed": list(api_ids_failed or [])[:10],
        "station_task_count": len(task_ids),
        "tasks_analyzed": len(results),
        "tasks_omitted_due_to_limit": len(task_ids) - len(results),
        "strong_historical_candidate_tasks": grades[
            "strong_historical_candidate"
        ],
        "tentative_historical_candidate_tasks": grades[
            "tentative_historical_candidate"
        ],
        "tasks_with_conflicting_candidates": sum(
            item["candidate_conflict"] for item in results
        ),
        "task_results": results,
        "current_task_configuration_verified": False,
        "operational_vehicle_dispatch_verified": False,
        "local_storage_modified": False,
        "brandweerrooster_modified": False,
        "personal_data_returned": False,
        "raw_incident_bodies_returned": False,
        "interpretation": (
            "Historical incident message co-occurrence only. P2000 terms are "
            "not proven task configuration or physical turnout. Shared "
            "candidates require manual review. The numerical evidence score "
            "is not a probability. Station task IDs/names come from current "
            "discovery, not a past configuration snapshot. Nothing is stored."
        ),
    }
