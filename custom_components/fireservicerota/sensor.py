"""Sensor platform for FireServiceRota integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DATA_CLIENT,
    DATA_COORDINATOR,
    CONF_P2000_ENABLED,
    CONF_P2000_SCAN_INTERVAL,
    CONF_P2000_SOURCE,
    DATA_INCIDENT_STORE,
    DATA_P2000_MANAGER,
    DOMAIN as FIRESERVICEROTA_DOMAIN,
    P2000_DEFAULT_SCAN_INTERVAL,
    P2000_SOURCE_ONLINE,
)
from .incident_store import ACTIVE_INCIDENT_REFRESH_SECONDS, HISTORY_LIMIT, IncidentStore
from .enrichment.nl.p2000 import P2000EnrichmentManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up FireServiceRota sensors based on a config entry."""
    client = hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][DATA_COORDINATOR]
    incident_store = IncidentStore(hass, client, entry.entry_id)
    hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][
        DATA_INCIDENT_STORE
    ] = incident_store

    options = {**entry.data, **entry.options}
    if (
        entry.data.get("url") == "www.brandweerrooster.nl"
        and options.get(CONF_P2000_ENABLED, False)
        and options.get(CONF_P2000_SOURCE, P2000_SOURCE_ONLINE)
        == P2000_SOURCE_ONLINE
    ):
        p2000_manager = P2000EnrichmentManager(
            hass,
            incident_store,
            scan_interval=options.get(
                CONF_P2000_SCAN_INTERVAL, P2000_DEFAULT_SCAN_INTERVAL
            ),
        )
        hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][
            DATA_P2000_MANAGER
        ] = p2000_manager
        await p2000_manager.async_start()

    async_add_entities(
        [
            IncidentsSensor(client, incident_store),
            ActiveIncidentsSensor(client, coordinator, incident_store),
            IncidentHistorySensor(client, incident_store),
            PagerSensor(client, coordinator),
        ]
    )


class IncidentsSensor(RestoreEntity, SensorEntity):
    """Representation of the latest FireServiceRota incident."""

    _attr_has_entity_name = True
    _attr_translation_key = "incidents"
    _attr_should_poll = False

    def __init__(self, client, incident_store: IncidentStore):
        """Initialize."""
        self._client = client
        self._incident_store = incident_store
        self._entry_id = self._client.entry_id
        self._attr_unique_id = f"{self._client.unique_id}_Incidents"
        self._state = None
        self._state_attributes = {}
        self._task_ids_by_incident: dict[Any, set] = {}

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
            "first_seen_at",
            "last_seen_at",
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

        incident_id = data.get("id")
        overview = self._incident_store.get_public(incident_id)
        if overview:
            for key in (
                "incident_active",
                "incident_status",
                "incident_ended_at",
                "duration_seconds",
                "lifecycle_known",
                "lifecycle_fields",
                "p2000_enrichment",
            ):
                if key in overview:
                    attr[key] = overview[key]

        return attr

    async def async_added_to_hass(self) -> None:
        """Run when about to be added to hass."""
        await super().async_added_to_hass()

        state = await self.async_get_last_state()
        if state:
            self._state = state.state
            self._state_attributes = dict(state.attributes)

            # A restored entity is historical state, not a newly received
            # WebSocket incident. Never replay the previous raw "new" trigger
            # after an integration reload or Home Assistant restart; otherwise
            # automations that key on trigger == "new" can announce an old call.
            self._state_attributes.pop("trigger", None)

            incident_id = self._state_attributes.get("id")
            if incident_id is not None:
                self._client.incident_id = incident_id
                self._task_ids_by_incident[incident_id] = set(
                    self._state_attributes.get("task_ids") or []
                )
                restored = dict(self._state_attributes)
                restored["body"] = self._state
                self._incident_store.upsert(
                    restored,
                    source="restore",
                    default_active=True,
                )
                # Re-fetch the incident so Extended attributes and lifecycle
                # information are refreshed after a Home Assistant restart.
                self.hass.async_create_task(self._async_enrich_from_rest(incident_id))
            _LOGGER.debug("Restored entity 'Incidents' to: %s", self._state)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{FIRESERVICEROTA_DOMAIN}_{self._entry_id}_update",
                self.client_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._incident_store.signal,
                self._handle_store_update,
            )
        )

    @callback
    def _handle_store_update(self) -> None:
        """Refresh latest-incident attributes when REST/store lifecycle changes."""
        if self._state_attributes.get("id") is not None:
            self.async_write_ha_state()

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
        # Keep task history for multiple concurrent incidents instead of
        # replacing the whole dictionary whenever another incident is updated.
        self._task_ids_by_incident[incident_id] = current_task_ids
        return enriched

    @callback
    def client_update(self) -> None:
        """Handle updated incident data from the websocket client."""
        data = self._client.websocket.incident_data
        if not data or "body" not in data: