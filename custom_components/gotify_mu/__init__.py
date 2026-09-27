"""Monita integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    GotifyMUAuthError,
    GotifyMUClient,
    GotifyMUConnectionError,
    GotifyMUError,
    GotifyMURateLimitError,
)
from .const import (
    CONF_APP_TOKEN,
    CONF_CHANNEL_ID,
    CONF_CHANNEL_NAME,
    CONF_CLIENT_TOKEN,
    CONF_DEFAULT_PRIORITY,
    CONF_INBOUND_ENABLED,
    CONF_NATIVE_EVENT_PATH,
    CONF_NATIVE_SECRET,
    CONF_NATIVE_WEBHOOK_ID,
    CONF_SERVER_URL,
    CONF_VERIFY_SSL,
    DEFAULT_INBOUND_ENABLED,
    DEFAULT_PRIORITY,
    DOMAIN,
    INTEGRATION_ORIGIN_EXTRA,
    PLATFORMS,
    SERVICE_SEND,
    STREAM_RECONNECT_MAX_SECONDS,
)
from .helpers import channel_unique_id, fallback_unique_id
from .media import async_acquire_entity_image, async_acquire_url_image
from .native import GotifyMUNativeBridge, native_pairing_is_configured
from .repairs import async_delete_native_bridge_repair_issue

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("title"): cv.string,
        vol.Optional("priority"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
        vol.Optional("markdown", default=False): cv.boolean,
        vol.Optional("entry_id"): cv.string,
        vol.Exclusive("image_entity", "image_source"): cv.entity_id,
        vol.Exclusive("image_url", "image_source"): cv.string,
        vol.Optional("extras"): dict,
    }
)

MessageCallback = Callable[[dict[str, Any]], None]
StatusCallback = Callable[[], None]


@dataclass(slots=True)
class GotifyMURuntimeData:
    """Runtime data for one Monita config entry."""

    client: GotifyMUClient
    channel_id: int | None
    channel_name: str
    entry_id: str
    inbound_enabled: bool
    native_bridge: GotifyMUNativeBridge | None = None
    stream_connected: bool = False
    stream_reconnects: int = 0
    last_stream_error: str | None = None
    _listeners: set[MessageCallback] = field(default_factory=set)
    _status_listeners: set[StatusCallback] = field(default_factory=set)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    @callback
    def async_subscribe(self, listener: MessageCallback) -> Callable[[], None]:
        """Subscribe to inbound messages."""
        self._listeners.add(listener)

        @callback
        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    @callback
    def async_dispatch_message(self, message: dict[str, Any]) -> None:
        """Dispatch one inbound message to subscribers."""
        for listener in tuple(self._listeners):
            listener(message)

    @callback
    def async_subscribe_status(self, listener: StatusCallback) -> Callable[[], None]:
        """Subscribe to stream connection status changes."""
        self._status_listeners.add(listener)

        @callback
        def remove_listener() -> None:
            self._status_listeners.discard(listener)

        return remove_listener

    @callback
    def async_set_stream_status(
        self, connected: bool, error: str | None = None
    ) -> None:
        """Update stream state and notify status entities."""
        changed = (
            self.stream_connected != connected
            or self.last_stream_error != error
        )
        self.stream_connected = connected
        self.last_stream_error = error
        if changed:
            for listener in tuple(self._status_listeners):
                listener()

    @callback
    def async_stop(self) -> None:
        """Request the stream loop to stop."""
        self._stop_event.set()
        self.async_set_stream_status(False, self.last_stream_error)


GotifyMUConfigEntry = ConfigEntry[GotifyMURuntimeData]


def _message_is_from_this_entry(entry_id: str, message: dict[str, Any]) -> bool:
    """Return True when a streamed message originated from this HA entry."""
    extras = message.get("extras")
    if not isinstance(extras, dict):
        return False
    origin = extras.get(INTEGRATION_ORIGIN_EXTRA)
    return isinstance(origin, dict) and origin.get("entry_id") == entry_id


async def _async_stream_loop(
    hass: HomeAssistant,
    entry: GotifyMUConfigEntry,
) -> None:
    """Maintain the optional realtime Monita stream."""
    runtime = entry.runtime_data
    delay = 1

    @callback
    def stream_connected() -> None:
        runtime.async_set_stream_status(True)

    while not runtime._stop_event.is_set():
        try:
            async for message in runtime.client.async_messages(
                on_connected=stream_connected
            ):
                if runtime._stop_event.is_set():
                    return

                delay = 1

                if runtime.channel_id is not None:
                    try:
                        message_app_id = int(message.get("appid", 0))
                    except (TypeError, ValueError):
                        continue
                    if message_app_id != runtime.channel_id:
                        continue

                # Avoid immediately retriggering an HA automation on the same
                # notification this integration entry just published.
                if _message_is_from_this_entry(entry.entry_id, message):
                    continue

                runtime.async_dispatch_message(message)

            if runtime._stop_event.is_set():
                runtime.async_set_stream_status(False, runtime.last_stream_error)
                return
            runtime.async_set_stream_status(False, "WebSocket stream closed")
        except GotifyMUAuthError as err:
            runtime.async_set_stream_status(False, str(err))
            entry.async_start_reauth(hass)
            return
        except GotifyMURateLimitError as err:
            runtime.stream_reconnects += 1
            runtime.async_set_stream_status(False, str(err))
        except GotifyMUConnectionError as err:
            runtime.stream_reconnects += 1
            runtime.async_set_stream_status(False, str(err))
            _LOGGER.debug(
                "Monita stream disconnected for %s: %s; retrying in %ss",
                entry.title,
                err,
                delay,
            )
        except asyncio.CancelledError:
            raise
        except Exception as err:  # Defensive: isolate stream failures from HA.
            runtime.stream_reconnects += 1
            runtime.async_set_stream_status(False, str(err))
            _LOGGER.exception("Unexpected Monita stream error for %s", entry.title)

        try:
            await asyncio.wait_for(runtime._stop_event.wait(), timeout=delay)
            return
        except TimeoutError:
            delay = min(delay * 2, STREAM_RECONNECT_MAX_SECONDS)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up Monita integration-level actions."""

    async def handle_send(call: ServiceCall) -> None:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("No Monita instances are configured")

        requested = call.data.get("entry_id")
        if requested is None:
            selected = next(
                (item for item in entries if item.state is ConfigEntryState.LOADED),
                None,
            )
        else:
            selected = next(
                (item for item in entries if item.entry_id == requested),
                None,
            )

        if selected is None:
            raise ServiceValidationError(
                "No loaded Monita config entry matches the request"
            )
        if selected.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError("Requested Monita config entry is not loaded")

        typed_entry: GotifyMUConfigEntry = selected
        runtime = typed_entry.runtime_data
        priority = call.data.get(
            "priority",
            selected.options.get(CONF_DEFAULT_PRIORITY, DEFAULT_PRIORITY),
        )

        extras = dict(call.data.get("extras") or {})
        existing_origin = extras.get(INTEGRATION_ORIGIN_EXTRA)
        origin = dict(existing_origin) if isinstance(existing_origin, dict) else {}
        origin.update(
            {
                "entry_id": selected.entry_id,
                "source": "gotify-mu-ha",
            }
        )
        extras[INTEGRATION_ORIGIN_EXTRA] = origin

        try:
            image = None
            if image_entity := call.data.get("image_entity"):
                image = await async_acquire_entity_image(hass, image_entity)
            elif image_url := call.data.get("image_url"):
                image = await async_acquire_url_image(
                    hass,
                    image_url,
                    verify_ssl=selected.data.get(CONF_VERIFY_SSL, True),
                )

            attachment_ids: list[int] | None = None
            if image is not None:
                try:
                    attachment = await runtime.client.async_upload_image(
                        image.content,
                        filename=image.filename,
                        content_type=image.content_type,
                    )
                except GotifyMUAuthError:
                    raise
                except GotifyMURateLimitError as err:
                    raise HomeAssistantError(
                        "Monita rate limited the image upload"
                    ) from err
                except GotifyMUConnectionError as err:
                    raise HomeAssistantError(
                        "Could not connect to Monita media endpoint"
                    ) from err
                except GotifyMUError as err:
                    raise HomeAssistantError(
                        f"Monita rejected the image: {err}"
                    ) from err
                attachment_ids = [attachment.id]

            send_kwargs: dict[str, Any] = {
                "title": call.data.get("title"),
                "priority": priority,
                "markdown": call.data.get("markdown", False),
                "extras": extras,
            }
            if attachment_ids is not None:
                send_kwargs["attachment_ids"] = attachment_ids

            await runtime.client.async_send(
                call.data["message"],
                **send_kwargs,
            )
        except GotifyMUAuthError as err:
            selected.async_start_reauth(hass)
            raise HomeAssistantError("Monita rejected the application token") from err
        except GotifyMURateLimitError as err:
            raise HomeAssistantError("Monita rate limited the notification") from err
        except GotifyMUConnectionError as err:
            raise HomeAssistantError(f"Could not connect to Monita: {err}") from err
        except GotifyMUError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND,
        handle_send,
        schema=SERVICE_SCHEMA,
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy config entries to the stable v2 data model."""
    if entry.version > 2:
        return False
    if entry.version == 2:
        return True

    data = dict(entry.data)
    server_url = data[CONF_SERVER_URL].rstrip("/")
    data[CONF_SERVER_URL] = server_url

    if channel_id := data.get(CONF_CHANNEL_ID):
        unique_id = channel_unique_id(server_url, int(channel_id))
    else:
        unique_id = fallback_unique_id(server_url, data[CONF_APP_TOKEN])

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        unique_id=unique_id,
        version=2,
        minor_version=0,
    )
    _LOGGER.info("Migrated Monita config entry %s to version 2", entry.title)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GotifyMUConfigEntry) -> bool:
    """Set up Monita from a config entry."""
    client = GotifyMUClient(
        async_get_clientsession(hass),
        entry.data[CONF_SERVER_URL],
        entry.data[CONF_APP_TOKEN],
        entry.data.get(CONF_VERIFY_SSL, True),
        entry.data.get(CONF_CLIENT_TOKEN),
    )

    try:
        await client.async_health()
        application = await client.async_validate_application_token()
        channels = []
        if entry.data.get(CONF_CLIENT_TOKEN):
            await client.async_validate_client_token()
            channels = await client.async_get_channels()
    except GotifyMUAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (GotifyMUConnectionError, GotifyMURateLimitError) as err:
        raise ConfigEntryNotReady(str(err)) from err
    except GotifyMUError as err:
        raise ConfigEntryNotReady(str(err)) from err

    data = dict(entry.data)
    configured_channel_id = data.get(CONF_CHANNEL_ID)
    if application is not None:
        if configured_channel_id is not None and application.id != configured_channel_id:
            raise ConfigEntryAuthFailed(
                "The application token belongs to a different Monita Channel"
            )
        configured_channel_id = application.id
        data[CONF_CHANNEL_ID] = application.id
        data.setdefault(CONF_CHANNEL_NAME, application.name)

    if configured_channel_id is not None and entry.data.get(CONF_CLIENT_TOKEN):
        if not any(channel.id == configured_channel_id for channel in channels):
            raise ConfigEntryAuthFailed(
                "The configured Monita client token cannot access this Channel"
            )

    if data != dict(entry.data):
        hass.config_entries.async_update_entry(entry, data=data)

    runtime = GotifyMURuntimeData(
        client=client,
        channel_id=configured_channel_id,
        channel_name=data.get(CONF_CHANNEL_NAME, entry.title),
        entry_id=entry.entry_id,
        inbound_enabled=bool(
            data.get(CONF_CLIENT_TOKEN)
            and entry.options.get(CONF_INBOUND_ENABLED, DEFAULT_INBOUND_ENABLED)
        ),
    )
    entry.runtime_data = runtime
    entry.async_on_unload(runtime.async_stop)

    if native_pairing_is_configured(data):
        native_bridge = GotifyMUNativeBridge(
            hass,
            async_get_clientsession(hass),
            name=runtime.channel_name,
            server_url=data[CONF_SERVER_URL],
            verify_ssl=data.get(CONF_VERIFY_SSL, True),
            secret=data[CONF_NATIVE_SECRET],
            event_path=data[CONF_NATIVE_EVENT_PATH],
            webhook_id=data[CONF_NATIVE_WEBHOOK_ID],
            entry_id=entry.entry_id,
        )
        runtime.native_bridge = native_bridge
        native_bridge.async_start()
        entry.async_on_unload(native_bridge.async_stop)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if runtime.inbound_enabled:
        entry.async_create_background_task(
            hass,
            _async_stream_loop(hass, entry),
            f"Monita stream: {entry.title}",
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: GotifyMUConfigEntry) -> bool:
    """Unload a Monita config entry."""
    entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(
    hass: HomeAssistant, entry: GotifyMUConfigEntry
) -> None:
    """Clean up repair issues when a Monita entry is removed."""
    async_delete_native_bridge_repair_issue(hass, entry.entry_id)
