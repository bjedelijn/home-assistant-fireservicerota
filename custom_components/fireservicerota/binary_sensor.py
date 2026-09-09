"""Binary Sensor platform for FireServiceRota integration."""
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN as FIRESERVICEROTA_DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up FireServiceRota binary sensors based on a config entry."""
    client = hass.data[FIRESERVICEROTA_DOMAIN][entry.entry_id][DATA_CLIENT]
    coordinator: DataUpdateCoordinator = hass.data[FIRESERVICEROTA_DOMAIN][
        entry.entry_id
    ][DATA_COORDINATOR]

    entities = [
        ResponseBinarySensor(coordinator, client, entry),
        DoNotDisturbBinarySensor(coordinator, client, entry),
    ]

    if len(client.membership_index) > 1:
        for membership_id, membership in client.membership_index.items():
            entities.append(
                MembershipDutyBinarySensor(
                    coordinator,
                    client,
                    entry,
                    membership_id,
                    membership,
                )
            )

    async_add_entities(entities)


class ResponseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of the legacy aggregate FireServiceRota duty sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "duty"

    def __init__(self, coordinator: DataUpdateCoordinator, client, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.unique_id}_Duty"

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        if self.is_on:
            return "mdi:calendar-check"
        return "mdi:calendar-remove"

    @property
    def is_on(self) -> bool:
        """Return aggregate duty state."""
        return self._client.on_duty

    @property
    def extra_state_attributes(self) -> dict:
        """Return aggregate/legacy availability attributes."""
        data = self._client.legacy_duty_data or {}
        attr = {
            key: data[key]
            for key in (
                "start_time",
                "end_time",
                "available",
                "active",
                "assigned_function_ids",
                "skill_ids",
                "type",
                "assigned_function",
            )
            if key in data
        }
        attr["multi_station"] = len(self._client.membership_index) > 1
        if len(self._client.membership_index) > 1:
            attr["membership_count"] = len(self._client.membership_index)
        return attr


class MembershipDutyBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Duty state for one BrandweerRooster membership/station."""

    _attr_has_entity_name = True
    _attr_translation_key = "duty_station"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        client,
        entry,
        membership_id: int,
        membership: dict,
    ):
        """Initialize a station-specific duty sensor."""
        super().__init__(coordinator)
        self._client = client
        self._membership_id = membership_id
        self._membership = membership
        self._attr_unique_id = f"{entry.unique_id}_Duty_{membership_id}"
        self._attr_translation_placeholders = {
            "station": membership.get("station_name") or str(membership_id)
        }

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        if self.is_on:
            return "mdi:calendar-check"
        return "mdi:calendar-remove"

    @property
    def is_on(self) -> bool:
        """Return duty state for this membership."""
        data = self._client.membership_duty.get(self._membership_id, {})
        return bool(data.get("available"))

    @property
    def available(self) -> bool:
        """Return whether duty data for this membership has been retrieved."""
        return self._membership_id in self._client.membership_duty

    @property
    def extra_state_attributes(self) -> dict:
        """Return station and raw current availability attributes."""
        data = self._client.membership_duty.get(self._membership_id, {})
        attr = {
            "membership_id": self._membership_id,
            "station_id": self._membership.get("station_id"),
            "station_name": self._membership.get("station_name"),
            "station_short_code": self._membership.get("station_short_code"),
        }
        attr.update(
            {
                key: data[key]
                for key in (
                    "start_time",
                    "end_time",
                    "available",
                    "active",
                    "assigned_function_ids",
                    "skill_ids",
                    "type",
                    "assigned_function",
                )
                if key in data
            }
        )
        return attr


class DoNotDisturbBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Global BrandweerRooster do-not-disturb state for the authenticated user."""

    _attr_has_entity_name = True
    _attr_translation_key = "do_not_disturb"
    _attr_icon = "mdi:bell-off"

    def __init__(self, coordinator: DataUpdateCoordinator, client, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.unique_id}_DoNotDisturb"

    @property
    def is_on(self) -> bool:
        """Return the raw user-level do-not-disturb flag."""
        return bool(self._client.do_not_disturb)

    @property
    def extra_state_attributes(self) -> dict:
        """Expose that this state belongs to the user, not one station."""
        return {"scope": "user"}
