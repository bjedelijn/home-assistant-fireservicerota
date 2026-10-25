"""Bounded, read-only inspection of the P2000 terms configured on one task.

The provider's web interface shows task-specific required P2000 message terms,
which may contain a six-digit Dutch appliance number. A task's GMS/alerting
settings can be richer than the task embedded in cached group discovery.
Inspect only allowlisted field *names* and exact six-digit required terms; never
return or cache raw API payloads or personal/group membership details.
"""

from __future__ import annotations

import re
from typing import Any

from .historical_fairness import _id

_KEY = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
_VEHICLE = re.compile(r"^0[0-9]{5}$")
_REDACT = re.compile(
    r"member|person|user|secret|token|password|credential|contact|"
    r"telephone|phone|email|address|location|coordinate|audit|capcode",
    re.IGNORECASE,
)
_MAX_TASKS = 25
_MAX_KEYS = 80
_MAX_NODES = 120
_MAX_DEPTH = 4
_MAX_PATHS = 20


def _safe_key(value: Any) -> str | None:
    if not isinstance(value, str) or not _KEY.fullmatch(value) or _REDACT.search(value):
        return None
    return value


def _required_p2000_field(path: tuple[str, ...]) -> bool:
    """Recognize required message *terms*, never excluded terms or IDs."""
    if not path:
        return False
    combined = "_".join(path).casefold()
    if any(
        token in combined
        for token in ("exclude", "without", "not_contain", "negative", "ignore")
    ):
        return False
    leaf = path[-1].casefold()
    explicit = {
        "required_terms", "required_words", "include_terms",
        "required_p2000_terms", "p2000_required_terms",
        "p2000_required_keywords", "p2000_message_required_terms",
        "required_terms_in_p2000_message", "message_required_terms",
        "message_required_keywords", "incident_required_terms",
        "incident_text_required_terms",
    }
    if leaf in explicit:
        return True
    required = any(
        part in combined
        for part in ("required", "include", "must_contain", "contains")
    )
    message = any(
        part in combined for part in ("p2000", "message", "text", "term", "keyword")
    )
    return required and message


def _tokens(value: Any) -> set[str]:
    """Only exact six-digit tokens; never extract arbitrary digits from text."""
    if isinstance(value, str):
        # Multiple explicit required terms can be separated by commas/semicolons.
        items = re.split(r"[,;\\n]", value)
        return {
            token.strip()
            for token in items
            if _VEHICLE.fullmatch(token.strip())
        }
    if isinstance(value, list) and len(value) <= 20:
        found = set()
        for item in value:
            if isinstance(item, str) and _VEHICLE.fullmatch(item.strip()):
                found.add(item.strip())
        return found
    return set()


def inspect_task_fields(task: Any) -> dict[str, Any]:
    """Sanitize any provider object to a bounded, identity-free field preview."""
    if not isinstance(task, dict):
        return {
            "field_names": [],
            "required_vehicle_terms": [],
            "recognized_required_term_paths": [],
        }
    keys = sorted(
        {key for key in task if _safe_key(key) is not None}
    )[:_MAX_KEYS]
    nodes = 0
    vehicle_terms: set[str] = set()
    paths: set[str] = set()

    def walk(obj: Any, path: tuple[str, ...], depth: int) -> None:
        nonlocal nodes
        if not isinstance(obj, dict) or depth >= _MAX_DEPTH:
            return
        for raw_key, value in list(obj.items())[:_MAX_NODES]:
            nodes += 1
            if nodes > _MAX_NODES:
                return
            key = _safe_key(raw_key)
            if key is None:
                continue
            next_path = (*path, key)
            if _required_p2000_field(next_path):
                paths.add(".".join(next_path))
                vehicle_terms.update(_tokens(value))
            # Stay within task configuration dictionaries only. Do not
            # traverse membership, people, responses, lists or raw messages.
            if isinstance(value, dict):
                walk(value, next_path, depth + 1)
    walk(task, (), 0)
    return {
        "field_names": keys,
        "required_vehicle_terms": sorted(vehicle_terms)[:_MAX_PATHS],
        "recognized_required_term_paths": sorted(paths)[:_MAX_PATHS],
    }


