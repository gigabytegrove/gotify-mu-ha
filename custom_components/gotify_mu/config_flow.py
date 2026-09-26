"""Config flow for Gotify MU."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GotifyMUClient, GotifyMUConnectionError
from .const import (
    CONF_APP_TOKEN,
    CONF_CHANNEL_NAME,
    CONF_DEFAULT_PRIORITY,
    CONF_SERVER_URL,
    CONF_VERIFY_SSL,
    DEFAULT_NAME,
    DEFAULT_PRIORITY,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)


class GotifyMUConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Gotify MU."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            server_url = user_input[CONF_SERVER_URL].strip().rstrip("/")
            channel_name = user_input[CONF_CHANNEL_NAME].strip()
            app_token = user_input[CONF_APP_TOKEN].strip()

            client = GotifyMUClient(
                async_get_clientsession(self.hass),
                server_url,
                app_token,
                user_input[CONF_VERIFY_SSL],
            )

            try:
                await client.health()
            except GotifyMUConnectionError:
                errors["base"] = "cannot_connect"
            else:
                unique_id = f"{server_url}|{channel_name.lower()}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=channel_name,
                    data={
                        CONF_SERVER_URL: server_url,
                        CONF_APP_TOKEN: app_token,
                        CONF_CHANNEL_NAME: channel_name,
                        CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                    },
                    options={
                        CONF_DEFAULT_PRIORITY: user_input[CONF_DEFAULT_PRIORITY],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SERVER_URL): str,
                vol.Required(CONF_APP_TOKEN): str,
                vol.Required(CONF_CHANNEL_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
                vol.Required(
                    CONF_DEFAULT_PRIORITY, default=DEFAULT_PRIORITY
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "GotifyMUOptionsFlow":
        """Create the options flow."""
        return GotifyMUOptionsFlow(config_entry)


class GotifyMUOptionsFlow(config_entries.OptionsFlow):
    """Handle Gotify MU options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEFAULT_PRIORITY,
                        default=self._config_entry.options.get(
                            CONF_DEFAULT_PRIORITY, DEFAULT_PRIORITY
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10))
                }
            ),
        )
