"""Structured escalation milestones derived from explicit Dutch P2000 text."""
from __future__ import annotations

import re
from typing import Any

_FIRE_PATTERNS = (
    ("very_large_fire", 4, re.compile(r"\b(?:zeer\s+grote\s+br|zeer\s+grote\s+brand)\b", re.IGNORECASE)),
    ("large_fire", 3, re.compile(r"\b(?:grote\s+br|grote\s+brand)\b", re.IGNORECASE)),
    ("medium_fire", 2, re.compile(r"\b(?:middel\s+br|middelbrand|middel\s+brand)\b", re.IGNORECASE)),
)
_GRIP_RE = re.compile(r"\bgrip\s*[-:]?\s*([1-4])\b", re.IGNORECASE)


def build_escalation_summary(
    events: list[Any],
) -> dict[str, Any]:
    """Return explicit upward fire-scale and GRIP milestones in event order."""
    timeline: list[dict[str, Any]] = []
    highest_fire_rank = 0
    highest_fire_scale: str | None = None
    highest_grip_rank = 0
    highest_grip: str | None = None

    for event in events:
        message = str(getattr(event, "message", "") or "")
        human_message = str(getattr(event, "human_message", "") or "")
        text = " ".join(part for part in (message, human_message) if part).strip()
        if not text:
            continue

        event_time = getattr(event, "event_time", None)
        external_id = getattr(event, "external_id", None)
        source = getattr(event, "source", None) or "p2000"

        fire_level = None
        fire_rank = 0
        for level, rank, pattern in _FIRE_PATTERNS:
            if pattern.search(text):
                fire_level = level
                fire_rank = rank
                break

        if fire_level is not None and fire_rank > highest_fire_rank:
            highest_fire_rank = fire_rank
            highest_fire_scale = fire_level
            timeline.append(
                {
                    "event_time": event_time,
                    "type": "fire_scale",
                    "level": fire_level,
                    "source": source,
                    "external_id": external_id,
                }
            )

        grip_match = _GRIP_RE.search(text)
        if grip_match:
            grip_rank = int(grip_match.group(1))
            if grip_rank > highest_grip_rank:
                highest_grip_rank = grip_rank
                highest_grip = f"grip_{grip_rank}"
                timeline.append(
                    {
                        "event_time": event_time,
                        "type": "grip",
                        "level": highest_grip,
                        "source": source,
                        "external_id": external_id,
                    }
                )

    type_order = {"fire_scale": 0, "grip": 1}
    timeline.sort(
        key=lambda item: (
            str(item.get("event_time") or ""),
            type_order.get(str(item.get("type") or ""), 99),
        )
    )
    return {
        "escalation_detected": bool(timeline),
        "escalation_timeline": timeline,
        "highest_fire_scale": highest_fire_scale,
        "highest_grip": highest_grip,
    }
