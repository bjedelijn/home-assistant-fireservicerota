"""Quiet notifications never use TTS and require configured notify entities."""
import asyncio
from custom_components.fireservicerota.replacement_notifications import (
    async_send_discrepancy,
    discrepancy_message,
    notify_entities,
    valid_notify_entity,
)

DECISION = {
    "station_id": 3853, "station_name": "Gramsbergen",
    "incident_id": 3154000, "original_vehicle_number": "042333",
    "replacement_vehicle_number": "041037",
    "observed_vehicle_number": "041099",
}


def test_no_default_notification_or_unknown_service():
    assert notify_entities({}) == []
    assert notify_entities({"replacement_alerts_enabled": True, "replacement_alert_channel": "push"}) == []
    assert not valid_notify_entity("notify.telegram;media_player.speaker")
    assert not valid_notify_entity("media_player.speaker")
    assert valid_notify_entity("notify.mobile_app_test")


def test_configurable_telegram_and_push_no_duplicate_entities():
    options = {
        "replacement_alerts_enabled": True,
        "replacement_alert_channel": "both",
        "replacement_alert_telegram_entity": "notify.telegram",
        "replacement_alert_push_entity": "notify.mobile_app_telefoon",
    }
    assert notify_entities(options) == ["notify.telegram", "notify.mobile_app_telefoon"]
    assert notify_entities({**options, "replacement_alerts_enabled": False}) == []


class Services:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, *, target=None, blocking=None):
        self.calls.append((domain, service, data, target, blocking))


class Hass:
    def __init__(self):
        self.services = Services()


def test_quiet_dispatch_only_uses_notify_send_message():
    hass = Hass()
    options = {
        "replacement_alerts_enabled": True,
        "replacement_alert_channel": "both",
        "replacement_alert_telegram_entity": "notify.telegram",
        "replacement_alert_push_entity": "notify.mobile_app_telefoon",
    }
    sent = asyncio.run(async_send_discrepancy(hass, options, DECISION, function="TS"))
    assert sent == 2
    assert all(domain == "notify" and service == "send_message" for domain, service, *_ in hass.services.calls)
    assert all("priority" not in data and "tts" not in data for _, _, data, *_ in hass.services.calls)
    assert "041099" in discrepancy_message(DECISION, function="TS")["message"]
