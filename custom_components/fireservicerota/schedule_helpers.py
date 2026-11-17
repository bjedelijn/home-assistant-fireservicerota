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
    """First proven non-paraat time after a temporary override ends.

    Read-only informational lookup; never extends the override. A complete,
    contiguous, unambiguous schedule is required. If the base schedule is
    already unavailable at the boundary, return that boundary.
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
    for row in rows:
        if not isinstance(row, dict) or type(row.get("available")) is not bool:
            return None
        try:
            start = datetime.fromisoformat(row["start_time"])
            end = datetime.fromisoformat(row["end_time"])
        except (KeyError, TypeError, ValueError):
            return None
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            return None
        if end > boundary:
            parsed.append((start, end, row["available"]))
    parsed.sort(key=lambda item: (item[0], item[1]))
    if not parsed:
        return None

    cursor = boundary
    while True:
        covering = [row for row in parsed if row[0] <= cursor < row[1]]
        if not covering:
            return None  # A gap is unknown; never claim continuous paraat.
        if any(row[2] is False for row in covering):
            if any(row[2] is True for row in covering):
                return None  # Conflicting overlap.
            return cursor
        # Advance only to an interval end whose next segment can be checked.
        next_end = min(row[1] for row in covering)
        if next_end <= cursor:
            return None
        cursor = next_end
