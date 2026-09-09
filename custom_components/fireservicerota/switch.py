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
    """Set up FireServiceRota switch based on a config entry."""
    client = hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][DATA_COORDINATOR]

    async_add_entities([ResponseSwitch(coordinator, client, entry)])


class ResponseSwitch(SwitchEntity):
    """Legacy incident response switch.

    The original integration exposes one generic response switch. Extended keeps
    that entity for backwards compatibility. For multi-station users the switch
    remains readable, but sending is disabled until the API request model for a
    specific membership has been confirmed.
    """

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
    def name(self) -> str:
        """Return the name of the switch."""
        return "Incident Response"

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
        """Send acknowledge response status."""
        await self.async_set_response(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Send reject response status."""
        await self.async_set_response(False)

    async def async_set_response(self, value) -> None:
        """Send response status when the target membership is unambiguous."""
        if not self._client.on_duty:
            _LOGGER.debug("Cannot send incident response when not on duty")
            return

        if len(self._client.membership_index) > 1:
            _LOGGER.warning(
                "Not sending legacy incident response because this account has "
                "multiple active station memberships"
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
