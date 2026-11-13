"""Bounded, one-page, anonymized task P2000 filter change diagnostics.

The task audit report is history, never a source of current task settings.
Only exact appliance-shaped tokens in relevant change text are exposed.
No raw audit rows, authors, change descriptions, membership or person data.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from .task_p2000_probe import choose_task_p2000_probe

_NUMERIC_UNIT = re.compile(r"(?<![0-9])0[0-9]{5}(?![0-9])")
_P2000_CONTEXT = re.compile(
    r"p2000|alarmer|incident|bericht|message|gms", re.IGNORECASE
)
_REQUIRED_CONTEXT = re.compile(
    r"vereist|benodig|required|must.contain|include|bevatten|"
    r"aanmaken.incident|create.incident|filter", re.IGNORECASE
)
_EXCLUDED_CONTEXT = re.compile(
    r"uitgesloten|exclud|ignore|negeer|intrekken", re.IGNORECASE
)
_MAX_RECORDS = 500
_MAX_CHANGE_LINES = 120
_MAX_RECORD_OUTPUT = 25


def choose_task_audit_probe(
    station_id: int | str,
    task_id: int | str,
    task_index: dict[Any, Any],
    page: int,
) -> dict[str, Any]:
    """Require one authorized, uniquely matched station task and page."""
    if type(page) is not int or not 1 <= page <= 5:
        raise ValueError("Only audit pages 1 through 5 are supported")
    selection = choose_task_p2000_probe(
        station_id, task_id, task_index, []
    )
    selection = {
        "station_id": selection["station_id"],
        "task_id": selection["task_id"],
        "task_name": selection["task_name"],
        "page": page,
        "probe_status": selection["probe_status"],
        "source": "single_task_historical_audit_log",
        "api_get_attempted": False,
        "api_endpoint": "reporting/general_report/audit_log/data",
        "audit_scope": "one_task_one_page",
        "audit_object_type": "task",
        "personal_data_returned": False,
        "raw_audit_changes_returned": False,
        "local_storage_modified": False,
        "brandweerrooster_modified": False,
        "current_task_vehicle_mapping_verified": False,
    }
    if selection["probe_status"] == "ready_for_single_task_GET":
        selection["probe_status"] = "ready_for_one_audit_page_GET"
    return selection


def _audit_value(record: dict[str, Any], key: str) -> Any:
    raw = record.get(key)
    return raw.get("value") if isinstance(raw, dict) else raw


def _safe_date(raw: Any) -> str | None:
    if not isinstance(raw, str) or len(raw) > 40:
        return None
    try:
        when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when.isoformat(timespec="seconds")


def _find_relevant_terms(change: str) -> tuple[list[str], bool]:
    """Only terms in task-filter-looking lines; never parse arbitrary IDs."""
    if len(change) > 50000:
        return [], False
    found = set()
    matched = False
    lines = change.splitlines()[:_MAX_CHANGE_LINES]
    for index, line in enumerate(lines):
        if _EXCLUDED_CONTEXT.search(line):
            continue
        if not (_P2000_CONTEXT.search(line) and _REQUIRED_CONTEXT.search(line)):
            continue
        matched = True
        # Some audit reports write the old/new values on the next lines.
        for candidate in lines[index:index + 3]:
            if _EXCLUDED_CONTEXT.search(candidate):
                break
            found.update(_NUMERIC_UNIT.findall(candidate))
    return sorted(found), matched


def summarize_task_audit_probe(
    selection: dict[str, Any], response: Any,
) -> dict[str, Any]:
    """Return bounded historical numeric evidence, never audit payloads."""
    base = {
        **selection,
        "api_get_attempted": True,
        "audit_record_count": 0,
        "audit_page_truncated": False,
        "filter_change_record_count": 0,
        "historical_numeric_p2000_terms": [],
        "matching_filter_change_examples": [],
        "vehicle_number": None,
        "mapping_source": None,
        "current_task_vehicle_mapping_verified": False,
        "interpretation": (
            "Task audit records are historical changes, not the current task "
            "configuration or a verified physical vehicle dispatch. Any numeric "
            "terms are context-limited clues only. No raw audit record, person, "
            "author, description or credential is returned."
        ),
    }
    if not isinstance(response, list):
        return {**base, "probe_status": "task_audit_unavailable_or_unexpected"}
    rows = response[:_MAX_RECORDS]
    base["audit_record_count"] = len(rows)
    base["audit_page_truncated"] = len(response) > _MAX_RECORDS
    terms = set()
    relevant_count = 0
    examples = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        changes = _audit_value(item, "changes")
        if not isinstance(changes, str):
            continue
        candidate_numbers, related = _find_relevant_terms(changes)
        if not related:
            continue
        relevant_count += 1
        terms.update(candidate_numbers)
        if len(examples) < _MAX_RECORD_OUTPUT:
            examples.append({
                "at": _safe_date(_audit_value(item, "created_at")),
                "numeric_terms": candidate_numbers[:15],
            })
    base["filter_change_record_count"] = relevant_count
    base["historical_numeric_p2000_terms"] = sorted(terms)[:40]
    base["matching_filter_change_examples"] = examples
    base["probe_status"] = "task_audit_page_readable"
    if terms:
        base["mapping_source"] = "historical_task_audit_changes_not_current"
    return base
