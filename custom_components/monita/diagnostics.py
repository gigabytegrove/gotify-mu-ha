"""Diagnostics support for Monita."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import MonitaConfigEntry
from .const import (
    CONF_APP_TOKEN,
    CONF_CLIENT_TOKEN,
    CONF_NATIVE_SECRET,
    CONF_NATIVE_WEBHOOK_ID,
    CONF_NATIVE_WEBHOOK_URL,
)
from .native import native_pairing_is_configured

TO_REDACT = {
    CONF_APP_TOKEN,
    CONF_CLIENT_TOKEN,
    CONF_NATIVE_SECRET,
    CONF_NATIVE_WEBHOOK_ID,
    CONF_NATIVE_WEBHOOK_URL,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: MonitaConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a Monita config entry."""
    runtime = entry.runtime_data
    active_channel_ids = list(
        getattr(
            runtime,
            "active_channel_ids",
            (
                (runtime.channel_id,)
                if getattr(runtime, "channel_id", None) is not None
                else ()
            ),
        )
    )
    channel_lookup = getattr(runtime, "channel", None)

    def channel_metadata(channel_id: int) -> dict[str, Any]:
        channel = channel_lookup(channel_id) if callable(channel_lookup) else None
        return {
            "id": channel_id,
            "name": channel.name if channel is not None else None,
            "role": channel.role if channel is not None else None,
            "can_post": channel.can_post if channel is not None else False,
        }

    return {
        "entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "runtime": {
            "channel_id": runtime.channel_id,
            "channel_name": runtime.channel_name,
            "selected_channel_ids": active_channel_ids,
            "selected_channels": [
                channel_metadata(channel_id) for channel_id in active_channel_ids
            ],
            "inbound_enabled": runtime.inbound_enabled,
            "stream_connected": runtime.stream_connected,
            "stream_reconnects": runtime.stream_reconnects,
            "last_stream_error": runtime.last_stream_error,
            "native_paired": native_pairing_is_configured(dict(entry.data)),
            "native_bridge": (
                {
                    "status": runtime.native_bridge.status,
                    "repair_required": runtime.native_bridge.repair_required,
                    "queued_events": runtime.native_bridge.queued_events,
                    "retry_count": runtime.native_bridge.retry_count,
                    "dropped_events": runtime.native_bridge.dropped_events,
                    "last_sent_at": runtime.native_bridge.last_sent_at,
                    "last_received_at": runtime.native_bridge.last_received_at,
                    "last_error": runtime.native_bridge.last_error,
                }
                if runtime.native_bridge is not None
                else None
            ),
        },
    }