def choose_task_p2000_probe(
    station_id: int | str,
    task_id: int | str,
    task_index: dict[Any, Any],
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require a uniquely known task at the authorized station."""
    station = _id(station_id)
    task = _id(task_id)
    if (
        station is None or task is None
        or len(station) > 15 or len(task) > 15
    ):
        raise ValueError("Numeric station and task IDs are required")
    base = {
        "station_id": station,
        "task_id": task,
        "task_name": None,
        "probe_status": "unverified",
        "source": "cached_groups_and_one_optional_authenticated_task_GET",
        "api_get_attempted": False,
        "api_endpoint": "tasks/<selected>",
        "api_task_id_matches": None,
        "cached_task_records_found": 0,
        "cached_task_field_names": [],
        "cached_required_p2000_vehicle_terms": [],
        "cached_required_term_paths": [],
        "api_task_field_names": [],
        "api_required_p2000_vehicle_terms": [],
        "api_required_term_paths": [],
        "vehicle_mapping_status": "unverified",
        "vehicle_number": None,
        "brandweerrooster_modified": False,
        "local_storage_modified": False,
        "personal_data_returned": False,
        "operational_vehicle_dispatch_verified": False,
    }
    matched = [
        item
        for candidate_id, entries in (task_index or {}).items()
        if _id(candidate_id) == task and isinstance(entries, list)
        for item in entries
        if isinstance(item, dict)
        and _id(item.get("id")) == task
        and _id(item.get("station_id")) == station
    ]
    if len(matched) != 1:
        return {
            **base,
            "probe_status": "task_not_uniquely_indexed_for_this_station",
        }
    name = matched[0].get("name")
    if (
        isinstance(name, str) and 1 <= len(name) <= 40
        and re.fullmatch(r"[a-zA-Z0-9 ._()/-]+", name)
    ):
        base["task_name"] = name

    raw_tasks = [
        item
        for group in (groups or [])[:100]
        if isinstance(group, dict)
        for item in (group.get("tasks") or [])[:_MAX_TASKS]
        if isinstance(item, dict)
        and _id(item.get("id")) == task
        and (
            not isinstance(item.get("station_ids"), list)
            or any(_id(s) == station for s in item["station_ids"])
        )
    ]
    base["cached_task_records_found"] = len(raw_tasks)
    if raw_tasks:
        scans = [inspect_task_fields(item) for item in raw_tasks[:_MAX_TASKS]]
        base["cached_task_field_names"] = sorted({
            name for scan in scans for name in scan["field_names"]
        })[:_MAX_KEYS]
        base["cached_required_p2000_vehicle_terms"] = sorted({
            num for scan in scans for num in scan["required_vehicle_terms"]
        })[:_MAX_PATHS]
        base["cached_required_term_paths"] = sorted({
            path for scan in scans for path in scan["recognized_required_term_paths"]
        })[:_MAX_PATHS]
    base["probe_status"] = "ready_for_single_task_GET"
    return base


def summarize_task_p2000_probe(
    selection: dict[str, Any],
    api_response: Any,
) -> dict[str, Any]:
    """Return only task-specific P2000 required terms, no raw task payload."""
    base = {
        **selection,
        "api_get_attempted": True,
        "api_task_field_names": [],
        "api_required_p2000_vehicle_terms": [],
        "api_required_term_paths": [],
        "api_task_id_matches": None,
    }
    if not isinstance(api_response, dict):
        base["probe_status"] = "task_api_unavailable_or_permission_denied"
        return base
    task = (
        api_response.get("task")
        if isinstance(api_response.get("task"), dict)
        else api_response
    )
    if _id(task.get("id")) != selection.get("task_id"):
        base["api_task_id_matches"] = False
        base["probe_status"] = "api_task_id_mismatch"
        return base
    base["api_task_id_matches"] = True
    api_fields = inspect_task_fields(task)
    base["api_task_field_names"] = api_fields["field_names"]
    base["api_required_p2000_vehicle_terms"] = (
        api_fields["required_vehicle_terms"]
    )
    base["api_required_term_paths"] = (
        api_fields["recognized_required_term_paths"]
    )
    api_terms = api_fields["required_vehicle_terms"]
    cached_terms = base["cached_required_p2000_vehicle_terms"]
    if api_terms:
        candidate_source = "live_task_api_required_message_filter"
        numbers = api_terms
    elif cached_terms:
        candidate_source = "cached_group_task_required_message_filter"
        numbers = cached_terms
    else:
        candidate_source = None
        numbers = []
    base["vehicle_mapping_status"] = (
        "one_explicit_required_p2000_number"
        if len(numbers) == 1 else
        "multiple_required_p2000_numbers"
        if len(numbers) > 1 else
        "no_supported_required_p2000_field_found"
    )
    base["vehicle_number"] = numbers[0] if len(numbers) == 1 else None
    base["vehicle_mapping_source"] = candidate_source
    base["probe_status"] = "task_detail_readable"
    base["interpretation"] = (
        "A six-digit P2000 required message term is a configured task-matching "
        "filter, not proof that this appliance actually attended every incident. "
        "Only safely recognized required terms are included. Other fields, "
        "personal data, raw API responses and excluded terms are omitted. "
        "This experiment makes one read-only GET and does not persist mappings."
    )
    return base
