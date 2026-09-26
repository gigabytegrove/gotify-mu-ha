"""Diagnostics support for Gotify MU."""

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
    """Return diagnostics for a Gotify MU config entry."""
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
            "inbound_enabled": runtime.inbound_enabled,
            "stream_connected": runtime.stream_connected,
            "stream_reconnects": runtime.stream_reconnects,
            "last_stream_error": runtime.last_stream_error,
            "native_paired": native_pairing_is_configured(dict(entry.data)),
        },
    }
