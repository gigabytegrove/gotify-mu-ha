"""Notify platform for Gotify MU."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import GotifyMUClient
from .const import (
    CONF_CHANNEL_NAME,
    CONF_DEFAULT_PRIORITY,
    DEFAULT_PRIORITY,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Gotify MU notify entity."""
    client: GotifyMUClient = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GotifyMUNotifyEntity(entry, client)])


class GotifyMUNotifyEntity(NotifyEntity):
    """Gotify MU notification entity."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:message-badge"

    def __init__(self, entry: ConfigEntry, client: GotifyMUClient) -> None:
        self._entry = entry
        self._client = client
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.data[CONF_CHANNEL_NAME]

    async def async_send_message(
        self,
        message: str,
        title: str | None = None,
    ) -> None:
        """Send a notification."""
        priority = self._entry.options.get(
            CONF_DEFAULT_PRIORITY,
            DEFAULT_PRIORITY,
        )
        await self._client.send(
            message,
            title=title,
            priority=priority,
        )
