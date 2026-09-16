"""Shared incident store for FireServiceRota Extended."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN as FIRESERVICEROTA_DOMAIN

HISTORY_LIMIT = 25
ACTIVE_INCIDENT_REFRESH_SECONDS = 120
FAST_INCIDENT_REFRESH_SECONDS = 10
FAST_INCIDENT_REFRESH_WINDOW_SECONDS = 100

END_TIME_KEYS = (
    "end_time",
    "ended_at",
    "closed_at",
    "finished_at",
    "resolved_at",
    "completed_at",
    "cancelled_at",
    "canceled_at",
)
STATUS_KEYS = (
    "status",
    "state",
    "incident_status",
    "lifecycle_status",
    "lifecycle_state",
)
CLOSED_STATUS_VALUES = {
    "closed",
    "ended",
    "finished",
    "resolved",
    "completed",
    "cancelled",
    "canceled",
    "archived",
}
OPEN_STATUS_VALUES = {
    "active",
    "open",
    "ongoing",
    "running",
    "started",
    "new",
    "dispatched",
}
CLOSED_TRIGGER_VALUES = {
    "close",
    "closed",
    "end",
    "ended",
    "finish",
    "finished",
    "resolve",
    "resolved",
    "complete",
    "completed",
    "cancel",
    "cancelled",
    "canceled",
    "archive",
    "archived",
}
NEGATIVE_RESPONSE_VALUES = {
    "rejected",
    "expired",
    "cancelled",
    "canceled",
    "declined",
    "no_show",
}
POSITIVE_RESPONSE_VALUES = {
    "acknowledged",
    "accepted",
    "confirmed",
    "responding",
    "dispatched",
    "shown_up",
    "arrived",
    "at_station",
}


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an API timestamp into an aware datetime."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _timestamp(value: Any) -> float:
    """Return a sortable timestamp."""
    parsed = _parse_datetime(value)
    return parsed.timestamp() if parsed else 0.0


def _now_iso() -> str:
    """Return the current UTC time as ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def _as_int(value: Any, default: int = 0) -> int:
    """Convert an API numeric value to int without raising."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class IncidentStore:
    """Keep unique incidents by API id for active overview and history."""

    def __init__(self, hass: HomeAssistant, client, entry_id: str) -> None:
        """Initialize the incident store."""
        self._hass = hass
        self._client = client
        self._entry_id = entry_id
        self._incidents: dict[str, dict] = {}
        self._latest_incident_id: Any = None
        self._last_rest_refresh: dict[str, float] = {}
        self._refresh_lock = asyncio.Lock()
        self._fast_refresh_tasks: dict[str, asyncio.Task] = {}

    @property
    def signal(self) -> str:
        """Return the dispatcher signal used by the overview sensors."""
        return f"{FIRESERVICEROTA_DOMAIN}_{self._entry_id}_incident_store_update"

    @property
    def latest_incident_id(self):
        """Return the most recently received live incident id."""
        return self._latest_incident_id

    def _notify(self) -> None:
        """Notify overview/history sensors that the store changed."""
        async_dispatcher_send(self._hass, self.signal)

    @staticmethod
    def _key(incident_id: Any) -> str:
        """Return a stable dictionary key for an incident id."""
        return str(incident_id)

    @staticmethod
    def _lifecycle_fields(data: dict) -> dict:
        """Expose scalar lifecycle-looking REST fields for safe diagnostics."""
        fields = {}
        for key, value in data.items():
            lowered = str(key).lower()
            lifecycle_like = (
                lowered in STATUS_KEYS
                or lowered in END_TIME_KEYS
                or lowered in {
                    "created_at",
                    "updated_at",
                    "active",
                    "closed",
                    "ended",
                    "finished",
                    "resolved",
                    "completed",
                    "cancelled",
                    "canceled",
                }
                or any(
                    token in lowered
                    for token in (
                        "status",
                        "state",
                        "closed",
                        "ended",
                        "finish",
                        "resolved",
                        "complete",
                        "cancel",
                    )
                )
            )
            if lifecycle_like and (
                value is None or isinstance(value, (str, int, float, bool))
            ):
                fields[key] = value
        return fields

    @staticmethod
    def _first_value(data: dict, keys: tuple[str, ...]) -> Any:
        """Return the first present, non-empty value from a key list."""
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                return value
        return None

    def _station_info(self, group_id: Any) -> dict:
        """Resolve a station/group id without hard-coded local station data."""
        if group_id is None:
            return {}

        for group in self._client.groups or []:
            if group.get("id") != group_id:
                continue
            return {
                "id": group_id,
                "name": group.get("name"),
                "short_code": group.get("short_code"),
                "type": group.get("type"),
            }

        membership = self._client.membership_index.get(group_id, {})
        if membership:
            return {
                "id": membership.get("station_id"),
                "name": membership.get("station_name"),
                "short_code": membership.get("station_short_code"),
                "type": "station",
            }
        return {"id": group_id}

    def _resolved_task_entries(self, task_ids: list) -> list[dict]:
        """Return compact task/station metadata for requirement task ids."""
        resolved = []
        seen = set()
        for task_id in task_ids:
            indexed = self._client.task_index.get(task_id, []) or []
            if indexed:
                for task in indexed:
                    key = (task_id, task.get("station_id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    resolved.append(
                        {
                            "id": task_id,
                            "name": task.get("name"),
                            "station_id": task.get("station_id"),
                            "station_name": task.get("station_name"),
                            "station_short_code": task.get("station_short_code"),
                        }
                    )
                continue

            # Keep the task usable even when the authenticated user's discovery
            # index does not contain it (for example a future other station).
            resolved.append({"id": task_id})
        return resolved

    @staticmethod
    def _response_is_responding(response: dict) -> bool:
        """Return whether a response represents an intended turnout."""
        status = str(response.get("status") or "").strip().lower()
        reported = str(response.get("reported_status") or "").strip().lower()
        if status in NEGATIVE_RESPONSE_VALUES or reported in NEGATIVE_RESPONSE_VALUES:
            return False
        if status in POSITIVE_RESPONSE_VALUES or reported in POSITIVE_RESPONSE_VALUES:
            return True
        return bool(response.get("responded_at"))

    def _normalize_response(self, response: dict) -> dict:
        """Return an automation-friendly response without photo/blob data."""
        station = self._station_info(response.get("group_id"))
        return {
            "membership_id": response.get("membership_id"),
            "user_id": response.get("user_id"),
            "group_id": response.get("group_id"),
            "station_id": station.get("id", response.get("group_id")),
            "station_name": station.get("name"),
            "station_short_code": station.get("short_code"),
            "status": response.get("status"),
            "reported_status": response.get("reported_status"),
            "responded_at": response.get("responded_at"),
            "arrived_at_station": response.get("arrived_at_station"),
            "estimated_time_of_arrival": response.get("estimated_time_of_arrival"),
            "assigned_skill_ids": list(response.get("assigned_skill_ids") or []),
            "responding": self._response_is_responding(response),
        }

    def _normalize_staffing(self, data: dict) -> dict | None:
        """Normalize dynamic incident assignments and crew sufficiency.

        The BrandweerRooster incident payload contains three useful structures:
        incident_responses (who responded), incident_skill_assignments (the live
        crew assignment) and warning_statuses (the requirement/skill model). This
        method joins them generically. No priority, station or local vehicle is
        hard-coded here.
        """
        raw_responses = data.get("incident_responses")
        raw_assignments = data.get("incident_skill_assignments")
        raw_warnings = data.get("warning_statuses")
        if not any(isinstance(value, list) for value in (raw_responses, raw_assignments, raw_warnings)):
            return None

        responses = [item for item in (raw_responses or []) if isinstance(item, dict)]
        assignments = [item for item in (raw_assignments or []) if isinstance(item, dict)]
        warnings = [item for item in (raw_warnings or []) if isinstance(item, dict)]

        response_by_membership = {
            response.get("membership_id"): response
            for response in responses
            if response.get("membership_id") is not None
        }
        response_by_user = {
            response.get("user_id"): response
            for response in responses
            if response.get("user_id") is not None
        }

        skill_meta: dict[Any, dict] = {}
        skill_to_tasks: dict[Any, set] = {}
        for warning in warnings:
            requirement = warning.get("availability_requirement") or {}
            task_ids = list(requirement.get("task_ids") or [])
            for status in warning.get("skill_statuses", []) or []:
                if not isinstance(status, dict) or status.get("skill_id") is None:
                    continue
                skill_meta[status.get("skill_id")] = {
                    "id": status.get("skill_id"),
                    "short_code": status.get("short_code"),
                    "level": status.get("level"),
                    "minimum": status.get("minimum"),
                    "buffer": status.get("buffer"),
                    "api_assigned_count": status.get("assigned_count"),
                    "available_count": len(status.get("available_memberships") or []),
                }
            for spec in requirement.get("single_skill_availability_requirements", []) or []:
                if not isinstance(spec, dict) or spec.get("skill_id") is None:
                    continue
                skill_to_tasks.setdefault(spec.get("skill_id"), set()).update(task_ids)

        crew_assignments = []
        for assignment in assignments:
            response = response_by_membership.get(assignment.get("membership_id"))
            if response is None:
                response = response_by_user.get(assignment.get("user_id"), {})
            station = self._station_info((response or {}).get("group_id"))
            skill_ids = list(assignment.get("skill_ids") or [])
            skills = []
            task_ids = set()
            for skill_id in skill_ids:
                meta = dict(skill_meta.get(skill_id) or {"id": skill_id})
                skills.append(meta)
                task_ids.update(skill_to_tasks.get(skill_id, set()))

            crew_assignments.append(
                {
                    "assignment_id": assignment.get("id"),
                    "membership_id": assignment.get("membership_id"),
                    "user_id": assignment.get("user_id"),
                    "user_name": (response or {}).get("user_name"),
                    "user_nickname": (response or {}).get("user_nickname"),
                    "group_id": (response or {}).get("group_id"),
                    "station_id": station.get("id", (response or {}).get("group_id")),
                    "station_name": station.get("name"),
                    "station_short_code": station.get("short_code"),
                    "skill_ids": skill_ids,
                    "skills": skills,
                    "task_ids": sorted(task_ids),
                    "tasks": self._resolved_task_entries(sorted(task_ids)),
                    "status": (response or {}).get("status"),
                    "reported_status": (response or {}).get("reported_status"),
                    "responded_at": (response or {}).get("responded_at"),
                    "arrived_at_station": (response or {}).get("arrived_at_station"),
                    "responding": self._response_is_responding(response or {}),
                }
            )

        own_user_id = self._client.user_data.get("id") if self._client.user_data else None
        own_responses = [
            self._normalize_response(response)
            for response in responses
            if own_user_id is not None and response.get("user_id") == own_user_id
        ]
        own_assignments = [
            assignment
            for assignment in crew_assignments
            if own_user_id is not None and assignment.get("user_id") == own_user_id
        ]
        own_skill_codes = []
        own_task_names = []
        for assignment in own_assignments:
            for skill in assignment.get("skills", []):
                code = skill.get("short_code")
                if code and code not in own_skill_codes:
                    own_skill_codes.append(code)
            for task in assignment.get("tasks", []):
                name = task.get("name")
                if name and name not in own_task_names:
                    own_task_names.append(name)

        crew_requirements = []
        for warning in warnings:
            requirement = warning.get("availability_requirement") or {}
            task_ids = list(requirement.get("task_ids") or [])
            resolved_tasks = self._resolved_task_entries(task_ids)
            station_ids = sorted(
                {
                    task.get("station_id")
                    for task in resolved_tasks
                    if task.get("station_id") is not None
                }
            )
            skill_status_index = {
                status.get("skill_id"): status
                for status in (warning.get("skill_statuses", []) or [])
                if isinstance(status, dict) and status.get("skill_id") is not None
            }
            skills = []
            for spec in requirement.get("single_skill_availability_requirements", []) or []:
                if not isinstance(spec, dict):
                    continue
                skill_id = spec.get("skill_id")
                required = max(0, _as_int(spec.get("assigned"), 0))
                actual = sum(
                    1
                    for assignment in assignments
                    if skill_id in (assignment.get("skill_ids") or [])
                )
                api_status = skill_status_index.get(skill_id, {})
                short_code = api_status.get("short_code") or skill_meta.get(skill_id, {}).get("short_code")
                skills.append(
                    {
                        "skill_id": skill_id,
                        "short_code": short_code,
                        "required": required,
                        "standby_required": max(0, _as_int(spec.get("standby"), 0)),
                        "assigned": actual,
                        "filled": min(actual, required) if required else 0,
                        "sufficient": actual >= required,
                        "level": api_status.get("level"),
                        "minimum": api_status.get("minimum"),
                        "buffer": api_status.get("buffer"),
                        "available_count": len(api_status.get("available_memberships") or []),
                        "api_assigned_count": api_status.get("assigned_count"),
                    }
                )

            sufficient = all(skill.get("sufficient") for skill in skills) if skills else None
            required_total = sum(skill.get("required", 0) for skill in skills)
            filled_total = sum(skill.get("filled", 0) for skill in skills)
            required_skill_ids = {skill.get("skill_id") for skill in skills}
            assigned_members = {
                assignment.get("membership_id")
                for assignment in assignments
                if assignment.get("membership_id") is not None
                and required_skill_ids.intersection(assignment.get("skill_ids") or [])
            }

            relevant_responses = responses
            if station_ids:
                relevant_responses = [
                    response
                    for response in responses
                    if response.get("group_id") in station_ids
                ]
            responding_members = {
                response.get("membership_id")
                for response in relevant_responses
                if response.get("membership_id") is not None
                and self._response_is_responding(response)
            }
            reserve_members = responding_members - assigned_members

            crew_requirements.append(
                {
                    "availability_requirement_id": requirement.get("id"),
                    "name": requirement.get("name"),
                    "short_code": requirement.get("short_code"),
                    "service_level": warning.get("service_level"),
                    "warning_level": warning.get("warning_level"),
                    "task_ids": task_ids,
                    "tasks": resolved_tasks,
                    "station_ids": station_ids,
                    "skills": skills,
                    "required_positions": required_total,
                    "filled_positions": filled_total,
                    "sufficient": sufficient,
                    "responding_count": len(responding_members),
                    "assigned_member_count": len(assigned_members),
                    "reserve_responding_count": len(reserve_members),
                }
            )

        known_sufficiency = [
            requirement.get("sufficient")
            for requirement in crew_requirements
            if requirement.get("sufficient") is not None
        ]
        overall_sufficient = all(known_sufficiency) if known_sufficiency else None
        all_responding_members = {
            response.get("membership_id")
            for response in responses
            if response.get("membership_id") is not None
            and self._response_is_responding(response)
        }
        all_assigned_members = {
            assignment.get("membership_id")
            for assignment in assignments
            if assignment.get("membership_id") is not None
        }

        return {
            "crew_assignments": crew_assignments,
            "crew_requirements": crew_requirements,
            "crew_summary": {
                "sufficient": overall_sufficient,
                "responding_count": len(all_responding_members),
                "assigned_member_count": len(all_assigned_members),
                "reserve_responding_count": len(all_responding_members - all_assigned_members),
            },
            "own_responses": own_responses,
            "own_response": next(
                (response for response in own_responses if response.get("responding")),
                own_responses[0] if own_responses else None,
            ),
            "own_responding": any(response.get("responding") for response in own_responses),
            "own_assignment": {
                "assigned": bool(own_assignments),
                "skill_codes": own_skill_codes,
                "task_names": own_task_names,
                "assignments": own_assignments,
            },
        }

    def _apply_staffing(self, snapshot: dict, data: dict, previous: dict) -> None:
        """Merge normalized staffing fields and maintain a revision timestamp."""
        normalized = self._normalize_staffing(data)
        if normalized is None:
            return

        compared_keys = (
            "crew_assignments",
            "crew_requirements",
            "crew_summary",
            "own_responses",
            "own_response",
            "own_responding",
            "own_assignment",
        )
        changed = any(previous.get(key) != normalized.get(key) for key in compared_keys)
        snapshot.update(normalized)
        if changed:
            snapshot["assignment_revision"] = _as_int(previous.get("assignment_revision"), 0) + 1
            snapshot["assignment_last_changed_at"] = _now_iso()
            snapshot["assignment_final"] = False
            snapshot.pop("assignment_finalized_at", None)
        else:
            snapshot.setdefault("assignment_revision", _as_int(previous.get("assignment_revision"), 0))

    def _compact_snapshot(
        self,
        data: dict,
        previous: dict | None,
        source: str,
        default_active: bool | None,
    ) -> dict:
        """Build a compact, dashboard-friendly incident snapshot."""
        previous = previous or {}
        snapshot = dict(previous)

        for key in (
            "id",
            "body",
            "trigger",
            "created_at",
            "updated_at",
            "prio",
            "type",
            "responder_mode",
            "can_respond_until",
            "task_ids",
            "previous_task_ids",
            "new_task_ids",
            "resolved_tasks",
            "resolved_stations",
            "responses_by_station",
            "first_seen_at",
            "last_seen_at",
        ):
            if key in data and data[key] is not None:
                value = data[key]
                if isinstance(value, list):
                    value = list(value)
                snapshot[key] = value

        self._apply_staffing(snapshot, data, previous)

        address = data.get("address")
        if isinstance(address, dict):
            snapshot["address"] = {
                key: address.get(key)
                for key in (
                    "latitude",
                    "longitude",
                    "address_type",
                    "formatted_address",
                )
                if address.get(key) is not None
            }
        else:
            flat_address = {
                key: data.get(key)
                for key in (
                    "latitude",
                    "longitude",
                    "address_type",
                    "formatted_address",
                )
                if data.get(key) is not None
            }
            if flat_address:
                snapshot["address"] = flat_address

        previous_lifecycle = previous.get("lifecycle_fields")
        lifecycle = dict(previous_lifecycle) if isinstance(previous_lifecycle, dict) else {}
        restored_lifecycle = data.get("lifecycle_fields")
        if isinstance(restored_lifecycle, dict):
            lifecycle.update(restored_lifecycle)
        lifecycle.update(self._lifecycle_fields(data))
        if lifecycle:
            snapshot["lifecycle_fields"] = lifecycle

        ended_at = self._first_value(data, END_TIME_KEYS)
        if ended_at is None:
            ended_at = self._first_value(lifecycle, END_TIME_KEYS)
        if ended_at is None:
            ended_at = data.get("incident_ended_at")
        if ended_at is None:
            ended_at = previous.get("incident_ended_at")

        raw_status = self._first_value(data, STATUS_KEYS)
        if raw_status is None:
            raw_status = self._first_value(lifecycle, STATUS_KEYS)

        active = previous.get("incident_active")
        lifecycle_known = bool(previous.get("lifecycle_known", False))
        explicit_lifecycle = False
        if source == "restore" and isinstance(data.get("incident_active"), bool):
            active = data["incident_active"]
        if source == "restore" and isinstance(data.get("lifecycle_known"), bool):
            lifecycle_known = data["lifecycle_known"]

        if ended_at is not None:
            active = False
            lifecycle_known = True
            explicit_lifecycle = True
        else:
            status_text = str(raw_status).strip().lower() if raw_status is not None else ""
            if status_text in CLOSED_STATUS_VALUES:
                active = False
                lifecycle_known = True
                explicit_lifecycle = True
            elif status_text in OPEN_STATUS_VALUES:
                active = True
                lifecycle_known = True
                explicit_lifecycle = True

            if isinstance(data.get("active"), bool):
                active = data["active"]
                lifecycle_known = True
                explicit_lifecycle = True

            for key in (
                "closed",
                "ended",
                "finished",
                "resolved",
                "completed",
                "cancelled",
                "canceled",
            ):
                if data.get(key) is True:
                    active = False
                    lifecycle_known = True
                    explicit_lifecycle = True
                    break

            trigger = str(data.get("trigger") or "").strip().lower()
            if trigger in CLOSED_TRIGGER_VALUES:
                active = False
                lifecycle_known = True
            elif (
                source == "websocket"
                and trigger in {"new", "update"}
                and not explicit_lifecycle
            ):
                # A websocket update means the incident is live only when the
                # payload does not itself contain an explicit lifecycle state.
                # For example, BrandweerRooster can send trigger=update together
                # with state=finished; finished must win in that case.
                active = True

        if active is None and default_active is not None:
            active = default_active
        if active is None and source == "websocket":
            active = True
        if active is None:
            active = True

        snapshot["incident_active"] = bool(active)
        snapshot["lifecycle_known"] = lifecycle_known
        snapshot["incident_status"] = (
            str(raw_status)
            if raw_status not in (None, "")
            else ("active" if active else "closed")
        )
        if ended_at is not None:
            snapshot["incident_ended_at"] = ended_at
        elif active:
            snapshot.pop("incident_ended_at", None)

        snapshot.setdefault("first_seen_at", _now_iso())
        if source != "restore":
            snapshot["last_seen_at"] = _now_iso()
        else:
            snapshot.setdefault("last_seen_at", snapshot.get("first_seen_at"))
        snapshot["last_source"] = source
        return snapshot

    def _prune(self) -> None:
        """Keep all active incidents and a bounded number of closed incidents."""
        closed = [
            (key, value)
            for key, value in self._incidents.items()
            if value.get("incident_active") is False
        ]
        closed.sort(
            key=lambda item: _timestamp(
                item[1].get("incident_ended_at")
                or item[1].get("updated_at")
                or item[1].get("created_at")
                or item[1].get("first_seen_at")
            ),
            reverse=True,
        )
        for key, _ in closed[HISTORY_LIMIT:]:
            self._incidents.pop(key, None)
            self._last_rest_refresh.pop(key, None)

    def _ensure_fast_refresh(self, incident_id: Any) -> None:
        """Start a short high-frequency REST refresh window for live assignments."""
        if incident_id is None:
            return
        key = self._key(incident_id)
        existing = self._fast_refresh_tasks.get(key)
        if existing is not None and not existing.done():
            return
        self._fast_refresh_tasks[key] = self._hass.async_create_task(
            self._async_fast_refresh(incident_id)
        )

    async def _async_fast_refresh(self, incident_id: Any) -> None:
        """Refresh a new/updated incident every 10 seconds for about 100 seconds."""
        key = self._key(incident_id)
        elapsed = 0
        try:
            while elapsed < FAST_INCIDENT_REFRESH_WINDOW_SECONDS:
                await asyncio.sleep(FAST_INCIDENT_REFRESH_SECONDS)
                elapsed += FAST_INCIDENT_REFRESH_SECONDS
                current = self._incidents.get(key)
                if not current or current.get("incident_active") is False:
                    return

                async with self._refresh_lock:
                    incident = await self._client.async_get_incident(incident_id)
                    self._last_rest_refresh[key] = time.monotonic()
                    if not isinstance(incident, dict):
                        continue
                    existing = self.get_raw(incident_id) or {"id": incident_id}
                    merged = dict(existing)
                    merged.update(incident)
                    for preserve in ("trigger", "previous_task_ids", "new_task_ids"):
                        if preserve not in incident and preserve in existing:
                            merged[preserve] = existing[preserve]
                    enriched = self._client.enrich_incident_data(merged)
                    self.upsert(enriched, source="rest")

            current = self._incidents.get(key)
            if current and current.get("incident_active") is not False:
                current["assignment_final"] = True
                current["assignment_finalized_at"] = _now_iso()
                self._notify()
                self._hass.bus.async_fire(
                    f"{FIRESERVICEROTA_DOMAIN}_assignment_finalized",
                    {"entry_id": self._entry_id, "incident_id": incident_id},
                )
        finally:
            self._fast_refresh_tasks.pop(key, None)

    def upsert(
        self,
        data: dict,
        *,
        source: str,
        default_active: bool | None = None,
        notify: bool = True,
    ) -> dict | None:
        """Insert or update one incident without creating duplicate history rows."""
        incident_id = data.get("id")
        if incident_id is None:
            return None

        key = self._key(incident_id)
        previous = self._incidents.get(key)
        snapshot = self._compact_snapshot(data, previous, source, default_active)
        self._incidents[key] = snapshot

        if source == "websocket":
            self._latest_incident_id = incident_id
            if snapshot.get("incident_active") is not False:
                # WebSocket updates can include task/vehicle changes; if a prior
                # fast window has finished, start a fresh short observation window.
                snapshot["assignment_final"] = False
                snapshot.pop("assignment_finalized_at", None)
                self._ensure_fast_refresh(incident_id)
        elif self._latest_incident_id is None:
            self._latest_incident_id = incident_id

        self._prune()
        if notify:
            self._notify()
        return snapshot

    def restore(self, incidents: list, *, active: bool) -> None:
        """Restore incident snapshots from a RestoreEntity attribute."""
        changed = False
        for incident in incidents:
            if not isinstance(incident, dict) or incident.get("id") is None:
                continue
            restored = dict(incident)
            restored["incident_active"] = active
            self.upsert(
                restored,
                source="restore",
                default_active=active,
                notify=False,
            )
            changed = True
        if changed:
            self._notify()

    def get_raw(self, incident_id: Any) -> dict | None:
        """Return the internal compact snapshot for one incident."""
        if incident_id is None:
            return None
        snapshot = self._incidents.get(self._key(incident_id))
        return dict(snapshot) if snapshot else None

    @staticmethod
    def _public_snapshot(snapshot: dict) -> dict:
        """Return a copy with live duration and convenient address fields."""
        public = dict(snapshot)
        address = public.get("address")
        if isinstance(address, dict):
            for key in (
                "latitude",
                "longitude",
                "address_type",
                "formatted_address",
            ):
                if address.get(key) is not None:
                    public[key] = address[key]

        start = _parse_datetime(public.get("created_at"))
        if start is not None:
            if public.get("incident_active"):
                end = datetime.now(timezone.utc)
            else:
                end = _parse_datetime(public.get("incident_ended_at"))
            if end is not None:
                public["duration_seconds"] = max(0, int((end - start).total_seconds()))
            else:
                public["duration_seconds"] = None
        else:
            public["duration_seconds"] = None
        return public

    def get_public(self, incident_id: Any) -> dict | None:
        """Return one public snapshot."""
        raw = self.get_raw(incident_id)
        return self._public_snapshot(raw) if raw else None

    @property
    def active_incidents(self) -> list[dict]:
        """Return all currently active/ongoing incidents, newest first."""
        incidents = [
            self._public_snapshot(snapshot)
            for snapshot in self._incidents.values()
            if snapshot.get("incident_active") is not False
        ]
        return sorted(
            incidents,
            key=lambda item: _timestamp(item.get("created_at") or item.get("first_seen_at")),
            reverse=True,
        )

    @property
    def history(self) -> list[dict]:
        """Return closed incidents, each incident id only once, newest first."""
        incidents = [
            self._public_snapshot(snapshot)
            for snapshot in self._incidents.values()
            if snapshot.get("incident_active") is False
        ]
        return sorted(
            incidents,
            key=lambda item: _timestamp(
                item.get("incident_ended_at")
                or item.get("updated_at")
                or item.get("created_at")
                or item.get("first_seen_at")
            ),
            reverse=True,
        )[:HISTORY_LIMIT]

    def mark_rest_refreshed(self, incident_id: Any) -> None:
        """Record when an incident was last refreshed through REST."""
        if incident_id is not None:
            self._last_rest_refresh[self._key(incident_id)] = time.monotonic()

    async def async_refresh_active(self) -> None:
        """Periodically refresh active incidents so API closure is detected."""
        if not self.active_incidents:
            return

        async with self._refresh_lock:
            now = time.monotonic()
            changed = False
            for public in list(self.active_incidents):
                incident_id = public.get("id")
                if incident_id is None:
                    continue
                key = self._key(incident_id)
                if now - self._last_rest_refresh.get(key, 0) < ACTIVE_INCIDENT_REFRESH_SECONDS:
                    continue

                incident = await self._client.async_get_incident(incident_id)
                self._last_rest_refresh[key] = time.monotonic()
                if not isinstance(incident, dict):
                    continue

                existing = self.get_raw(incident_id) or {"id": incident_id}
                merged = dict(existing)
                merged.update(incident)
                for preserve in ("trigger", "previous_task_ids", "new_task_ids"):
                    if preserve not in incident and preserve in existing:
                        merged[preserve] = existing[preserve]

                enriched = self._client.enrich_incident_data(merged)
                self.upsert(enriched, source="rest", notify=False)
                changed = True

            if changed:
                self._notify()
