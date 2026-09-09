"""Switch platform for FireServiceRota integration."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.typing import HomeAssistantType

from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN as FIRESERVICEROTA_DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistantType, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up FireServiceRota switches based on a config entry."""
    client = hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities = [ResponseSwitch(coordinator, client, entry)]

    if len(client.membership_index) > 1:
        for membership_id, membership in client.membership_index.items():
            entities.append(
                MembershipResponseSwitch(
                    coordinator,
                    client,
                    entry,
                    membership_id,
                    membership,
                )
            )

    async_add_entities(entities)


class ResponseSwitch(SwitchEntity):
    """Legacy incident response switch.

    The original integration exposes one generic response switch. Extended keeps
    that entity for backwards compatibility. For multi-station users the legacy
    switch remains readable but station-specific switches are used for writes.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "incident_response"

    def __init__(self, coordinator, client, entry):
        """Initialize."""
        self._coordinator = coordinator
        self._client = client
        self._unique_id = f"{entry.unique_id}_Response"
        self._entry_id = entry.entry_id
        self._state = None
        self._state_attributes = {}
        self._state_icon = None

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        if self._state_icon == "acknowledged":
            return "mdi:run-fast"
        if self._state_icon == "rejected":
            return "mdi:account-off-outline"
        return "mdi:forum"

    @property
    def is_on(self) -> bool:
        """Return aggregate response state."""
        return self._state

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this switch."""
        return self._unique_id

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def available(self) -> bool:
        """Only make the legacy write control available when unambiguous."""
        return self._client.on_duty and len(self._client.membership_index) <= 1

    @property
    def extra_state_attributes(self) -> dict:
        """Return legacy and Extended response attributes."""
        attr = dict(self._state_attributes)
        attr["multi_station"] = len(self._client.membership_index) > 1
        attr["writable"] = self.available
        return attr

    async def async_turn_on(self, **kwargs) -> None:
        """Send acknowledged response status."""
        await self.async_set_response(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Send rejected response status."""
        await self.async_set_response(False)

    async def async_set_response(self, value) -> None:
        """Send response status when the target membership is unambiguous."""
        if not self._client.on_duty:
            _LOGGER.debug("Cannot send incident response when not on duty")
            return

        if len(self._client.membership_index) > 1:
            _LOGGER.warning(
                "Not sending legacy incident response because this account has "
                "multiple active station memberships; use a station-specific "
                "response switch instead"
            )
            return

        await self._client.async_set_response(value)
        self.client_update()

    async def async_added_to_hass(self) -> None:
        """Register update callback."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{FIRESERVICEROTA_DOMAIN}_{self._entry_id}_update",
                self.client_update,
            )
        )
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    @callback
    def client_update(self) -> None:
        """Handle updated incident data from the client."""
        self.async_schedule_update_ha_state(True)

    async def async_update(self) -> None:
        """Update response data without collapsing multiple memberships."""
        responses = await self._client.async_response_update()
        if not responses:
            self._state = None
            self._state_attributes = {
                "responses_by_station": [],
                "response_count": 0,
            }
            self._state_icon = None
            return

        acknowledged = [
            response
            for response in responses
            if response.get("status") == "acknowledged"
        ]
        rejected = [
            response for response in responses if response.get("status") == "rejected"
        ]

        self._state = bool(acknowledged)
        if acknowledged:
            self._state_icon = "acknowledged"
        elif rejected:
            self._state_icon = "rejected"
        else:
            self._state_icon = None

        self._state_attributes = {
            "response_count": len(responses),
            "responses_by_station": responses,
        }

        _LOGGER.debug(
            "Updated legacy response switch from %s station response(s)",
            len(responses),
        )


class MembershipResponseSwitch(SwitchEntity):
    """Incident response switch for one BrandweerRooster membership."""

    _attr_has_entity_name = True
    _attr_translation_key = "incident_response_station"

    def __init__(
        self,
        coordinator,
        client,
        entry,
        membership_id: int,
        membership: dict,
    ):
        """Initialize a station-specific incident response switch."""
        self._coordinator = coordinator
        self._client = client
        self._entry_id = entry.entry_id
        self._membership_id = membership_id
        self._membership = membership
        self._unique_id = f"{entry.unique_id}_Response_{membership_id}"
        self._state = None
        self._state_attributes = {}
        self._state_icon = None
        self._attr_translation_placeholders = {
            "station": membership.get("station_name") or str(membership_id)
        }

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        if self._state_icon == "acknowledged":
            return "mdi:run-fast"
        if self._state_icon == "rejected":
            return "mdi:account-off-outline"
        return "mdi:forum"

    @property
    def is_on(self) -> bool:
        """Return the response state for this membership."""
        return self._state

    @property
    def unique_id(self) -> str:
        """Return a stable unique ID based on membership ID."""
        return self._unique_id

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def available(self) -> bool:
        """Return whether the response control can currently be used."""
        return self._client.on_duty and self._client.incident_id is not None

    @property
    def extra_state_attributes(self) -> dict:
        """Return station, membership and raw response attributes."""
        attr = {
            "membership_id": self._membership_id,
            "station_id": self._membership.get("station_id"),
            "station_name": self._membership.get("station_name"),
            "station_short_code": self._membership.get("station_short_code"),
        }
        attr.update(self._state_attributes)
        return attr

    async def async_turn_on(self, **kwargs) -> None:
        """Send an acknowledged response for this membership."""
        await self._async_set_membership_response("acknowledged")

    async def async_turn_off(self, **kwargs) -> None:
        """Send a rejected response for this membership."""
        await self._async_set_membership_response("rejected")

    async def _async_set_membership_response(self, status: str) -> None:
        """Create an incident response for the selected membership."""
        if not self.available:
            _LOGGER.debug(
                "Cannot send incident response for membership %s while unavailable",
                self._membership_id,
            )
            return

        body = {
            "status": status,
            "membership_id": self._membership_id,
        }
        result = await self._client.update_call(
            self._client.fsr._request,
            "POST",
            f"incidents/{self._client.incident_id}/incident_responses",
            f"set incident response for membership {self._membership_id}",
            None,
            body,
            False,
        )

        if not isinstance(result, dict):
            _LOGGER.error(
                "BrandweerRooster did not accept incident response for membership %s",
                self._membership_id,
            )
            return

        self._apply_response(result)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register incident and coordinator update callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{FIRESERVICEROTA_DOMAIN}_{self._entry_id}_update",
                self.client_update,
            )
        )
        self.async_on_remove(
            self._coordinator.async_add_listener(self.client_update)
        )

    @callback
    def client_update(self) -> None:
        """Schedule a refresh from current incident response data."""
        self.async_schedule_update_ha_state(True)

    def _apply_response(self, response: dict) -> None:
        """Apply raw API response values to the entity state."""
        status = response.get("status")
        if status == "acknowledged":
            self._state = True
            self._state_icon = "acknowledged"
        elif status == "rejected":
            self._state = False
            self._state_icon = "rejected"
        else:
            self._state = None
            self._state_icon = None

        self._state_attributes = dict(response)

    async def async_update(self) -> None:
        """Update this membership's response from the current incident."""
        responses = await self._client.async_response_update()
        if not responses:
            self._state = None
            self._state_attributes = {}
            self._state_icon = None
            return

        response = next(
            (
                item
                for item in responses
                if item.get("membership_id") == self._membership_id
            ),
            None,
        )

        if response is None:
            self._state = None
            self._state_attributes = {}
            self._state_icon = None
            return

        self._apply_response(response)
