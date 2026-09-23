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
    CONF_P2000_ENABLED,
    CONF_P2000_SCAN_INTERVAL,
    CONF_P2000_SOURCE,
    DATA_CLIENT,
    DATA_COORDINATOR,
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

    entities = [
        IncidentsSensor(client, incident_store),
        ActiveIncidentsSensor(client, coordinator, incident_store),
        IncidentHistorySensor(client, incident_store),
        PagerSensor(client, coordinator),
    ]
    if client.mobile_devices_supported:
        entities.append(MobileDevicesSensor(client, coordinator))

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
        entities.extend([
            P2000StatusSensor(client, p2000_manager),
            P2000MatchesSensor(client, p2000_manager),
        ])
        await p2000_manager.async_start()

    async_add_entities(entities)


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
            "own_stations",
            "own_affiliations",
            "own_incident_affiliations",
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
                "operational_status",
                "operational_ended_at",
                "operational_ended_at_source",
                "api_closed",
                "manual_closed",
                "manual_closed_at",
                "incident_group",
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
            return

        data_with_changes = self._with_task_changes(data)
        self._state = data_with_changes["body"]
        self._state_attributes = self._client.enrich_incident_data(data_with_changes)
        incident_id = data_with_changes.get("id")
        if incident_id is not None:
            self._client.incident_id = incident_id

        self._incident_store.upsert(
            self._state_attributes,
            source="websocket",
        )
        self.async_write_ha_state()

        if incident_id is not None:
            self.hass.async_create_task(self._async_enrich_from_rest(incident_id))

    async def _async_enrich_from_rest(self, incident_id) -> None:
        """Fetch full incident and merge richer response/lifecycle data."""
        incident = await self._client.async_get_incident(incident_id)
        if not isinstance(incident, dict):
            return

        existing = self._incident_store.get_raw(incident_id) or {"id": incident_id}
        store_merged = dict(existing)
        store_merged.update(incident)
        for key in ("trigger", "previous_task_ids", "new_task_ids"):
            if key not in incident and key in existing:
                store_merged[key] = existing[key]
        store_enriched = self._client.enrich_incident_data(store_merged)
        self._incident_store.upsert(store_enriched, source="rest")
        self._incident_store.mark_rest_refreshed(incident_id)

        # A REST request for an older concurrent incident may finish after a
        # newer one became the central sensor. Enrich the store regardless,
        # but only replace sensor.incidents when it still represents this id.
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


class ActiveIncidentsSensor(RestoreEntity, SensorEntity):
    """Representation of all currently active incidents seen by Extended."""

    _attr_has_entity_name = True
    _attr_translation_key = "active_incidents"
    _attr_should_poll = False
    _attr_icon = "mdi:fire-alert"

    def __init__(self, client, coordinator, incident_store: IncidentStore):
        """Initialize."""
        self._client = client
        self._coordinator = coordinator
        self._incident_store = incident_store
        self._attr_unique_id = f"{self._client.unique_id}_ActiveIncidents"

    @property
    def native_value(self) -> int:
        """Return the number of active incidents."""
        return len(self._incident_store.active_incidents)

    @property
    def extra_state_attributes(self) -> dict:
        """Return active incident snapshots for dashboards."""
        return {
            "latest_incident_id": self._incident_store.latest_incident_id,
            "incidents": self._incident_store.active_incidents,
            "refresh_seconds": ACTIVE_INCIDENT_REFRESH_SECONDS,
            "own_stations": self._client.own_stations,
            "own_affiliations": [dict(item) for item in self._client.own_affiliations],
        }

    async def async_added_to_hass(self) -> None:
        """Restore snapshots and register live/coordinator updates."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            incidents = state.attributes.get("incidents")
            if isinstance(incidents, list):
                self._incident_store.restore(incidents, active=True)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._incident_store.signal,
                self._handle_store_update,
            )
        )
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )
        if self._incident_store.active_incidents:
            self.hass.async_create_task(self._async_refresh_active())

    @callback
    def _handle_store_update(self) -> None:
        """Write state when the shared incident store changes."""
        self.async_write_ha_state()

    async def _async_refresh_active(self) -> None:
        """Refresh active incidents from the REST API."""
        await self._incident_store.async_refresh_active()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Tick live durations and periodically refresh active REST records."""
        self.async_write_ha_state()
        self.hass.async_create_task(self._async_refresh_active())


