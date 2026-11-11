"""Conservative incident-to-task P2000 term association, read-only.

This does not know the provider's actual per-task required P2000 filter.
Incident bodies mention many dispatched appliance numbers, including vehicles
from other stations. They MUST NEVER be interpreted as task configuration or
verified physical attendance. In particular, multi-task incidents only
provide co-occurrence evidence, not per-task assignments.

All output is bounded to numeric incident IDs, safe task labels and six-digit
P2000 terms, with explicit evidence counts and an uncalibrated heuristic score.
No personnel, alert text, address, response records or persistent mappings.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any

from .task_p2000_probe import choose_task_p2000_probe

_P2000_TERM = re.compile(r"(?<![0-9])0[0-9]{5}(?![0-9])")
_NUMERIC_ID = re.compile(r"[0-9]{1,15}\Z")
_MAX_BODY = 12_000
_MAX_RECORDS = 40
_MAX_CANDIDATES = 15
_MAX_INCIDENT_EVIDENCE = 8


def _id(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    text = str(value) if isinstance(value, (int, str)) else ""
    return text if _NUMERIC_ID.fullmatch(text) else None


def _task_set(value: Any) -> set[str] | None:
    if not isinstance(value, list) or not 1 <= len(value) <= 100:
        return None
    values = [_id(item) for item in value]
    if any(item is None for item in values):
        return None
    return set(values)


def _terms_from_incident_body(value: Any) -> set[str] | None:
    if not isinstance(value, str) or not 1 <= len(value) <= _MAX_BODY:
        return None
    return set(_P2000_TERM.findall(value))


def _eligible_incident(record: Any) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    incident_id = _id(record.get("id"))
    task_ids = _task_set(record.get("task_ids"))
    terms = _terms_from_incident_body(record.get("body"))
    if incident_id is None or task_ids is None or not terms:
        return None
    return {
        "id": incident_id,
        "task_ids": task_ids,
        "terms": terms,
        "is_single_task": len(task_ids) == 1,
        "is_single_term": len(terms) == 1,
    }


def _heuristic_score(
    *, exclusive_single: int, single: int, support: int,
    task_total: int, other_task_support: int, other_task_total: int,
) -> int:
    """Uncalibrated evidence index, not a probability of the vehicle match."""
    coverage = support / task_total if task_total else 0.0
    strength = (
        35.0 * min(1, exclusive_single)
        + 20.0 * min(1.0, single / 2)
        + 30.0 * coverage
        + 15.0 * min(1.0, support / 4)
    )
    # Never claim general specificity when we have no negative examples.
    # The small other-task prevalence penalty is explicitly descriptive.
    if other_task_total:
        strength -= 10.0 * other_task_support / other_task_total
    return max(0, min(100, round(strength)))


def analyze_task_p2000_history(
    station_id: int | str,
    task_id: int | str,
    task_index: dict[Any, Any],
    incidents: list[dict[str, Any]],
    *,
    retained_count: int,
    explicitly_requested_ids: list[str] | None = None,
    api_ids_read: list[str] | None = None,
    api_ids_failed: list[str] | None = None,
) -> dict[str, Any]:
    """Report bounded association for one uniquely indexed station task.

    Incidents contain closed historical HA snapshots and, optionally, one
    authenticated official API detail GET per explicitly requested ID.
    Deduplication by incident ID occurs before scoring, and explicit fetched
    detail only wins if it contains an eligible body/task list.
    """
    selection = choose_task_p2000_probe(
        station_id, task_id, task_index, []
    )
    base: dict[str, Any] = {
        "station_id": selection["station_id"],
        "task_id": selection["task_id"],
        "task_name": selection["task_name"],
        "probe_status": "task_not_uniquely_indexed_for_this_station",
        "analysis_source": "retained_closed_incidents_plus_optional_explicit_api_details",
        "retained_closed_incidents_available": max(0, retained_count),
        "explicit_incident_ids_requested": list(explicitly_requested_ids or [])[:10],
        "api_incident_ids_read": list(api_ids_read or [])[:10],
        "api_incident_ids_failed": list(api_ids_failed or [])[:10],
        "records_examined": 0,
        "usable_incident_records": 0,
        "skipped_unusable_records": 0,
        "target_task_incidents": 0,
        "target_single_task_incidents": 0,
        "target_multi_task_incidents": 0,
        "other_station_task_incidents": 0,
        "candidate_p2000_term": None,
        "candidate_evidence_grade": "unavailable",
        "candidate_heuristic_score": None,
        "candidate_terms": [],
        "operational_vehicle_dispatch_verified": False,
        "current_task_configuration_verified": False,
        "local_storage_modified": False,
        "brandweerrooster_modified": False,
        "personal_data_returned": False,
        "raw_incident_bodies_returned": False,
        "caveats": [
            "A P2000 term in an incident is only co-occurrence; it does not "
            "prove the station vehicle attended or the term is its task filter.",
            "Multi-task incidents cannot assign a number to an individual task.",
            "Task/station membership is resolved from the current index, not "
            "a historical task configuration snapshot.",
            "The numeric score is an uncalibrated evidence index, not a probability.",
        ],
    }
    if selection["probe_status"] != "ready_for_single_task_GET" or not selection["task_name"]:
        return base
    base["probe_status"] = "insufficient_historical_incident_evidence"

    if not isinstance(incidents, list):
        return base
    records = incidents[:_MAX_RECORDS]
    base["records_examined"] = len(records)
    unique_records: dict[str, dict[str, Any]] = {}
    ignored = 0
    for item in records:
        record = _eligible_incident(item)
        if record is None:
            ignored += 1
            continue
        # Ignore duplicates except if an explicit GET was appended with better
        # task/message detail. The service deliberately passes API details last.
        unique_records[record["id"]] = record
    base["skipped_unusable_records"] = ignored
    base["usable_incident_records"] = len(unique_records)

    # Station tasks are scoped to the authorized user's current station.
    station_tasks = {
        str(candidate_id)
        for candidate_id, entries in task_index.items()
        if _id(candidate_id) is not None
        and isinstance(entries, list)
        and any(
            isinstance(entry, dict)
            and _id(entry.get("id")) == _id(candidate_id)
            and _id(entry.get("station_id")) == str(station_id)
            for entry in entries
        )
    }
    target = selection["task_id"]
    incident_rows = [
        item for item in unique_records.values() if target in item["task_ids"]
    ]
    other_rows = [
        item for item in unique_records.values()
        if target not in item["task_ids"]
        and bool(item["task_ids"] & station_tasks)
    ]
    solo_rows = [r for r in incident_rows if r["is_single_task"]]
    base["target_task_incidents"] = len(incident_rows)
    base["target_single_task_incidents"] = len(solo_rows)
    base["target_multi_task_incidents"] = len(incident_rows) - len(solo_rows)
    base["other_station_task_incidents"] = len(other_rows)

    if not incident_rows:
        return base

    total = len(incident_rows)
    all_counts: Counter[str] = Counter()
    solo_counts: Counter[str] = Counter()
    exclusive_counts: Counter[str] = Counter()
    other_counts: Counter[str] = Counter()
    supporting_ids: dict[str, list[str]] = defaultdict(list)
    solo_ids: dict[str, list[str]] = defaultdict(list)
    for record in incident_rows:
        for number in record["terms"]:
            all_counts[number] += 1
            if len(supporting_ids[number]) < _MAX_INCIDENT_EVIDENCE:
                supporting_ids[number].append(record["id"])
            if record["is_single_task"]:
                solo_counts[number] += 1
                if len(solo_ids[number]) < _MAX_INCIDENT_EVIDENCE:
                    solo_ids[number].append(record["id"])
                if record["is_single_term"]:
                    exclusive_counts[number] += 1
    for record in other_rows:
        other_counts.update(record["terms"])

    candidates = []
    for number, support in all_counts.items():
        solo = solo_counts[number]
        exclusive = exclusive_counts[number]
        other = other_counts[number]
        score = _heuristic_score(
            exclusive_single=exclusive, single=solo,
            support=support, task_total=total,
            other_task_support=other, other_task_total=len(other_rows),
        )
        candidates.append({
            "p2000_term": number,
            "incidents_with_task_and_term": support,
            "incidents_with_task_without_term": total - support,
            "single_task_incidents_with_term": solo,
            "single_task_single_term_incidents": exclusive,
            "multi_task_incidents_with_term": support - solo,
            "other_station_task_incidents_with_term": other,
            "coverage_percent": round(100 * support / total),
            "heuristic_score": score,
            "supporting_incident_ids": sorted(
                supporting_ids[number], key=int
            )[:_MAX_INCIDENT_EVIDENCE],
            "single_task_incident_ids": sorted(
                solo_ids[number], key=int
            )[:_MAX_INCIDENT_EVIDENCE],
        })
    candidates.sort(
        key=lambda item: (
            -item["single_task_single_term_incidents"],
            -item["single_task_incidents_with_term"],
            -item["incidents_with_task_and_term"],
            item["other_station_task_incidents_with_term"],
            item["p2000_term"],
        )
    )
    base["candidate_terms"] = candidates[:_MAX_CANDIDATES]
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None

    if not solo_rows:
        base["probe_status"] = "multi_task_only_no_per_task_attribution"
        base["candidate_evidence_grade"] = "multi_task_only"
        return base

    # Ties on all positive support metrics are ambiguous even if another
    # station happened to have lower shared-term counts.
    unambiguous = (
        second is None or
        (
            top["single_task_single_term_incidents"],
            top["single_task_incidents_with_term"],
            top["incidents_with_task_and_term"],
        ) > (
            second["single_task_single_term_incidents"],
            second["single_task_incidents_with_term"],
            second["incidents_with_task_and_term"],
        )
    )
    if not unambiguous:
        base["probe_status"] = "ambiguous_equally_supported_terms"
        base["candidate_evidence_grade"] = "ambiguous"
        return base

    if top["incidents_with_task_and_term"] < 2:
        base["candidate_evidence_grade"] = "insufficient"
        return base

    base["candidate_p2000_term"] = top["p2000_term"]
    base["candidate_heuristic_score"] = top["heuristic_score"]
    if (
        top["incidents_with_task_and_term"] >= 3
        and top["single_task_incidents_with_term"] >= 2
        and top["single_task_single_term_incidents"] >= 1
        and top["incidents_with_task_and_term"] / total >= 0.8
    ):
        base["probe_status"] = "strong_historical_candidate_not_verified"
        base["candidate_evidence_grade"] = "strong_historical_candidate"
    else:
        base["probe_status"] = "tentative_historical_candidate_not_verified"
        base["candidate_evidence_grade"] = "tentative_historical_candidate"
    return base
