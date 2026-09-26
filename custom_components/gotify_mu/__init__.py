"""Gotify MU integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    GotifyMUAuthError,
    GotifyMUClient,
    GotifyMUConnectionError,
    GotifyMUError,
)
from .const import (
    CONF_APP_TOKEN,
    CONF_DEFAULT_PRIORITY,
    CONF_SERVER_URL,
    CONF_VERIFY_SSL,
    DEFAULT_PRIORITY,
    DOMAIN,
    PLATFORMS,
    SERVICE_SEND,
)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("title"): cv.string,
        vol.Optional("priority"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
        vol.Optional("markdown", default=False): cv.boolean,
        vol.Optional("entry_id"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Gotify MU from a config entry."""
    client = GotifyMUClient(
        async_get_clientsession(hass),
        entry.data[CONF_SERVER_URL],
        entry.data[CONF_APP_TOKEN],
        entry.data.get(CONF_VERIFY_SSL, True),
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_SEND):
        async def handle_domain_send(call: ServiceCall) -> None:
            """Send through the requested or first configured Gotify MU entry."""
            entries = hass.config_entries.async_entries(DOMAIN)
            if not entries:
                raise HomeAssistantError("No Gotify MU instances are configured")

            requested = call.data.get("entry_id")
            selected = next(
                (item for item in entries if item.entry_id == requested),
                entries[0] if requested is None else None,
            )
            if selected is None:
                raise HomeAssistantError("Requested Gotify MU config entry was not found")

            selected_client: GotifyMUClient = hass.data[DOMAIN][selected.entry_id]
            priority = call.data.get(
                "priority",
                selected.options.get(CONF_DEFAULT_PRIORITY, DEFAULT_PRIORITY),
            )

            try:
                await selected_client.send(
                    call.data["message"],
                    title=call.data.get("title"),
                    priority=priority,
                    markdown=call.data.get("markdown", False),
                )
            except GotifyMUAuthError as err:
                raise HomeAssistantError(
                    "Gotify MU rejected the application token"
                ) from err
            except GotifyMUConnectionError as err:
                raise HomeAssistantError(
                    f"Could not connect to Gotify MU: {err}"
                ) from err
            except GotifyMUError as err:
                raise HomeAssistantError(str(err)) from err

        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND,
            handle_domain_send,
            schema=SERVICE_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Gotify MU config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if not hass.config_entries.async_entries(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_SEND)
    return unloaded
