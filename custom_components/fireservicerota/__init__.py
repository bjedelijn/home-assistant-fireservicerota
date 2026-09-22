"""The FireServiceRota integration."""
import asyncio
from datetime import datetime, timedelta
import importlib
import logging
from zoneinfo import ZoneInfo

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
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_ADDRESS,
    ATTR_ADDRESSES,
    ATTR_CONFIRMATION,
    ATTR_ENTRY_ID,
    ATTR_INCIDENT_ID,
    ATTR_LIMIT,
    ATTR_MESSAGE,
    ATTR_PAGER_ID,
    ATTR_WEBHOOK_URL,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_INCIDENT_STORE,
    DATA_P2000_MANAGER,
    DOMAIN,
    SERVICE_BACKFILL_HISTORY_STAFFING,
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

BACKFILL_HISTORY_STAFFING_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_INCIDENT_ID): vol.Coerce(str),
        vol.Optional(ATTR_LIMIT, default=25): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=25)
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the FireServiceRota component."""
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry after Extended options change."""
    await hass.config_entries.async_reload(entry.entry_id)


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

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
    }

    _async_register_services(hass)

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
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data[DATA_CLIENT]
    p2000_manager = entry_data.get(DATA_P2000_MANAGER)
    if p2000_manager is not None:
        await p2000_manager.async_stop()
    await hass.async_add_executor_job(client.websocket.stop_listener)

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, SUPPORTED_PLATFORMS
    )

    if unload_ok:
        del hass.data[DOMAIN][entry.entry_id]

    if not hass.data[DOMAIN]:
        for service in (
            SERVICE_SEND_PAGER_MESSAGE,
            SERVICE_BACKFILL_HISTORY_STAFFING,
        ):
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)

    return unload_ok


def _service_entry_data(hass: HomeAssistant, entry_id: str | None) -> dict:
    """Return the config-entry data targeted by a Home Assistant service call."""
    entries = hass.data.get(DOMAIN, {})

    if entry_id:
        entry_data = entries.get(entry_id)
        if not entry_data:
            raise HomeAssistantError(
                f"Unknown FireServiceRota config entry: {entry_id}"
            )
        return entry_data

    if len(entries) == 1:
        return next(iter(entries.values()))

    if not entries:
        raise HomeAssistantError("No FireServiceRota config entry is loaded")

    raise HomeAssistantError(
        "Multiple FireServiceRota config entries are loaded; specify entry_id"
    )


def _service_client(hass: HomeAssistant, entry_id: str | None):
    """Return the client targeted by a Home Assistant service call."""
    return _service_entry_data(hass, entry_id)[DATA_CLIENT]


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""

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

    async def async_backfill_history_staffing(call: ServiceCall) -> dict:
        """Re-fetch retained closed incidents that lack staffing data."""
        entry_data = _service_entry_data(hass, call.data.get(ATTR_ENTRY_ID))
        incident_store = entry_data.get(DATA_INCIDENT_STORE)
        if incident_store is None:
            raise HomeAssistantError(
                "FireServiceRota incident history is not ready yet"
            )

        result = await incident_store.async_backfill_history_staffing(
            incident_id=call.data.get(ATTR_INCIDENT_ID),
            limit=call.data.get(ATTR_LIMIT, 25),
        )
        _LOGGER.info("History staffing backfill result: %s", result)
        return result

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_PAGER_MESSAGE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_PAGER_MESSAGE,
            async_send_pager_message,
            schema=SEND_PAGER_MESSAGE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_BACKFILL_HISTORY_STAFFING):
        hass.services.async_register(
            DOMAIN,
            SERVICE_BACKFILL_HISTORY_STAFFING,
            async_backfill_history_staffing,
            schema=BACKFILL_HISTORY_STAFFING_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
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
        self.legacy_duty_data = {}
        self.membership_duty = {}
        self.do_not_disturb = None

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
        """Start websocket listener and discover user-related API objects."""
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

    async def async_api_get(self, endpoint, params=None):
        """Call an API v2 GET endpoint through pyfireservicerota."""
        return await self.update_call(
            self.fsr._request,
            "GET",
            endpoint,
            f"get {endpoint}",
            params,
            None,
            False,
        )

    @staticmethod
    def _sanitize_debug_value(value):
        """Return API structure useful for debugging without personal fields."""
        blocked_keys = {
            "address",
            "addresses",
            "coordinates",
            "email",
            "emails",
            "first_name",
            "last_name",
            "members",
            "memberships",
            "name_of_user",
            "phone",
            "phone_number",
            "token",
            "tokens",
            "user",
            "users",
        }
        if isinstance(value, dict):
            return {
                key: FireServiceRotaClient._sanitize_debug_value(item)
                for key, item in value.items()
                if key not in blocked_keys
            }
        if isinstance(value, list):
            return [FireServiceRotaClient._sanitize_debug_value(item) for item in value]
        return value

    @staticmethod
    def _extract_alerting_debug(data, path="user") -> dict:
        """Extract communication/alerting preference fields and their paths."""
        keywords = (
            "alert",
            "communication",
            "disturb",
            "mute",
            "notification",
            "preference",
            "silent",
        )
        found = {}

        if isinstance(data, dict):
            for key, value in data.items():
                child_path = f"{path}.{key}"
                if any(keyword in key.lower() for keyword in keywords):
                    found[child_path] = FireServiceRotaClient._sanitize_debug_value(value)
                if isinstance(value, (dict, list)):
                    found.update(
                        FireServiceRotaClient._extract_alerting_debug(value, child_path)
                    )
        elif isinstance(data, list):
            for index, value in enumerate(data):
                if isinstance(value, (dict, list)):
                    found.update(
                        FireServiceRotaClient._extract_alerting_debug(
                            value, f"{path}[{index}]"