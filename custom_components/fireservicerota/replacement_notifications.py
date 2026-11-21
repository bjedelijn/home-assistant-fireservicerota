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


def notify_targets(options: dict) -> list[tuple[str, str]]:
    """Return explicit, validated destinations (entity or native Telegram bot).

    The native Telegram integration uses telegram_bot.send_message rather than
    a notify entity. Do not log the config-entry identifier.
    """
    if not options.get("replacement_alerts_enabled", False):
        return []
    channel = options.get("replacement_alert_channel", "push")
    if channel not in {"telegram", "push", "both"}:
        return []
    targets: list[tuple[str, str]] = []
    if channel in {"telegram", "both"}:
        entity = str(options.get("replacement_alert_telegram_entity") or "").strip()
        bot_entry = str(options.get("replacement_alert_telegram_bot_entry_id") or "").strip()
        if valid_notify_entity(entity):
            targets.append(("notify", entity))
        elif re.fullmatch(r"[A-Za-z0-9_-]{16,64}", bot_entry):
            targets.append(("telegram_bot", bot_entry))
    if channel in {"push", "both"}:
        entity = str(options.get("replacement_alert_push_entity") or "").strip()
        if valid_notify_entity(entity) and ("notify", entity) not in targets:
            targets.append(("notify", entity))
    return targets


def notify_entities(options: dict) -> list[str]:
    """Backward-compatible helper for notify-entity-only destinations."""
    return [value for kind, value in notify_targets(options) if kind == "notify"]


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
    targets = notify_targets(options)
    if not targets:
        return 0
    payload = discrepancy_message(decision, function=function)
    delivered = 0
    for kind, target in targets:
        try:
            if kind == "telegram_bot":
                await hass.services.async_call(
                    "telegram_bot", "send_message",
                    {"config_entry_id": target, "message": payload["title"] + chr(10) + payload["message"], "parse_mode": "plain_text"},
                    blocking=False,
                )
            else:
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
