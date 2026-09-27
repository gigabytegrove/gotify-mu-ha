"""Diagnostics support for Monita."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import GotifyMUConfigEntry
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
    entry: GotifyMUConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a Monita config entry."""
    runtime = entry.runtime_data
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
            "selected_channel_ids": list(runtime.active_channel_ids),
            "selected_channels": [
                {
                    "id": channel_id,
                    "name": (
                        runtime.channel(channel_id).name
                        if runtime.channel(channel_id) is not None
                        else None
                    ),
                    "role": (
                        runtime.channel(channel_id).role
                        if runtime.channel(channel_id) is not None
                        else None
                    ),
                    "can_post": (
                        runtime.channel(channel_id).can_post
                        if runtime.channel(channel_id) is not None
                        else False
                    ),
                }
                for channel_id in runtime.active_channel_ids
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
