"""Notify platform for Monita."""

from __future__ import annotations

from typing import override

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GotifyMUConfigEntry
from .api import (
    GotifyMUAuthError,
    GotifyMUConnectionError,
    GotifyMUError,
    GotifyMURateLimitError,
)
from .const import (
    CONF_DEFAULT_PRIORITY,
    CONF_SERVER_URL,
    DEFAULT_PRIORITY,
    DOMAIN,
    INTEGRATION_ORIGIN_EXTRA,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GotifyMUConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Monita notify entity."""
    async_add_entities([GotifyMUNotifyEntity(entry)])


class GotifyMUNotifyEntity(NotifyEntity):
    """Monita notification entity."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:message-badge"
    _attr_translation_key = "notifications"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, entry: GotifyMUConfigEntry) -> None:
        """Initialize the notify entity."""
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_notify"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.runtime_data.channel_name,
            manufacturer="Monita",
            model="Notification Channel",
            configuration_url=entry.data[CONF_SERVER_URL],
        )

    @override
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
        try:
            await self._entry.runtime_data.client.async_send(
                message,
                title=title,
                priority=priority,
                extras={
                    INTEGRATION_ORIGIN_EXTRA: {
                        "entry_id": self._entry.entry_id,
                        "source": "monita-ha",
                    }
                },
            )
        except GotifyMUAuthError as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Monita rejected the application token") from err
        except GotifyMURateLimitError as err:
            raise HomeAssistantError("Monita rate limited the notification") from err
        except GotifyMUConnectionError as err:
            raise HomeAssistantError(f"Could not connect to Monita: {err}") from err
        except GotifyMUError as err:
            raise HomeAssistantError(str(err)) from err