class IncidentHistorySensor(RestoreEntity, SensorEntity):
    """Representation of unique closed incident history."""

    _attr_has_entity_name = True
    _attr_translation_key = "incident_history"
    _attr_should_poll = False
    _attr_icon = "mdi:history"

    def __init__(self, client, incident_store: IncidentStore):
        """Initialize."""
        self._client = client
        self._incident_store = incident_store
        self._attr_unique_id = f"{self._client.unique_id}_IncidentHistory"

    @property
    def native_value(self) -> int:
        """Return the number of retained closed incidents."""
        return len(self._incident_store.history)

    @property
    def extra_state_attributes(self) -> dict:
        """Return unique closed incident snapshots."""
        return {
            "incidents": self._incident_store.history,
            "history_limit": HISTORY_LIMIT,
            "own_stations": self._client.own_stations,
            "own_affiliations": [dict(item) for item in self._client.own_affiliations],
        }

    async def async_added_to_hass(self) -> None:
        """Restore history and register store updates."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            incidents = state.attributes.get("incidents")
            if isinstance(incidents, list):
                self._incident_store.restore(incidents, active=False)

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._incident_store.signal,
                self._handle_store_update,
            )
        )

    @callback
    def _handle_store_update(self) -> None:
        """Write state when the shared incident store changes."""
        self.async_write_ha_state()


class P2000StatusSensor(SensorEntity):
    """Diagnostic status for the optional Dutch P2000 enrichment module."""

    _attr_has_entity_name = True
    _attr_translation_key = "p2000_status"
    _attr_should_poll = False
    _attr_icon = "mdi:radio-tower"

    def __init__(self, client, manager: P2000EnrichmentManager):
        """Initialize."""
        self._client = client
        self._manager = manager
        self._attr_unique_id = f"{self._client.unique_id}_P2000Status"

    @property
    def native_value(self) -> int:
        """Return the number of unique P2000 events in the rolling buffer."""
        return self._manager.buffer_size

    @property
    def extra_state_attributes(self) -> dict:
        """Return P2000 reception and ring-buffer diagnostics."""
        return self._manager.status

    async def async_added_to_hass(self) -> None:
        """Register for P2000 poll/buffer updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._manager.async_add_listener(self.async_write_ha_state)
        )


class P2000MatchesSensor(RestoreEntity, SensorEntity):
    """Persistent confirmed P2000 matches beyond the rolling ring buffer."""

    _attr_has_entity_name = True
    _attr_translation_key = "p2000_matches"
    _attr_should_poll = False
    _attr_icon = "mdi:link-variant"

    def __init__(self, client, manager: P2000EnrichmentManager):
        self._client = client
        self._manager = manager
        self._attr_unique_id = f"{self._client.unique_id}_P2000Matches"

    @property
    def native_value(self) -> int:
        return len(self._manager.persistent_matches)

    @property
    def extra_state_attributes(self) -> dict:
        return {"matches": self._manager.persistent_matches, "match_limit": 25}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            matches = state.attributes.get("matches")
            if isinstance(matches, list):
                self._manager.restore_matches(matches)
        self.async_on_remove(self._manager.async_add_listener(self.async_write_ha_state))


class MobileDevicesSensor(SensorEntity):
    """Privacy-filtered mobile app/device diagnostics for BrandweerRooster."""

    _attr_has_entity_name = True
    _attr_translation_key = "mobile_devices"
    _attr_should_poll = False

    def __init__(self, client, coordinator):
        """Initialize."""
        self._client = client
        self._coordinator = coordinator
        self._attr_unique_id = f"{self._client.unique_id}_MobileDevices"

    @property
    def icon(self) -> str:
        """Return mobile communication icon."""
        return "mdi:cellphone-wireless"

    @property
    def available(self) -> bool:
        """Return whether the mobile-device endpoint has been read successfully."""
        return bool(
            self._client.mobile_devices_supported
            and self._client.mobile_devices_available
        )

    @property
    def native_value(self) -> int | None:
        """Return the number of registered mobile devices."""
        if not self.available:
            return None
        return len(self._client.mobile_devices)

    @property
    def extra_state_attributes(self) -> dict:
        """Return privacy-filtered mobile device fields only."""
        if not self.available:
            return {}

        devices = [dict(device) for device in self._client.mobile_devices]
        attr = {
            "device_count": len(devices),
            "enabled_device_count": sum(
                1 for device in devices if device.get("enabled") is True
            ),
            "alert_notifications_enabled_count": sum(
                1
                for device in devices
                if device.get("alert_notifications_enabled") is True
            ),
            "mobile_devices": devices,
        }
        if len(devices) == 1:
            attr.update(devices[0])
        return attr

    async def async_added_to_hass(self) -> None:
        """Register coordinator updates."""
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )


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