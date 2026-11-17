"""Pure schedule helpers for safe spoken availability announcements."""
from __future__ import annotations

from datetime import datetime


def next_available_after(schedule: dict, boundary: datetime) -> datetime | None:
    """Find first roster-available moment at/after an override's end.

    Return None for incomplete/unverifiable schedules. All intervals must carry
    timezone-aware timestamps and explicit boolean availability.
    """
    if not schedule.get("complete", False) or boundary.tzinfo is None:
        return None
    intervals = []
    for raw in schedule.get("intervals", []) or []:
        if not isinstance(raw, dict) or type(raw.get("available")) is not bool:
            continue
        try:
            start = datetime.fromisoformat(raw["start_time"])
            end = datetime.fromisoformat(raw["end_time"])
        except (KeyError, TypeError, ValueError):
            continue
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            continue
        if end > boundary:
            intervals.append((start, end, raw["available"]))
    intervals.sort(key=lambda item: (item[0], item[1]))
    # Do not infer availability across gaps or contradictory overlapping data.
    cursor = boundary
    while True:
        covering = [i for i in intervals if i[0] <= cursor < i[1]]
        if covering:
            if any(i[2] is False for i in covering):
                cursor = max(i[1] for i in covering if i[2] is False)
                continue
            return cursor
        upcoming = [i for i in intervals if i[0] > cursor]
        if not upcoming:
            return None
        # In a genuine gap availability is unknown. Do not invent a return time.
        return None


def next_unavailable_after(schedule: dict, boundary: datetime) -> datetime | None:
    """First verifiable non-paraat time after a temporary override expires.

    A missing/gapped/contradictory roster returns None instead of a guess.
    This does not extend the real override's expiry.
    """
    if (
        not isinstance(schedule, dict)
        or schedule.get("complete") is not True
        or boundary.tzinfo is None
    ):
        return None
    rows = schedule.get("intervals")
    if not isinstance(rows, list) or not rows:
        return None
    parsed = []
    for raw in rows:
        if not isinstance(raw, dict) or type(raw.get("available")) is not bool:
            return None
        try:
            start = datetime.fromisoformat(raw["start_time"])
            end = datetime.fromisoformat(raw["end_time"])
        except (KeyError, TypeError, ValueError):
            return None
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            return None
        if end > boundary:
            parsed.append((start, end, raw["available"]))
    cursor = boundary
    for _ in range(len(parsed) * 2 + 2):
        covering = [r for r in parsed if r[0] <= cursor < r[1]]
        if not covering:
            return None
        if any(r[2] is False for r in covering):
            return None if any(r[2] is True for r in covering) else cursor
        next_points = [r[1] for r in covering]
        next_points.extend(r[0] for r in parsed if r[0] > cursor)
        next_cursor = min(next_points)
        if next_cursor <= cursor:
            return None
        cursor = next_cursor
    return None
