"""Connection status binary sensor for Gotify MU."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GotifyMUConfigEntry
from .const import CONF_SERVER_URL, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GotifyMUConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Gotify MU stream status entity."""
    if not entry.runtime_data.inbound_enabled:
        return
    async_add_entities([GotifyMUConnectionBinarySensor(entry)])


class GotifyMUConnectionBinarySensor(BinarySensorEntity):
    """Represent the realtime inbound stream connection state."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "inbound_connection"

    def __init__(self, entry: GotifyMUConfigEntry) -> None:
        """Initialize the connection sensor."""
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_inbound_connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.runtime_data.channel_name,
            manufacturer="Gotify MU",
            model="Notification Channel",
            configuration_url=entry.data[CONF_SERVER_URL],
        )

    @property
    @override
    def is_on(self) -> bool:
        """Return whether the inbound WebSocket is connected."""
        return self._entry.runtime_data.stream_connected

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return stream diagnostics."""
        runtime = self._entry.runtime_data
        return {
            "reconnects": runtime.stream_reconnects,
            "last_error": runtime.last_stream_error,
        }

    @override
    async def async_added_to_hass(self) -> None:
        """Subscribe to stream status changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._entry.runtime_data.async_subscribe_status(self._async_status_changed)
        )

    @callback
    def _async_status_changed(self) -> None:
        """Write state after stream status changes."""
        self.async_write_ha_state()
