"""Config flow for FireServiceRota."""
from pyfireservicerota import FireServiceRota, InvalidAuthError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_URL, CONF_USERNAME
from homeassistant.core import callback

from .const import (
    CONF_P2000_ENABLED,
    CONF_P2000_RTL_TOPIC,
    CONF_P2000_SCAN_INTERVAL,
    CONF_P2000_SOURCE,
    DOMAIN,
    P2000_DEFAULT_RTL_TOPIC,
    P2000_DEFAULT_SCAN_INTERVAL,
    P2000_SOURCE_BOTH,
    P2000_SOURCE_ONLINE,
    P2000_SOURCE_RTL,
    URL_LIST,
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, default="www.brandweerrooster.nl"): vol.In(URL_LIST),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class FireServiceRotaFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a FireServiceRota config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize config flow."""
        self.api = None
        self._base_url = None
        self._username = None
        self._password = None
        self._existing_entry = None
        self._description_placeholders = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return FireServiceRotaOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""
        errors = {}

        if user_input is None:
            return self._show_setup_form(user_input, errors)

        return await self._validate_and_create_entry(user_input, "user")

    async def _validate_and_create_entry(self, user_input, step_id):
        """Check if config is valid and create entry if so."""
        self._password = user_input[CONF_PASSWORD]

        extra_inputs = user_input

        if self._existing_entry:
            extra_inputs = self._existing_entry

        self._username = extra_inputs[CONF_USERNAME]
        self._base_url = extra_inputs[CONF_URL]

        if self.unique_id is None:
            await self.async_set_unique_id(self._username)
            self._abort_if_unique_id_configured()

        self.api = FireServiceRota(
            base_url=self._base_url,
            username=self._username,
            password=self._password,
        )

        try:
            token_info = await self.hass.async_add_executor_job(self.api.request_tokens)
        except InvalidAuthError:
            self.api = None
            return self.async_show_form(
                step_id=step_id,
                data_schema=DATA_SCHEMA,
                errors={"base": "invalid_auth"},
            )

        data = {
            "auth_implementation": DOMAIN,
            CONF_URL: self._base_url,
            CONF_USERNAME: self._username,
            CONF_TOKEN: token_info,
        }

        if step_id == "user":
            return self.async_create_entry(title=self._username, data=data)

        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.unique_id == self.unique_id:
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

    def _show_setup_form(self, user_input=None, errors=None, step_id="user"):
        """Show the setup form to the user."""

        if user_input is None:
            user_input = {}

        if step_id == "user":
            schema = {
                vol.Required(CONF_URL, default="www.brandweerrooster.nl"): vol.In(
                    URL_LIST
                ),
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        else:
            schema = {vol.Required(CONF_PASSWORD): str}

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema),
            errors=errors or {},
            description_placeholders=self._description_placeholders,
        )

    async def async_step_reauth(self, user_input=None):
        """Get new tokens for a config entry that can't authenticate."""

        if not self._existing_entry:
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._existing_entry = user_input.copy()
            self._description_placeholders = {"username": user_input[CONF_USERNAME]}
            user_input = None

        if user_input is None:
            return self._show_setup_form(step_id=config_entries.SOURCE_REAUTH)

        return await self._validate_and_create_entry(
            user_input, config_entries.SOURCE_REAUTH
        )

class FireServiceRotaOptionsFlow(config_entries.OptionsFlowWithReload):
    """Configure optional Extended features."""

    async def async_step_init(self, user_input=None):
        """Configure Netherlands-only P2000 enrichment."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        if self.config_entry.data.get(CONF_URL) != "www.brandweerrooster.nl":
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                description_placeholders={"p2000_availability": "P2000 is only available for BrandweerRooster Netherlands."},
            )

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_P2000_ENABLED,
                    default=bool(current.get(CONF_P2000_ENABLED, False)),
                ): bool,
                vol.Optional(
                    CONF_P2000_SOURCE,
                    default=current.get(CONF_P2000_SOURCE, P2000_SOURCE_ONLINE),
                ): vol.In(
                    {
                        P2000_SOURCE_ONLINE: "P2000 online",
                        P2000_SOURCE_RTL: "P2000 via ether (RTL-SDR, beta)",
                        P2000_SOURCE_BOTH: "P2000 online + ether (beta)",
                    }
                ),
                vol.Optional(
                    CONF_P2000_RTL_TOPIC,
                    default=str(
                        current.get(CONF_P2000_RTL_TOPIC, P2000_DEFAULT_RTL_TOPIC)
                    ),
                ): str,
                vol.Optional(
                    CONF_P2000_SCAN_INTERVAL,
                    default=int(
                        current.get(
                            CONF_P2000_SCAN_INTERVAL,
                            P2000_DEFAULT_SCAN_INTERVAL,
                        )
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)