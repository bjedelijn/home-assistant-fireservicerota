"""Conservative Dutch P2000 station and unit hints from capcode descriptions."""
from __future__ import annotations

import re
from typing import Any

_CONFIDENCE_SCORE = {"medium": 2, "high": 3}
_UNIT_TOKEN_RE = re.compile(r"(?<!\\d)(\\d{3,6})(?!\\d)")
_NON_FIRE_RE = re.compile(
    r"\\b(?:ambulance|ambu|traumaheli|lifeliner|mmt|politie|knrm)\\b",
    re.IGNORECASE,
)
_NON_STATION_RE = re.compile(
    r"\\b(?:monitor(?:code)?|h?ovd|rovd\\w*|woordvoerder|persinformatie|"
    r"infocode|calamiteiten\\s*co[oö]rdinator|meldkamer|regionaal|regio|"
    r"veiligheidsregio)\\b",
    re.IGNORECASE,
)
_EXPLICIT_STATION_ROLE_RE = re.compile(
    r"\\b(?:kazerne(?:alarm|commandant|techniek)?|brandweerpost|blusploeg|"
    r"bezetting|springbemanning|lichtkrant|postcommandant|ploeg)\\b",
    re.IGNORECASE,
)
_APPLIANCE_ROLE_RE = re.compile(
    r"\\b(?:ts|tst|tw|wt|wts|rv|hw|al|hv|wo|da|db|pm|ha|sb|ab|sl)\\b",
    re.IGNORECASE,
)
_PREFIX_STATION_RE = re.compile(
    r"^(?:brandweerpost|kazerne(?:alarm)?)\\s*[:\\-]?\\s*(?P<station>.+)$",
    re.IGNORECASE,
)
_SUFFIX_STATION_RE = re.compile(
    r"^(?P<station>.+?)\\s+(?:kazernealarm|blusploeg|springbemanning|"
    r"postcommandant|lichtkrant)$",
    re.IGNORECASE,
)


