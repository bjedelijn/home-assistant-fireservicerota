"""Structured escalation milestones derived from explicit Dutch P2000 text."""
from __future__ import annotations

import re
from typing import Any

# Keep incident disciplines independent. A "Middel HV" is not a medium fire,
# and IBGS/OGS/IGS scaling is likewise separate from fire and rescue scaling.
# Patterns are deliberately explicit: generic capcode descriptions such as
# "Infocode Middel incident" must never imply a specific incident discipline.
_SCALE_PATTERNS = {
    "fire_scale": (
        (
            "very_large_fire",
            4,
            re.compile(
                r"\bzeer\s+(?:groot|grote)\s+(?:br|brand)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "large_fire",
            3,
            re.compile(r"\b(?:groot|grote)\s+(?:br|brand)\b", re.IGNORECASE),
        ),
        (
            "medium_fire",
            2,
            re.compile(
                r"\b(?:middel\s+(?:br|brand)|middelbrand)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "small_fire",
            1,
            re.compile(r"\b(?:klein|kleine)\s+(?:br|brand)\b", re.IGNORECASE),
        ),
    ),
    "hv_scale": (
        (
            "very_large_hv",
            4,
            re.compile(
                r"\bzeer\s+(?:groot|grote)\s+(?:hv|hulpverlening)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "large_hv",
            3,
            re.compile(
                r"\b(?:groot|grote)\s+(?:hv|hulpverlening)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "medium_hv",
            2,
            re.compile(
                r"\bmiddel\s+(?:hv|hulpverlening)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "small_hv",
            1,
            re.compile(
                r"\b(?:klein|kleine)\s+(?:hv|hulpverlening)\b",
                re.IGNORECASE,
            ),
        ),
    ),
    "ibgs_scale": (
        (
            "very_large_ibgs",
            4,
            re.compile(
                r"\bzeer\s+(?:groot|grote)\s+(?:ibgs|ogs|igs)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "large_ibgs",
            3,
            re.compile(
                r"\b(?:groot|grote)\s+(?:ibgs|ogs|igs)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "medium_ibgs",
            2,
            re.compile(
                r"\bmiddel\s+(?:ibgs|ogs|igs)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "small_ibgs",
            1,
            re.compile(
                r"\b(?:klein|kleine)\s+(?:ibgs|ogs|igs)\b",
                re.IGNORECASE,
            ),
        ),
    ),
}

_HIGHEST_KEYS = {
    "fire_scale": "highest_fire_scale",
    "hv_scale": "highest_hv_scale",
    "ibgs_scale": "highest_ibgs_scale",
}

_GRIP_RE = re.compile(r"\bgrip\s*[-:]?\s*([1-4])\b", re.IGNORECASE)


def _match_scale(
    text: str, patterns: tuple[tuple[str, int, re.Pattern[str]], ...]
) -> tuple[str | None, int]:
    """Return the highest explicit scale found for one incident discipline."""
    for level, rank, pattern in patterns:
        if pattern.search(text):
            return level, rank
    return None, 0


def build_escalation_summary(
    events: list[Any],
) -> dict[str, Any]:
    """Return explicit BR, HV, IBGS and GRIP milestones in event order."""
    timeline: list[dict[str, Any]] = []
    highest_ranks = {scale_type: 0 for scale_type in _SCALE_PATTERNS}
    highest_levels: dict[str, str | None] = {
        scale_type: None for scale_type in _SCALE_PATTERNS
    }
    highest_grip_rank = 0
    highest_grip: str | None = None
    escalation_detected = False

    for event in events:
        message = str(getattr(event, "message", "") or "")
        human_message = str(getattr(event, "human_message", "") or "")
        text = " ".join(part for part in (message, human_message) if part).strip()
        if not text:
            continue

        event_time = getattr(event, "event_time", None)
        external_id = getattr(event, "external_id", None)
        source = getattr(event, "source", None) or "p2000"

        for scale_type, patterns in _SCALE_PATTERNS.items():
            level, rank = _match_scale(text, patterns)
            if level is None or rank <= highest_ranks[scale_type]:
                continue

            highest_ranks[scale_type] = rank
            highest_levels[scale_type] = level
            timeline.append(
                {
                    "event_time": event_time,
                    "type": scale_type,
                    "level": level,
                    "source": source,
                    "external_id": external_id,
                }
            )
            # "Small" is an explicit classification but not an escalation.
            if rank >= 2:
                escalation_detected = True

        grip_match = _GRIP_RE.search(text)
        if grip_match:
            grip_rank = int(grip_match.group(1))
            if grip_rank > highest_grip_rank:
                highest_grip_rank = grip_rank
                highest_grip = f"grip_{grip_rank}"
                escalation_detected = True
                timeline.append(
                    {
                        "event_time": event_time,
                        "type": "grip",
                        "level": highest_grip,
                        "source": source,
                        "external_id": external_id,
                    }
                )

    type_order = {
        "fire_scale": 0,
        "hv_scale": 1,
        "ibgs_scale": 2,
        "grip": 3,
    }
    timeline.sort(
        key=lambda item: (
            str(item.get("event_time") or ""),
            type_order.get(str(item.get("type") or ""), 99),
        )
    )

    result = {
        "escalation_detected": escalation_detected,
        "escalation_timeline": timeline,
        "highest_grip": highest_grip,
    }
    for scale_type, highest_key in _HIGHEST_KEYS.items():
        result[highest_key] = highest_levels[scale_type]
    return result
