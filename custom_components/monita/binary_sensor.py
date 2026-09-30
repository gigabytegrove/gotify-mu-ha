"""Connection status binary sensors for Monita."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MonitaConfigEntry
from .const import CONF_SERVER_URL, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MonitaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Monita connection status entities."""
    entities: list[BinarySensorEntity] = []
    if entry.runtime_data.inbound_enabled:
        entities.append(MonitaConnectionBinarySensor(entry))
    if entry.runtime_data.native_bridge is not None:
        entities.append(MonitaNativeBridgeBinarySensor(entry))
    if entities:
        async_add_entities(entities)


class _MonitaBaseConnectionSensor(BinarySensorEntity):
    """Shared Monita connection sensor device metadata."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, entry: MonitaConfigEntry) -> None:
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Monita",
            model="Notification Server",
            configuration_url=entry.data[CONF_SERVER_URL],
        )


class MonitaConnectionBinarySensor(_MonitaBaseConnectionSensor):
    """Represent the realtime inbound stream connection state."""

    _attr_translation_key = "inbound_connection"

    def __init__(self, entry: MonitaConfigEntry) -> None:
        """Initialize the inbound stream entity."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.unique_id}_inbound_connection"

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


class MonitaNativeBridgeBinarySensor(_MonitaBaseConnectionSensor):
    """Represent native Monita bridge health."""

    _attr_translation_key = "native_bridge"

    def __init__(self, entry: MonitaConfigEntry) -> None:
        """Initialize the native bridge entity."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.unique_id}_native_bridge"

    @property
    def _bridge(self):
        return self._entry.runtime_data.native_bridge

    @property
    @override
    def is_on(self) -> bool:
        """Return whether the native bridge is healthy."""
        return bool(self._bridge and self._bridge.is_connected)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return native bridge health and delivery diagnostics."""
        bridge = self._bridge
        if bridge is None:
            return {"status": "not_paired"}
        return {
            "status": bridge.status,
            "repair_required": bridge.repair_required,
            "queued_events": bridge.queued_events,
            "retry_count": bridge.retry_count,
            "dropped_events": bridge.dropped_events,
            "last_sent_at": bridge.last_sent_at,
            "last_received_at": bridge.last_received_at,
            "last_error": bridge.last_error,
        }

    @override
    async def async_added_to_hass(self) -> None:
        """Subscribe to native bridge status changes."""
        await super().async_added_to_hass()
        bridge = self._bridge
        if bridge is not None:
            self.async_on_remove(
                bridge.async_subscribe_status(self._async_status_changed)
            )

    @callback
    def _async_status_changed(self) -> None:
        """Write state after native bridge status changes."""
        self.async_write_ha_state()
