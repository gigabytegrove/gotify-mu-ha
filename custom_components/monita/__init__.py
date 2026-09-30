"""Monita integration."""

from __future__ import annotations

import asyncio
import logging
import re
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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_set_service_schema

from .api import (
    MonitaAuthError,
    MonitaChannel,
    MonitaClient,
    MonitaConnectionError,
    MonitaError,
    MonitaRateLimitError,
)
from .const import (
    CONF_APP_TOKEN,
    CONF_CHANNEL_ID,
    CONF_CHANNEL_IDS,
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
    LEGACY_INTEGRATION_ORIGIN_EXTRA,
    LEGACY_SERVICE_DOMAIN,
    PLATFORMS,
    SERVICE_DOMAIN,
    SERVICE_SEND,
    STREAM_RECONNECT_MAX_SECONDS,
)
from .helpers import channel_unique_id, fallback_unique_id
from .media import async_acquire_entity_image, async_acquire_url_image
from .native import MonitaNativeBridge, native_pairing_is_configured
from .repairs import async_delete_native_bridge_repair_issue

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

MESSAGE_CONTROL_VALUES = ("assign", "resolve", "attach")

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("title"): cv.string,
        vol.Optional("priority"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
        vol.Optional("markdown", default=False): cv.boolean,
        vol.Optional("channel"): cv.entity_id,
        vol.Optional("channel_id"): vol.Coerce(int),
        vol.Optional("entry_id"): cv.string,
        vol.Exclusive("image_entity", "image_source"): cv.entity_id,
        vol.Exclusive("image_url", "image_source"): cv.string,
        vol.Optional("controls", default=[]): vol.All(
            cv.ensure_list,
            [vol.In(MESSAGE_CONTROL_VALUES)],
        ),
        vol.Optional("extras"): dict,
    }
)

MONITA_SEND_DESCRIPTION: dict[str, Any] = {
    "name": "Send to Monita Channel",
    "description": "Send a notification, message, or image to a selected Monita Channel.",
    "fields": {
        "channel": {
            "name": "Channel",
            "description": "Choose the Monita Channel that should receive this message.",
            "required": False,
            "selector": {
                "entity": {
                    "domain": "notify",
                    "integration": DOMAIN,
                }
            },
        },
        "title": {
            "name": "Title",
            "required": False,
            "selector": {"text": {}},
        },
        "message": {
            "name": "Message",
            "required": True,
            "selector": {"text": {"multiline": True}},
        },
        "priority": {
            "name": "Priority",
            "description": "Monita priority from 0 through 10.",
            "required": False,
            "selector": {
                "number": {
                    "min": 0,
                    "max": 10,
                    "step": 1,
                    "mode": "slider",
                }
            },
        },
        "markdown": {
            "name": "Markdown",
            "description": "Render the message as Markdown on supported Monita clients.",
            "required": False,
            "default": False,
            "selector": {"boolean": {}},
        },
        "image_entity": {
            "name": "Image entity",
            "description": (
                "Capture a current Home Assistant camera/image and send the bytes "
                "to the selected Monita Channel."
            ),
            "required": False,
            "selector": {"entity": {"domain": ["camera", "image"]}},
        },
        "image_url": {
            "name": "Image URL",
            "description": (
                "Download an HTTP/HTTPS JPEG, PNG, GIF, or WebP through Home Assistant "
                "and send it to Monita."
            ),
            "required": False,
            "selector": {"text": {"type": "url"}},
        },
        "controls": {
            "name": "Message controls",
            "description": (
                "Choose which collaboration controls this message exposes in Monita. "
                "Leave empty for a normal notification."
            ),
            "required": False,
            "default": [],
            "selector": {
                "select": {
                    "multiple": True,
                    "options": [
                        {"value": "assign", "label": "Assign to Me"},
                        {"value": "resolve", "label": "Resolve"},
                        {"value": "attach", "label": "Attach"},
                    ],
                }
            },
        },
        "extras": {
            "name": "Monita extras",
            "description": "Optional advanced Monita message extras.",
            "required": False,
            "selector": {"object": {}},
        },
    },
}

