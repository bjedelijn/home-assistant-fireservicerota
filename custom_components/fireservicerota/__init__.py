"""The FireServiceRota integration."""
import asyncio
from datetime import timedelta
import logging

from pyfireservicerota import (
    ExpiredTokenError,
    FireServiceRota,
    FireServiceRotaIncidents,
    InvalidAuthError,
    InvalidTokenError,
)

from homeassistant.components.binary_sensor import DOMAIN as BINARYSENSOR_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.const import CONF_TOKEN, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN, WSS_BWRURL

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

_LOGGER = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = {SENSOR_DOMAIN, BINARYSENSOR_DOMAIN, SWITCH_DOMAIN}


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

    for platform in SUPPORTED_PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload FireServiceRota config entry."""
    client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
    await hass.async_add_executor_job(client.websocket.stop_listener)

    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in SUPPORTED_PLATFORMS
            ]
        )
    )

    if unload_ok:
        del hass.data[DOMAIN][entry.entry_id]

    return unload_ok


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

        # Extended discovery data. These indexes are built dynamically from the
        # authenticated user's API data; no station/task IDs are hardcoded.
        self.user_data = None
        self.groups = []
        self.stations = []
        self.membership_index = {}
        self.task_index = {}
        self.pagers = []
        self.pagers_by_id = {}

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

        pyfireservicerota 0.0.49 has no public get_groups() method yet. Keeping
        this small compatibility shim here lets the HA integration discover
        stations now, while making it easy to replace with get_groups() later.
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
                    **task,
                    "station_id": group.get("id"),
                    "station_name": group.get("name"),
                    "station_short_code": group.get("short_code"),
                }
                self.task_index.setdefault(task_id, []).append(task_info)

    async def async_update(self) -> object:
        """Get latest availability and pager data."""
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

        return data

    async def async_get_incident(self, incident_id) -> object:
        """Return full incident data from the REST API."""
        if not incident_id:
            return None
        return await self.async_api_get(f"incidents/{incident_id}")

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

        responses_by_station = []
        user_id = self.user_data.get("id") if self.user_data else None
        if user_id is not None:
            for response in data.get("incident_responses", []) or []:
                if response.get("user_id") != user_id:
                    continue

                membership = self.membership_index.get(
                    response.get("membership_id"), {}
                )
                status = response.get("status")
                if status == "acknowledged":
                    friendly_response = "accepted"
                elif status == "rejected":
                    friendly_response = "rejected"
                else:
                    friendly_response = status or "unknown"

                responses_by_station.append(
                    {
                        "station_id": membership.get(
                            "station_id", response.get("group_id")
                        ),
                        "station_name": membership.get("station_name"),
                        "station_short_code": membership.get(
                            "station_short_code"
                        ),
                        "membership_id": response.get("membership_id"),
                        "group_id": response.get("group_id"),
                        "status": status,
                        "response": friendly_response,
                        "responded_at": response.get("responded_at"),
                        "channel": response.get("channel"),
                        "reported_status": response.get("reported_status"),
                        "arrived_at_station": response.get(
                            "arrived_at_station"
                        ),
                        "estimated_time_of_arrival": response.get(
                            "estimated_time_of_arrival"
                        ),
                    }
                )

        enriched["resolved_tasks"] = resolved_tasks
        enriched["resolved_stations"] = list(resolved_stations.values())
        enriched["responses_by_station"] = responses_by_station
        return enriched

    async def async_response_update(self) -> object:
        """Get the latest incident response data."""
        if not self.incident_id:
            return None

        _LOGGER.debug("Updating response data for incident id %s", self.incident_id)
        return await self.update_call(self.fsr.get_incident_response, self.incident_id)

    async def async_set_response(self, value) -> None:
        """Set incident response status."""
        if not self.incident_id:
            return

        _LOGGER.debug(
            "Setting incident response for incident id '%s' to state '%s'",
            self.incident_id,
            value,
        )
        await self.update_call(self.fsr.set_incident_response, self.incident_id, value)
