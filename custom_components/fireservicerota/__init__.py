"""The FireServiceRota integration."""
import asyncio
from datetime import timedelta
import importlib
import logging

from pyfireservicerota import (
    ExpiredTokenError,
    FireServiceRota,
    FireServiceRotaIncidents,
    InvalidAuthError,
    InvalidTokenError,
)
import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.const import CONF_TOKEN, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_ADDRESS,
    ATTR_ADDRESSES,
    ATTR_CONFIRMATION,
    ATTR_ENTRY_ID,
    ATTR_MESSAGE,
    ATTR_PAGER_ID,
    ATTR_WEBHOOK_URL,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DOMAIN,
    SERVICE_SEND_PAGER_MESSAGE,
    WSS_BWRURL,
)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

_LOGGER = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]

SEND_PAGER_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_PAGER_ID): vol.Coerce(int),
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_ADDRESS): cv.string,
        vol.Optional(ATTR_ADDRESSES): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_CONFIRMATION, default=True): cv.boolean,
        vol.Optional(ATTR_WEBHOOK_URL): cv.url,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the FireServiceRota component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up FireServiceRota from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    client = FireServiceRotaClient(hass, entry)
    await client.setup()

    if client.token_refresh_failure:
        return False

    async def async_update_data():
        return await client.async_update()

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="FireServiceRota data",
        update_method=async_update_data,
        update_interval=MIN_TIME_BETWEEN_UPDATES,
    )

    await coordinator.async_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
    }

    _async_register_services(hass)

    # Home Assistant 2026.x / Python 3.14 can flag lazy platform imports from
    # async_forward_entry_setups() as blocking disk I/O. Pre-import the platform
    # modules in executor threads so the subsequent loader lookup is served from
    # sys.modules and remains event-loop safe.
    await asyncio.gather(
        *(
            hass.async_add_executor_job(
                importlib.import_module,
                f"{__package__}.{platform.value}",
            )
            for platform in SUPPORTED_PLATFORMS
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload FireServiceRota config entry."""
    client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
    await hass.async_add_executor_job(client.websocket.stop_listener)

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, SUPPORTED_PLATFORMS
    )

    if unload_ok:
        del hass.data[DOMAIN][entry.entry_id]

    if not hass.data[DOMAIN] and hass.services.has_service(
        DOMAIN, SERVICE_SEND_PAGER_MESSAGE
    ):
        hass.services.async_remove(DOMAIN, SERVICE_SEND_PAGER_MESSAGE)

    return unload_ok


def _service_client(hass: HomeAssistant, entry_id: str | None):
    """Return the client targeted by a Home Assistant service call."""
    entries = hass.data.get(DOMAIN, {})

    if entry_id:
        entry_data = entries.get(entry_id)
        if not entry_data:
            raise HomeAssistantError(
                f"Unknown FireServiceRota config entry: {entry_id}"
            )
        return entry_data[DATA_CLIENT]

    if len(entries) == 1:
        return next(iter(entries.values()))[DATA_CLIENT]

    if not entries:
        raise HomeAssistantError("No FireServiceRota config entry is loaded")

    raise HomeAssistantError(
        "Multiple FireServiceRota config entries are loaded; specify entry_id"
    )


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_PAGER_MESSAGE):
        return

    async def async_send_pager_message(call: ServiceCall) -> None:
        """Send a message through a discovered BrandweerRooster pager."""
        client = _service_client(hass, call.data.get(ATTR_ENTRY_ID))
        pager_id = call.data.get(ATTR_PAGER_ID)

        if pager_id is None:
            if len(client.pagers) != 1:
                raise HomeAssistantError(
                    "pager_id is required unless exactly one pager is linked"
                )
            pager_id = client.pagers[0].get("id")

        if pager_id not in client.pagers_by_id:
            raise HomeAssistantError(
                f"Pager {pager_id} is not linked to this FireServiceRota account"
            )

        if call.data.get(ATTR_ADDRESS) and call.data.get(ATTR_ADDRESSES):
            raise HomeAssistantError(
                "Use either address or addresses for a pager message, not both"
            )

        result = await client.async_send_pager_message(
            pager_id=pager_id,
            message=call.data[ATTR_MESSAGE],
            address=call.data.get(ATTR_ADDRESS),
            addresses=call.data.get(ATTR_ADDRESSES),
            confirmation=call.data.get(ATTR_CONFIRMATION, True),
            webhook_url=call.data.get(ATTR_WEBHOOK_URL),
        )

        if not isinstance(result, dict):
            raise HomeAssistantError("BrandweerRooster did not accept the pager message")

        client.last_pager_message = result
        dispatcher_send(hass, f"{DOMAIN}_{client.entry_id}_pager_update")

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_PAGER_MESSAGE,
        async_send_pager_message,
        schema=SEND_PAGER_MESSAGE_SCHEMA,
    )


class FireServiceRotaOauth:
    """Handle authentication tokens."""

    def __init__(self, hass, entry, fsr):
        """Initialize the oauth object."""
        self._hass = hass
        self._entry = entry
        self._url = entry.data[CONF_URL]
        self._username = entry.data[CONF_USERNAME]
        self._fsr = fsr

    async def async_refresh_tokens(self) -> bool:
        """Refresh tokens and update config entry."""
        _LOGGER.debug("Refreshing authentication tokens after expiration")

        try:
            token_info = await self._hass.async_add_executor_job(
                self._fsr.refresh_tokens
            )
        except (InvalidAuthError, InvalidTokenError):
            _LOGGER.error("Error refreshing tokens, triggered reauth workflow")
            self._hass.async_create_task(
                self._hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_REAUTH},
                    data={**self._entry.data},
                )
            )
            return False

        _LOGGER.debug("Saving new tokens in config entry")
        self._hass.config_entries.async_update_entry(
            self._entry,
            data={
                "auth_implementation": DOMAIN,
                CONF_URL: self._url,
                CONF_USERNAME: self._username,
                CONF_TOKEN: token_info,
            },
        )
        return True


class FireServiceRotaWebSocket:
    """Define a FireServiceRota websocket manager object."""

    def __init__(self, hass, entry):
        """Initialize the websocket object."""
        self._hass = hass
        self._entry = entry
        self._fsr_incidents = FireServiceRotaIncidents(on_incident=self._on_incident)
        self.incident_data = None

    def _construct_url(self) -> str:
        """Return URL with latest access token."""
        return WSS_BWRURL.format(
            self._entry.data[CONF_URL], self._entry.data[CONF_TOKEN]["access_token"]
        )

    def _on_incident(self, data) -> None:
        """Received new incident, update data."""
        _LOGGER.debug("Received new incident via websocket: %s", data)
        self.incident_data = data
        dispatcher_send(self._hass, f"{DOMAIN}_{self._entry.entry_id}_update")

    def start_listener(self) -> None:
        """Start the websocket listener."""
        _LOGGER.debug("Starting incidents listener")
        self._fsr_incidents.start(self._construct_url())

    def stop_listener(self) -> None:
        """Stop the websocket listener."""
        _LOGGER.debug("Stopping incidents listener")
        self._fsr_incidents.stop()


class FireServiceRotaClient:
    """Get data from FireServiceRota / BrandweerRooster."""

    def __init__(self, hass, entry):
        """Initialize the data object."""
        self._hass = hass
        self._entry = entry
        self._url = entry.data[CONF_URL]
        self._tokens = entry.data[CONF_TOKEN]

        self.entry_id = entry.entry_id
        self.unique_id = entry.unique_id

        self.token_refresh_failure = False
        self.incident_id = None
        self.on_duty = False

        self.user_data = None
        self.groups = []
        self.stations = []
        self.membership_index = {}
        self.task_index = {}
        self.pagers = []
        self.pagers_by_id = {}
        self.last_pager_message = None

        self.fsr = FireServiceRota(base_url=self._url, token_info=self._tokens)
        self.oauth = FireServiceRotaOauth(self._hass, self._entry, self.fsr)
        self.websocket = FireServiceRotaWebSocket(self._hass, self._entry)

    async def setup(self) -> None:
        """Start the websocket listener and discover user-related API objects."""
        await self._hass.async_add_executor_job(self.websocket.start_listener)
        await self.async_discover()

    async def update_call(self, func, *args):
        """Perform API call, transparently refreshing expired tokens."""
        if self.token_refresh_failure:
            return None

        try:
            return await self._hass.async_add_executor_job(func, *args)
        except (ExpiredTokenError, InvalidTokenError):
            await self._hass.async_add_executor_job(self.websocket.stop_listener)
            self.token_refresh_failure = True

            if await self.oauth.async_refresh_tokens():
                self.token_refresh_failure = False
                await self._hass.async_add_executor_job(self.websocket.start_listener)
                return await self._hass.async_add_executor_job(func, *args)

        return None

    async def async_api_get(self, endpoint):
        """Call an API v2 GET endpoint through pyfireservicerota.

        pyfireservicerota 0.0.49 has no public get_groups() method yet. This
        compatibility shim can later be replaced by a public library method.
        """
        return await self.update_call(
            self.fsr._request,
            "GET",
            endpoint,
            f"get {endpoint}",
            None,
            None,
            False,
        )

    async def async_discover(self) -> None:
        """Discover current user, stations, memberships, tasks and pagers."""
        user_data = await self.update_call(self.fsr.get_user)
        groups = await self.async_api_get("groups")
        pagers = await self.update_call(self.fsr.get_pagers)

        if isinstance(user_data, dict):
            self.user_data = user_data

        if isinstance(groups, list):
            self.groups = groups
            self._rebuild_group_indexes()

        if isinstance(pagers, list):
            self.pagers = pagers
            self.pagers_by_id = {
                pager["id"]: pager
                for pager in pagers
                if pager.get("id") is not None
            }

        _LOGGER.debug(
            "Discovered %s stations, %s memberships, %s tasks and %s pagers",
            len(self.stations),
            len(self.membership_index),
            len(self.task_index),
            len(self.pagers),
        )

    def _rebuild_group_indexes(self) -> None:
        """Build indexes for this user's stations, memberships and tasks."""
        self.stations = []
        self.membership_index = {}
        self.task_index = {}

        if not self.user_data:
            return

        user_id = self.user_data.get("id")
        if user_id is None:
            return

        for group in self.groups:
            if group.get("type") != "station":
                continue

            memberships = [
                membership
                for membership in group.get("memberships", [])
                if membership.get("user_id") == user_id
                and membership.get("status") == "active"
            ]
            if not memberships:
                continue

            station = {
                "id": group.get("id"),
                "name": group.get("name"),
                "short_code": group.get("short_code"),
                "crew_type": group.get("crew_type"),
                "coordinates": group.get("coordinates"),
                "enabled_features": group.get("enabled_features", []),
                "memberships": memberships,
                "tasks": group.get("tasks", []),
            }
            self.stations.append(station)

            for membership in memberships:
                membership_id = membership.get("id")
                if membership_id is not None:
                    self.membership_index[membership_id] = {
                        **membership,
                        "station_id": group.get("id"),
                        "station_name": group.get("name"),
                        "station_short_code": group.get("short_code"),
                    }

            for task in group.get("tasks", []):
                task_id = task.get("id")
                if task_id is None:
                    continue
                task_info = {
                    "id": task_id,
                    "name": task.get("name"),
                    "alertable": task.get("alertable"),
                    "station_id": group.get("id"),
                    "station_name": group.get("name"),
                    "station_short_code": group.get("short_code"),
                }
                self.task_index.setdefault(task_id, []).append(task_info)

    async def async_update(self) -> object:
        """Get latest availability, pager data and last pager-message status."""
        data = await self.update_call(
            self.fsr.get_availability, str(self._hass.config.time_zone)
        )

        if data:
            self.on_duty = bool(data.get("available"))
            _LOGGER.debug("Updated availability data: %s", data)

        pagers = await self.update_call(self.fsr.get_pagers)
        if isinstance(pagers, list):
            self.pagers = pagers
            self.pagers_by_id = {
                pager["id"]: pager
                for pager in pagers
                if pager.get("id") is not None
            }

        if isinstance(self.last_pager_message, dict):
            pager_id = self.last_pager_message.get("pager_id")
            message_id = self.last_pager_message.get("id")
            if pager_id is not None and message_id is not None:
                status = await self.update_call(
                    self.fsr.get_pager_message_status, pager_id, message_id
                )
                if isinstance(status, dict):
                    merged_message = dict(self.last_pager_message)
                    merged_message.update(status)
                    self.last_pager_message = merged_message

        return data

    async def async_get_incident(self, incident_id) -> object:
        """Return full incident data from the REST API."""
        if not incident_id:
            return None
        return await self.async_api_get(f"incidents/{incident_id}")

    def own_incident_responses(self, data: dict) -> list[dict]:
        """Return all responses belonging to the authenticated user."""
        user_id = self.user_data.get("id") if self.user_data else None
        if user_id is None:
            return []

        own = []
        for response in data.get("incident_responses", []) or []:
            if response.get("user_id") != user_id:
                continue

            membership = self.membership_index.get(response.get("membership_id"), {})
            own.append(
                {
                    "station_id": membership.get(
                        "station_id", response.get("group_id")
                    ),
                    "station_name": membership.get("station_name"),
                    "station_short_code": membership.get("station_short_code"),
                    "membership_id": response.get("membership_id"),
                    "group_id": response.get("group_id"),
                    "status": response.get("status"),
                    "responded_at": response.get("responded_at"),
                    "channel": response.get("channel"),
                    "reported_status": response.get("reported_status"),
                    "arrived_at_station": response.get("arrived_at_station"),
                    "estimated_time_of_arrival": response.get(
                        "estimated_time_of_arrival"
                    ),
                }
            )
        return own

    def enrich_incident_data(self, data: dict) -> dict:
        """Enrich incident with resolved stations, tasks and own responses."""
        enriched = dict(data)
        task_ids = data.get("task_ids") or []
        resolved_tasks = []
        resolved_stations = {}

        for task_id in task_ids:
            for task in self.task_index.get(task_id, []):
                resolved_tasks.append(task)
                station_id = task.get("station_id")
                if station_id is not None:
                    resolved_stations[station_id] = {
                        "id": station_id,
                        "name": task.get("station_name"),
                        "short_code": task.get("station_short_code"),
                    }

        enriched["resolved_tasks"] = resolved_tasks
        enriched["resolved_stations"] = list(resolved_stations.values())
        enriched["responses_by_station"] = self.own_incident_responses(data)
        return enriched

    async def async_response_update(self) -> object:
        """Get all current-user response data for the latest incident."""
        if not self.incident_id:
            return None

        _LOGGER.debug("Updating response data for incident id %s", self.incident_id)
        incident = await self.async_get_incident(self.incident_id)
        if not isinstance(incident, dict):
            return None
        return self.own_incident_responses(incident)

    async def async_set_response(self, value) -> None:
        """Set incident response status using the existing API wrapper method."""
        if not self.incident_id:
            return

        _LOGGER.debug(
            "Setting incident response for incident id '%s' to state '%s'",
            self.incident_id,
            value,
        )
        await self.update_call(self.fsr.set_incident_response, self.incident_id, value)

    async def async_send_pager_message(
        self,
        pager_id: int,
        message: str,
        address: str | None = None,
        addresses: list | None = None,
        confirmation: bool = True,
        webhook_url: str | None = None,
    ) -> object:
        """Send a pager message using the public pyfireservicerota method."""
        return await self.update_call(
            self.fsr.send_pager_message,
            pager_id,
            message,
            address,
            addresses,
            confirmation,
            webhook_url,
        )
