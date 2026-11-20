"""Silent replacement discrepancy notifications via HA notify entities.

Never uses TTS, media players, sirens, or critical push priority. The configured
notify entities (Telegram, mobile app, or both) are controlled by the user.
"""
from __future__ import annotations

import re
from typing import Any

_NOTIFY_ENTITY = re.compile(r"^notify\.[a-z0-9_]+$")


def valid_notify_entity(value: Any) -> bool:
    return isinstance(value, str) and bool(_NOTIFY_ENTITY.fullmatch(value.strip()))


def notify_entities(options: dict) -> list[str]:
    """Select explicitly configured entity targets; no implicit defaults."""
    if not options.get("replacement_alerts_enabled", False):
        return []
    channel = options.get("replacement_alert_channel", "push")
    if channel not in {"telegram", "push", "both"}:
        return []
    targets = []
    for name, key in (
        ("telegram", "replacement_alert_telegram_entity"),
        ("push", "replacement_alert_push_entity"),
    ):
        if channel in (name, "both"):
            target = str(options.get(key) or "").strip()
            if valid_notify_entity(target) and target not in targets:
                targets.append(target)
    return targets


def discrepancy_message(decision: dict, *, function: str | None = None) -> dict:
    """Never include credentials, personal data, or raw incident content."""
    station = str(decision.get("station_name") or decision.get("station_id") or "?")[:80]
    original = str(decision.get("original_vehicle_number") or "?")
    replacement = str(decision.get("replacement_vehicle_number") or "?")
    observed = str(decision.get("observed_vehicle_number") or "?")
    incident = str(decision.get("incident_id") or "?")
    function_text = str(function or "onbekend")[:80]
    return {
        "title": f"Voertuigafwijking - {station}",
        "message": (
            f"BrandweerRooster: {observed}; oorspronkelijke eenheid: {original}; "
            f"ingestelde vervanger: {replacement}; functie: {function_text}; "
            f"incident: {incident}. Vervanging NIET automatisch gewijzigd."
        ),
    }


async def async_send_discrepancy(hass, options: dict, decision: dict, *, function: str | None = None) -> int:
    """Send noncritical notifications to explicit HA notify entities only."""
    targets = notify_entities(options)
    if not targets:
        return 0
    payload = discrepancy_message(decision, function=function)
    delivered = 0
    for target in targets:
        try:
            await hass.services.async_call(
                "notify", "send_message",
                payload,
                target={"entity_id": target},
                blocking=False,
            )
            delivered += 1
        except Exception:
            # Avoid logging the notification contents, credentials or HA entity names.
            # The caller may surface a generic failed-delivery diagnostic.
            continue
    return delivered
