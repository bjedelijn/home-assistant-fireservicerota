"""Sensor platform for FireServiceRota integration."""
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN as FIRESERVICEROTA_DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up FireServiceRota sensors based on a config entry."""
    client = hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][DATA_COORDINATOR]

    async_add_entities(
        [
            IncidentsSensor(client),
            PagerSensor(client, coordinator),
        ]
    )


class IncidentsSensor(RestoreEntity, SensorEntity):
    """Representation of the latest FireServiceRota incident."""

    _attr_has_entity_name = True
    _attr_translation_key = "incidents"
    _attr_should_poll = False

    def __init__(self, client):
        """Initialize."""
        self._client = client
        self._entry_id = self._client.entry_id
        self._attr_unique_id = f"{self._client.unique_id}_Incidents"
        self._state = None
        self._state_attributes = {}
        self._task_ids_by_incident = {}

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        prio = self._state_attributes.get("prio")
        if isinstance(prio, str) and prio.startswith("a"):
            return "mdi:ambulance"
        return "mdi:fire-truck"

    @property
    def native_value(self) -> str | None:
        """Return the sensor value."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict:
        """Return available incident attributes."""
        data = self._state_attributes
        if not data:
            return {}

        attr = {}
        for value in (
            "id",
            "trigger",
            "created_at",
            "message_to_speech_url",
            "prio",
            "type",
            "responder_mode",
            "can_respond_until",
            "task_ids",
            "previous_task_ids",
            "new_task_ids",
            "groups",
            "resolved_tasks",
            "resolved_stations",
            "responses_by_station",
        ):
            if value in data and data[value] is not None:
                attr[value] = data[value]

        address = data.get("address")
        if isinstance(address, dict):
            for address_value in (
                "latitude",
                "longitude",
                "address_type",
                "formatted_address",
            ):
                if address_value in address:
                    attr[address_value] = address[address_value]

        return attr

    async def async_added_to_hass(self) -> None:
        """Run when about to be added to hass."""
        await super().async_added_to_hass()

        state = await self.async_get_last_state()
        if state:
            self._state = state.state
            self._state_attributes = dict(state.attributes)
            incident_id = self._state_attributes.get("id")
            if incident_id is not None:
                self._client.incident_id = incident_id
                self._task_ids_by_incident[incident_id] = set(
                    self._state_attributes.get("task_ids") or []
                )
                # A restored incident only contains attributes saved by the
                # previous entity state. Re-fetch the incident so Extended
                # attributes such as resolved_tasks, resolved_stations and
                # responses_by_station are available immediately after a
                # Home Assistant restart instead of waiting for the next
                # WebSocket incident update.
                self.hass.async_create_task(self._async_enrich_from_rest(incident_id))
            _LOGGER.debug("Restored entity 'Incidents' to: %s", self._state)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{FIRESERVICEROTA_DOMAIN}_{self._entry_id}_update",
                self.client_update,
            )
        )

    def _with_task_changes(self, data: dict) -> dict:
        """Add task-change metadata for the current incident update."""
        enriched = dict(data)
        incident_id = data.get("id")
        current_task_ids = set(data.get("task_ids") or [])

        if incident_id is None:
            enriched["previous_task_ids"] = []
            enriched["new_task_ids"] = sorted(current_task_ids)
            return enriched

        previous_task_ids = self._task_ids_by_incident.get(incident_id, set())
        trigger = data.get("trigger")

        if trigger == "new" or incident_id not in self._task_ids_by_incident:
            previous_task_ids = set()
            new_task_ids = current_task_ids
        else:
            new_task_ids = current_task_ids - previous_task_ids

        enriched["previous_task_ids"] = sorted(previous_task_ids)
        enriched["new_task_ids"] = sorted(new_task_ids)
        self._task_ids_by_incident = {incident_id: current_task_ids}
        return enriched

    @callback
    def client_update(self) -> None:
        """Handle updated incident data from the websocket client."""
        data = self._client.websocket.incident_data
        if not data or "body" not in data:
            return

        data_with_changes = self._with_task_changes(data)
        self._state = data_with_changes["body"]
        self._state_attributes = self._client.enrich_incident_data(data_with_changes)
        incident_id = data_with_changes.get("id")
        if incident_id is not None:
            self._client.incident_id = incident_id

        self.async_write_ha_state()

        if incident_id is not None:
            self.hass.async_create_task(self._async_enrich_from_rest(incident_id))

    async def _async_enrich_from_rest(self, incident_id) -> None:
        """Fetch full incident and merge richer per-station response data."""
        incident = await self._client.async_get_incident(incident_id)
        if not isinstance(incident, dict):
            return

        if self._client.incident_id != incident_id:
            return

        merged = dict(self._state_attributes)
        merged.update(incident)

        if "trigger" not in incident and "trigger" in self._state_attributes:
            merged["trigger"] = self._state_attributes["trigger"]

        for key in ("previous_task_ids", "new_task_ids"):
            if key not in incident and key in self._state_attributes:
                merged[key] = self._state_attributes[key]

        self._state_attributes = self._client.enrich_incident_data(merged)
        self._state = self._state_attributes.get("body", self._state)
        self.async_write_ha_state()


class PagerSensor(RestoreEntity, SensorEntity):
    """Representation of pager status for the authenticated user."""

    _attr_has_entity_name = True
    _attr_translation_key = "pager"
    _attr_should_poll = False

    def __init__(self, client, coordinator):
        """Initialize."""
        self._client = client
        self._coordinator = coordinator
        self._entry_id = self._client.entry_id
        self._attr_unique_id = f"{self._client.unique_id}_Pager"

    @property
    def icon(self) -> str:
        """Return pager icon."""
        return "mdi:pager"

    @property
    def available(self) -> bool:
        """Return whether at least one pager is available from the API."""
        return bool(self._client.pagers)

    @property
    def native_value(self):
        """Return a useful value while keeping multiple pagers supported."""
        pagers = self._client.pagers
        if not pagers:
            return None
        if len(pagers) == 1:
            return pagers[0].get("state", "unknown")
        return len(pagers)

    def _pager_attributes(self, pager: dict) -> dict:
        """Return selected, automation-friendly pager fields."""
        return {
            key: pager.get(key)
            for key in (
                "id",
                "user_id",
                "serial_number",
                "firmware_version",
                "type",
                "battery_level",
                "last_seen_at",
                "state",
                "signal_strength",
                "signal_strength_status",
                "paging_signal_strength",
                "paging_signal_strength_status",
                "mobile_operator",
            )
            if pager.get(key) is not None
        }

    @property
    def extra_state_attributes(self) -> dict:
        """Return pager details and latest locally sent message."""
        pagers = self._client.pagers
        if not pagers:
            return {}

        if len(pagers) == 1:
            attr = self._pager_attributes(pagers[0])
        else:
            attr = {
                "pager_count": len(pagers),
                "pagers": [self._pager_attributes(pager) for pager in pagers],
            }

        if isinstance(self._client.last_pager_message, dict):
            message = self._client.last_pager_message
            attr["last_sent_message"] = {
                key: message.get(key)
                for key in (
                    "id",
                    "body",
                    "pager_id",
                    "acknowledgment_state",
                    "address",
                    "subaddress",
                    "addresses",
                )
                if message.get(key) is not None
            }

        return attr

    async def async_added_to_hass(self) -> None:
        """Register coordinator and pager-message updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{FIRESERVICEROTA_DOMAIN}_{self._entry_id}_pager_update",
                self.async_write_ha_state,
            )
        )
