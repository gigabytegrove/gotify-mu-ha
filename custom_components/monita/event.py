"""Inbound message event platform for Monita."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MonitaConfigEntry
from .const import CONF_SERVER_URL, DOMAIN, EVENT_TYPE_MESSAGE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MonitaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Monita inbound-message event entity."""
    if not entry.runtime_data.inbound_enabled:
        return
    async_add_entities([MonitaMessageEventEntity(entry)])


class MonitaMessageEventEntity(EventEntity):
    """Expose inbound Monita messages as Home Assistant events."""

    _attr_has_entity_name = True
    _attr_event_types = [EVENT_TYPE_MESSAGE]
    _attr_icon = "mdi:message-arrow-left"
    _attr_translation_key = "messages"

    def __init__(self, entry: MonitaConfigEntry) -> None:
        """Initialize the event entity."""
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_message_event"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Monita",
            model="Notification Server",
            configuration_url=entry.data[CONF_SERVER_URL],
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Subscribe after the entity is registered."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._entry.runtime_data.async_subscribe(self._async_handle_message)
        )

    @callback
    def _async_handle_message(self, message: dict[str, Any]) -> None:
        """Record an inbound Monita message."""
        raw_channel_id = message.get("appid")
        try:
            channel_id = int(raw_channel_id)
        except (TypeError, ValueError):
            channel_id = None
        runtime = self._entry.runtime_data
        channel_lookup = getattr(runtime, "channel", None)
        channel = (
            channel_lookup(channel_id)
            if channel_id is not None and callable(channel_lookup)
            else None
        )
        event_data = {
            "message_id": message.get("id"),
            "channel_id": channel_id,
            "channel_name": channel.name if channel is not None else None,
            "title": message.get("title"),
            "message": message.get("message"),
            "priority": message.get("priority"),
            "date": message.get("date"),
            "sender_user_id": message.get("senderUserId"),
            "sender_name": message.get("senderName"),
            "extras": message.get("extras", {}),
        }
        self._trigger_event(EVENT_TYPE_MESSAGE, event_data)
        self.async_write_ha_state()