MessageCallback = Callable[[dict[str, Any]], None]
StatusCallback = Callable[[], None]
_CHANNEL_NOTIFY_UNIQUE_ID = re.compile(r"_channel_(\d+)_notify$")


@dataclass(slots=True)
class MonitaRuntimeData:
    """Runtime data for one Monita server/config entry."""

    client: MonitaClient
    channel_id: int | None
    channel_name: str
    entry_id: str
    inbound_enabled: bool
    channels: dict[int, MonitaChannel] = field(default_factory=dict)
    selected_channel_ids: tuple[int, ...] = ()
    capabilities: dict[str, Any] = field(default_factory=dict)
    native_bridge: MonitaNativeBridge | None = None
    stream_connected: bool = False
    stream_reconnects: int = 0
    last_stream_error: str | None = None
    _listeners: set[MessageCallback] = field(default_factory=set)
    _status_listeners: set[StatusCallback] = field(default_factory=set)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def active_channel_ids(self) -> tuple[int, ...]:
        """Return the Channels this entry exposes to Home Assistant."""
        if self.selected_channel_ids:
            return self.selected_channel_ids
        if self.channel_id is not None:
            return (self.channel_id,)
        return ()

    def channel(self, channel_id: int) -> MonitaChannel | None:
        """Return metadata for one selected Channel."""
        return self.channels.get(channel_id)

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


MonitaConfigEntry = ConfigEntry[MonitaRuntimeData]


def _message_is_from_this_entry(entry_id: str, message: dict[str, Any]) -> bool:
    """Return True when a streamed message originated from this HA entry."""
    extras = message.get("extras")
    if not isinstance(extras, dict):
        return False
    for key in (INTEGRATION_ORIGIN_EXTRA, LEGACY_INTEGRATION_ORIGIN_EXTRA):
        origin = extras.get(key)
        if isinstance(origin, dict) and origin.get("entry_id") == entry_id:
            return True
    return False


def _channel_id_from_notify_unique_id(
    runtime: MonitaRuntimeData,
    unique_id: str,
) -> int | None:
    """Resolve a Monita Channel from one notification entity unique ID."""
    match = _CHANNEL_NOTIFY_UNIQUE_ID.search(unique_id)
    if match:
        return int(match.group(1))
    if unique_id.endswith("_notify"):
        return runtime.channel_id
    return None


def _resolve_push_target(
    hass: HomeAssistant,
    call: ServiceCall,
) -> tuple[MonitaConfigEntry, int]:
    """Resolve the selected server entry and destination Channel."""
    candidate_domains = tuple(dict.fromkeys((DOMAIN, SERVICE_DOMAIN, LEGACY_SERVICE_DOMAIN)))
    loaded_by_id: dict[str, MonitaConfigEntry] = {}
    for candidate_domain in candidate_domains:
        for entry in hass.config_entries.async_entries(candidate_domain):
            if entry.state is ConfigEntryState.LOADED:
                loaded_by_id.setdefault(entry.entry_id, entry)
    loaded = list(loaded_by_id.values())
    if not loaded:
        raise ServiceValidationError("No loaded Monita server is configured")

    channel_entity = call.data.get("channel")
    requested_entry_id = call.data.get("entry_id")
    requested_channel_id = call.data.get("channel_id")

    selected: MonitaConfigEntry | None = None
    target_channel_id: int | None = None

    if channel_entity:
        registry_entry = er.async_get(hass).async_get(channel_entity)
        if (
            registry_entry is None
            or registry_entry.platform not in candidate_domains
            or registry_entry.domain != "notify"
            or not registry_entry.config_entry_id
        ):
            raise ServiceValidationError(
                "Choose a Monita notification entity for Channel"
            )
        selected = next(
            (
                entry
                for entry in loaded
                if entry.entry_id == registry_entry.config_entry_id
            ),
            None,
        )
        if selected is None:
            raise ServiceValidationError(
                "The selected Monita Channel is not currently loaded"
            )
        target_channel_id = _channel_id_from_notify_unique_id(
            selected.runtime_data,
            registry_entry.unique_id,
        )

    if selected is None and requested_entry_id:
        selected = next(
            (entry for entry in loaded if entry.entry_id == requested_entry_id),
            None,
        )
        if selected is None:
            raise ServiceValidationError(
                "No loaded Monita config entry matches the request"
            )

    if selected is None:
        if len(loaded) != 1:
            raise ServiceValidationError(
                "Choose a Monita Channel when more than one server is configured"
            )
        selected = loaded[0]

    if target_channel_id is None and requested_channel_id is not None:
        target_channel_id = int(requested_channel_id)

    runtime = selected.runtime_data
    active = getattr(runtime, "active_channel_ids", None)
    if active is None:
        legacy_channel_id = getattr(runtime, "channel_id", None)
        active = (legacy_channel_id,) if legacy_channel_id is not None else ()
    if target_channel_id is None:
        if len(active) != 1:
            raise ServiceValidationError(
                "Choose a Monita Channel for this Push Message action"
            )
        target_channel_id = active[0]

    if target_channel_id not in active:
        raise ServiceValidationError(
            "The selected Channel is not enabled for this Monita server"
        )

    return selected, target_channel_id