def _description(item: dict[str, Any]) -> str:
    """Return the first supported human capcode description."""
    for key in ("omschrijving", "description", "name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _clean_station(value: str) -> str | None:
    """Normalize a possible station name and reject obvious region/function labels."""
    cleaned = " ".join(str(value or "").strip(" -/").split())
    cleaned = re.sub(r"^brandweer\\s+", "", cleaned, flags=re.IGNORECASE).strip()
    if not cleaned or cleaned.casefold() in {"onbekend", "unknown", "nvt", "n/a"}:
        return None
    if _NON_STATION_RE.search(cleaned) or _NON_FIRE_RE.search(cleaned):
        return None
    if not any(char.isalpha() for char in cleaned):
        return None
    return cleaned


def station_hint_from_capcode(item: dict[str, Any]) -> dict[str, Any] | None:
    """Return a conservative station candidate from one capcode description."""
    description = _description(item)
    if not description or _NON_FIRE_RE.search(description):
        return None

    capcode = str(item.get("capcode") or "").strip() or None

    prefix = _PREFIX_STATION_RE.match(description)
    if prefix:
        station = _clean_station(prefix.group("station"))
        if station:
            return {
                "name": station,
                "source": "p2000_capcode",
                "confidence": "high",
                "reason": "named_station_role",
                "capcode": capcode,
                "description": description,
                "unit_tokens": _UNIT_TOKEN_RE.findall(description),
            }

    suffix = _SUFFIX_STATION_RE.match(description)
    if suffix:
        station = _clean_station(suffix.group("station"))
        if station:
            return {
                "name": station,
                "source": "p2000_capcode",
                "confidence": "high",
                "reason": "named_station_role",
                "capcode": capcode,
                "description": description,
                "unit_tokens": _UNIT_TOKEN_RE.findall(description),
            }

    parts = re.split(r"\\s+/\\s+", description, maxsplit=1)
    if len(parts) != 2:
        return None

    role, raw_station = (part.strip() for part in parts)
    if _NON_STATION_RE.search(role):
        return None

    station = _clean_station(raw_station)
    if station is None:
        return None

    if _EXPLICIT_STATION_ROLE_RE.search(role):
        confidence = "high"
        reason = "station_role"
    elif _APPLIANCE_ROLE_RE.search(role):
        confidence = "medium"
        reason = "appliance_role"
    else:
        return None

    return {
        "name": station,
        "source": "p2000_capcode",
        "confidence": confidence,
        "reason": reason,
        "capcode": capcode,
        "description": description,
        "unit_tokens": _UNIT_TOKEN_RE.findall(role),
    }


def build_station_and_unit_hints(
    events: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build station hints and safe per-unit station fallbacks for P2000 events."""
    station_map: dict[str, dict[str, Any]] = {}
    unit_candidates: dict[str, dict[str, dict[str, Any]]] = {
        str(unit): {}
        for event in events
        for unit in (getattr(event, "units", None) or [])
    }

    for event in events:
        event_hints: list[dict[str, Any]] = []
        for item in getattr(event, "capcodes", None) or []:
            if not isinstance(item, dict):
                continue
            hint = station_hint_from_capcode(item)
            if hint is None:
                continue
            event_hints.append(hint)

            key = hint["name"].casefold()
            score = _CONFIDENCE_SCORE.get(hint["confidence"], 0)
            current = station_map.get(key)
            if current is None:
                station_map[key] = {
                    "name": hint["name"],
                    "source": "p2000_capcode",
                    "confidence": hint["confidence"],
                    "_score": score,
                    "capcodes": {hint["capcode"]} if hint.get("capcode") else set(),
                    "descriptions": {hint["description"]},
                    "reasons": {hint["reason"]},
                }
            else:
                if score > current["_score"]:
                    current["_score"] = score
                    current["confidence"] = hint["confidence"]
                if hint.get("capcode"):
                    current["capcodes"].add(hint["capcode"])
                current["descriptions"].add(hint["description"])
                current["reasons"].add(hint["reason"])

        distinct_event_stations = {
            hint["name"].casefold(): hint["name"] for hint in event_hints
        }

        for raw_unit in getattr(event, "units", None) or []:
            unit = str(raw_unit)
            candidates = unit_candidates.setdefault(unit, {})
            explicit = [
                hint
                for hint in event_hints
                if any(
                    len(token) >= 3 and unit.endswith(token)
                    for token in (hint.get("unit_tokens") or [])
                )
            ]

            if explicit:
                chosen = explicit
                inferred_confidence = "high"
                inferred_reason = "unit_suffix_match"
            elif len(distinct_event_stations) == 1 and event_hints:
                only_key = next(iter(distinct_event_stations))
                chosen = [
                    next(
                        hint
                        for hint in event_hints
                        if hint["name"].casefold() == only_key
                    )
                ]
                inferred_confidence = "medium"
                inferred_reason = "unique_event_station_hint"
            else:
                chosen = event_hints
                inferred_confidence = None
                inferred_reason = "ambiguous_event_station_hints"

            for hint in chosen:
                key = hint["name"].casefold()
                score = _CONFIDENCE_SCORE.get(inferred_confidence or "", 0)
                candidate = candidates.setdefault(
                    key,
                    {
                        "name": hint["name"],
                        "source": "p2000_capcode",
                        "confidence": inferred_confidence,
                        "reason": inferred_reason,
                        "_score": score,
                        "capcodes": set(),
                        "descriptions": set(),
                    },
                )
                if score > candidate["_score"]:
                    candidate["_score"] = score
                    candidate["confidence"] = inferred_confidence
                    candidate["reason"] = inferred_reason
                if hint.get("capcode"):
                    candidate["capcodes"].add(hint["capcode"])
                candidate["descriptions"].add(hint["description"])

    station_hints = [
        {
            "name": item["name"],
            "source": item["source"],
            "confidence": item["confidence"],
            "capcodes": sorted(item["capcodes"]),
            "descriptions": sorted(item["descriptions"])[:10],
            "reasons": sorted(item["reasons"]),
        }
        for item in station_map.values()
    ]
    station_hints.sort(key=lambda item: item["name"].casefold())

    unit_details = []
    for unit in sorted(unit_candidates):
        candidates = unit_candidates[unit]
        candidate_list = []
        for item in candidates.values():
            candidate_list.append(
                {
                    "name": item["name"],
                    "source": item["source"],
                    "confidence": item["confidence"],
                    "reason": item["reason"],
                    "capcodes": sorted(item["capcodes"]),
                    "descriptions": sorted(item["descriptions"])[:10],
                    "_score": item["_score"],
                }
            )
        candidate_list.sort(
            key=lambda item: (-item["_score"], item["name"].casefold())
        )

        station_name = None
        station_source = None
        station_confidence = None
        station_reason = None
        if candidate_list:
            best_score = candidate_list[0]["_score"]
            best = [item for item in candidate_list if item["_score"] == best_score]
            if best_score > 0 and len(best) == 1:
                station_name = best[0]["name"]
                station_source = best[0]["source"]
                station_confidence = best[0]["confidence"]
                station_reason = best[0]["reason"]

        clean_candidates = [
            {key: value for key, value in item.items() if key != "_score"}
            for item in candidate_list
        ]
        unit_details.append(
            {
                "unit": unit,
                "station_name": station_name,
                "station_source": station_source,
                "station_confidence": station_confidence,
                "station_reason": station_reason,
                "station_candidates": clean_candidates,
            }
        )

    return station_hints[:25], unit_details