async def _async_stream_loop(
    hass: HomeAssistant,
    entry: MonitaConfigEntry,
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
                try:
                    message_app_id = int(message.get("appid", 0))
                except (TypeError, ValueError):
                    continue
                if (
                    runtime.active_channel_ids
                    and message_app_id not in runtime.active_channel_ids
                ):
                    continue

                if _message_is_from_this_entry(entry.entry_id, message):
                    continue

                runtime.async_dispatch_message(message)

            if runtime._stop_event.is_set():
                runtime.async_set_stream_status(False, runtime.last_stream_error)
                return
            runtime.async_set_stream_status(False, "WebSocket stream closed")
        except MonitaAuthError as err:
            runtime.async_set_stream_status(False, str(err))
            entry.async_start_reauth(hass)
            return
        except MonitaRateLimitError as err:
            runtime.stream_reconnects += 1
            runtime.async_set_stream_status(False, str(err))
        except MonitaConnectionError as err:
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
        selected, target_channel_id = _resolve_push_target(hass, call)
        runtime = selected.runtime_data
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
                "channel_id": target_channel_id,
                "source": "monita-ha",
            }
        )
        extras[INTEGRATION_ORIGIN_EXTRA] = origin

        controls = [
            value
            for value in call.data.get("controls", [])
            if value in MESSAGE_CONTROL_VALUES
        ]
        if controls:
            extras["monita::controls"] = controls
        else:
            extras.pop("monita::controls", None)

        use_client_route = bool(runtime.client.client_token)
        legacy_image_route = bool(
            runtime.client.app_token
            and runtime.channel_id is not None
            and target_channel_id == runtime.channel_id
        )

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
                if use_client_route and not legacy_image_route:
                    channel = runtime.channel(target_channel_id)
                    features = getattr(runtime, "capabilities", {}).get(
                        "features", {}
                    )
                    channel_type = (
                        channel.channel_type
                        if channel is not None and channel.channel_type
                        else "notification"
                    )
                    direct_images_supported = bool(
                        isinstance(features, dict)
                        and (
                            (
                                channel_type == "chat"
                                and features.get("chatImages") is True
                            )
                            or (
                                channel_type != "chat"
                                and features.get("notificationImages") is True
                            )
                        )
                    )

                    # Capabilities are normally loaded with the config entry, but
                    # the Monita server may have been upgraded without reloading
                    # Home Assistant. Refresh once before dropping an image so a
                    # newly upgraded server can accept it immediately.
                    if not direct_images_supported:
                        refreshed = await runtime.client.async_capabilities()
                        if isinstance(refreshed, dict):
                            runtime.capabilities = refreshed
                            features = refreshed.get("features", {})
                            direct_images_supported = bool(
                                isinstance(features, dict)
                                and (
                                    (
                                        channel_type == "chat"
                                        and features.get("chatImages") is True
                                    )
                                    or (
                                        channel_type != "chat"
                                        and features.get("notificationImages") is True
                                    )
                                )
                            )

                    if direct_images_supported:
                        direct_extras = dict(extras)
                        if call.data.get("markdown", False):
                            direct_extras.setdefault(
                                "client::display",
                                {"contentType": "text/markdown"},
                            )
                        await runtime.client.async_send_chat_image(
                            call.data["message"],
                            channel_id=target_channel_id,
                            image=image.content,
                            filename=image.filename,
                            content_type=image.content_type,
                            title=call.data.get("title"),
                            priority=priority,
                            extras=direct_extras,
                        )
                        return

                    # Never lose an urgent notification just because an older
                    # Monita server cannot accept images on this Channel type.
                    # The text notification is still delivered. Monita 1.1.9+
                    # advertises notificationImages and receives the snapshot.
                    _LOGGER.warning(
                        "Monita Channel %s does not advertise direct image support; "
                        "sending the notification text without the requested image",
                        target_channel_id,
                    )
                    image = None

                if image is not None:
                    try:
                        attachment = await runtime.client.async_upload_image(
                            image.content,
                            filename=image.filename,
                            content_type=image.content_type,
                        )
                    except MonitaAuthError:
                        raise
                    except MonitaRateLimitError as err:
                        raise HomeAssistantError(
                            "Monita rate limited the image upload"
                        ) from err
                    except MonitaConnectionError as err:
                        raise HomeAssistantError(
                            "Could not connect to Monita media endpoint"
                        ) from err
                    except MonitaError as err:
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

            if use_client_route and not legacy_image_route:
                send_kwargs["channel_id"] = target_channel_id

            await runtime.client.async_send(
                call.data["message"],
                **send_kwargs,
            )
        except MonitaAuthError as err:
            selected.async_start_reauth(hass)
            raise HomeAssistantError("Monita rejected the configured credential") from err
        except MonitaRateLimitError as err:
            raise HomeAssistantError("Monita rate limited the notification") from err
        except MonitaConnectionError as err:
            raise HomeAssistantError(f"Could not connect to Monita: {err}") from err
        except MonitaError as err:
            raise HomeAssistantError(str(err)) from err

    # Monita is the canonical user-facing service namespace. The historical
    # integration domain remains registered as a compatibility alias so
    # existing automations keep working during the transition.
    for service_domain in (SERVICE_DOMAIN, LEGACY_SERVICE_DOMAIN):
        if not hass.services.has_service(service_domain, SERVICE_SEND):
            hass.services.async_register(
                service_domain,
                SERVICE_SEND,
                handle_send,
                schema=SERVICE_SCHEMA,
            )

    # The canonical Monita action lives outside the historical config-entry
    # domain, so register its frontend description explicitly. This keeps the
    # automation editor fully native: Channel picker, title, priority, image
    # entity, and the rest of the Monita fields all render under monita.send.
    async_set_service_schema(
        hass,
        SERVICE_DOMAIN,
        SERVICE_SEND,
        MONITA_SEND_DESCRIPTION,
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy per-Channel entries without breaking their identities."""
    if entry.version > 3:
        return False

    data = dict(entry.data)
    options = dict(entry.options)

    if entry.version < 2:
        server_url = data[CONF_SERVER_URL].rstrip("/")
        data[CONF_SERVER_URL] = server_url
        if channel_id := data.get(CONF_CHANNEL_ID):
            unique_id = channel_unique_id(server_url, int(channel_id))
        else:
            unique_id = fallback_unique_id(server_url, data[CONF_APP_TOKEN])
    else:
        unique_id = entry.unique_id

    if entry.version < 3 and data.get(CONF_CHANNEL_ID) is not None:
        options.setdefault(CONF_CHANNEL_IDS, [int(data[CONF_CHANNEL_ID])])

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        unique_id=unique_id,
        version=3,
        minor_version=0,
    )
    _LOGGER.info("Migrated Monita config entry %s to version 3", entry.title)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MonitaConfigEntry) -> bool:
    """Set up one Monita server or legacy Channel entry."""
    app_token = entry.data.get(CONF_APP_TOKEN, "")
    client_token = entry.data.get(CONF_CLIENT_TOKEN)
    client = MonitaClient(
        async_get_clientsession(hass),
        entry.data[CONF_SERVER_URL],
        app_token,
        entry.data.get(CONF_VERIFY_SSL, True),
        client_token,
    )

    try:
        await client.async_health()
        application: MonitaChannel | None = None
        if app_token:
            application = await client.async_validate_application_token()

        channels: list[MonitaChannel] = []
        capabilities: dict[str, Any] = {}
        if client_token:
            await client.async_validate_client_token()
            channels = await client.async_get_channels()
            capabilities = await client.async_capabilities()
    except MonitaAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (MonitaConnectionError, MonitaRateLimitError) as err:
        raise ConfigEntryNotReady(str(err)) from err
    except MonitaError as err:
        raise ConfigEntryNotReady(str(err)) from err

    data = dict(entry.data)
    configured_channel_id = data.get(CONF_CHANNEL_ID)
    by_id = {channel.id: channel for channel in channels}

    if application is not None:
        if (
            configured_channel_id is not None
            and application.id != int(configured_channel_id)
        ):
            raise ConfigEntryAuthFailed(
                "The application token belongs to a different Monita Channel"
            )
        configured_channel_id = application.id
        data[CONF_CHANNEL_ID] = application.id
        data.setdefault(CONF_CHANNEL_NAME, application.name)
        by_id.setdefault(application.id, application)

    has_selected_option = CONF_CHANNEL_IDS in entry.options
    selected_raw = entry.options.get(CONF_CHANNEL_IDS, [])
    selected = [int(value) for value in selected_raw]

    if not selected and not has_selected_option and configured_channel_id is not None:
        selected = [int(configured_channel_id)]
    if client_token:
        selected = [channel_id for channel_id in selected if channel_id in by_id]
    if not selected and not has_selected_option and application is not None:
        selected = [application.id]

    if not selected:
        raise ConfigEntryNotReady(
            "None of the selected Monita Channels are currently accessible; "
            "update Manage Channels"
        )

    primary_channel_id = (
        int(configured_channel_id)
        if configured_channel_id is not None
        and int(configured_channel_id) in selected
        else selected[0]
    )
    primary = by_id.get(primary_channel_id)
    primary_name = (
        primary.name
        if primary is not None
        else data.get(CONF_CHANNEL_NAME, entry.title)
    )

    if data != dict(entry.data):
        hass.config_entries.async_update_entry(entry, data=data)

    runtime = MonitaRuntimeData(
        client=client,
        channel_id=primary_channel_id,
        channel_name=primary_name,
        entry_id=entry.entry_id,
        inbound_enabled=bool(
            client_token
            and entry.options.get(CONF_INBOUND_ENABLED, DEFAULT_INBOUND_ENABLED)
        ),
        channels=by_id,
        selected_channel_ids=tuple(selected),
        capabilities=capabilities,
    )
    entry.runtime_data = runtime
    entry.async_on_unload(runtime.async_stop)

    if native_pairing_is_configured(data):
        native_bridge = MonitaNativeBridge(
            hass,
            async_get_clientsession(hass),
            name=entry.title,
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


async def async_unload_entry(hass: HomeAssistant, entry: MonitaConfigEntry) -> bool:
    """Unload a Monita config entry."""
    entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(
    hass: HomeAssistant, entry: MonitaConfigEntry
) -> None:
    """Clean up repair issues when a Monita entry is removed."""
    async_delete_native_bridge_repair_issue(hass, entry.entry_id)
