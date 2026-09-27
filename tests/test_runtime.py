"""Regression tests for Gotify MU runtime entities and services."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from custom_components.gotify_mu import (
    GotifyMURuntimeData,
    _async_stream_loop,
    async_setup,
)
from custom_components.gotify_mu.api import (
    GotifyMUAttachment,
    GotifyMUAuthError,
    GotifyMUConnectionError,
    GotifyMUError,
)
from custom_components.gotify_mu.binary_sensor import (
    GotifyMUConnectionBinarySensor,
    GotifyMUNativeBridgeBinarySensor,
)
from custom_components.gotify_mu.const import (
    CONF_DEFAULT_PRIORITY,
    CONF_SERVER_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
    EVENT_TYPE_MESSAGE,
    INTEGRATION_ORIGIN_EXTRA,
    SERVICE_SEND,
)
from custom_components.gotify_mu.event import GotifyMUMessageEventEntity
from custom_components.gotify_mu.media import GotifyMUImage
from custom_components.gotify_mu.notify import GotifyMUNotifyEntity

SERVER = "http://gotify-mu.local:8080"
ENTRY_ID = "entry-runtime-test"
UNIQUE_ID = f"{SERVER}|channel:7"


def _entry(runtime, *, options=None):
    return SimpleNamespace(
        runtime_data=runtime,
        unique_id=UNIQUE_ID,
        entry_id=ENTRY_ID,
        title="Home Assistant",
        data={CONF_SERVER_URL: SERVER},
        options=options or {},
        state=ConfigEntryState.LOADED,
        async_start_reauth=MagicMock(),
    )


async def test_notify_entity_sends_with_default_priority_and_origin():
    """Notify entity publishes through the configured application client."""
    client = SimpleNamespace(async_send=AsyncMock(return_value={"id": 1}))
    runtime = SimpleNamespace(client=client, channel_name="Home Assistant")
    entry = _entry(runtime, options={CONF_DEFAULT_PRIORITY: 8})
    entity = GotifyMUNotifyEntity(entry)

    await entity.async_send_message("Door opened", title="Home")

    client.async_send.assert_awaited_once_with(
        "Door opened",
        title="Home",
        priority=8,
        extras={
            INTEGRATION_ORIGIN_EXTRA: {
                "entry_id": ENTRY_ID,
                "source": "gotify-mu-ha",
            }
        },
    )


async def test_send_service_supports_priority_markdown_and_entry_selection(hass):
    """gotify_mu.send preserves Gotify-specific send controls."""
    client = SimpleNamespace(async_send=AsyncMock(return_value={"id": 2}))
    runtime = SimpleNamespace(client=client)
    entry = _entry(runtime)

    with patch.object(
        hass.config_entries, "async_entries", return_value=[entry]
    ):
        assert await async_setup(hass, {})
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "title": "Alert",
                "message": "**High temperature**",
                "priority": 9,
                "markdown": True,
            },
            blocking=True,
        )

    client.async_send.assert_awaited_once_with(
        "**High temperature**",
        title="Alert",
        priority=9,
        markdown=True,
        extras={
            INTEGRATION_ORIGIN_EXTRA: {
                "entry_id": ENTRY_ID,
                "source": "gotify-mu-ha",
            }
        },
    )


async def test_stream_filters_other_channels_and_self_origin(hass):
    """Inbound stream dispatches only external messages for the configured channel."""
    messages = [
        {"id": 1, "appid": 8, "message": "Wrong channel"},
        {
            "id": 2,
            "appid": 7,
            "message": "Loopback",
            "extras": {
                INTEGRATION_ORIGIN_EXTRA: {
                    "entry_id": ENTRY_ID,
                    "source": "gotify-mu-ha",
                }
            },
        },
        {"id": 3, "appid": 7, "message": "External"},
    ]

    class FakeStreamClient:
        async def async_messages(self, *, on_connected=None):
            if on_connected is not None:
                on_connected()
            for message in messages:
                yield message

    runtime = GotifyMURuntimeData(
        client=FakeStreamClient(),
        channel_id=7,
        channel_name="Home Assistant",
        entry_id=ENTRY_ID,
        inbound_enabled=True,
    )
    received = []

    def receive(message):
        received.append(message)
        runtime.async_stop()

    runtime.async_subscribe(receive)
    entry = _entry(runtime)

    await _async_stream_loop(hass, entry)

    assert received == [{"id": 3, "appid": 7, "message": "External"}]
    assert runtime.stream_connected is False


def test_event_entity_maps_inbound_message_fields():
    """Inbound Gotify messages are exposed as structured event entity data."""
    runtime = SimpleNamespace(channel_name="Home Assistant")
    entity = GotifyMUMessageEventEntity(_entry(runtime))
    message = {
        "id": 42,
        "appid": 7,
        "title": "Door",
        "message": "Opened",
        "priority": 6,
        "date": "2026-09-26T23:00:00Z",
        "senderUserId": 3,
        "senderName": "Jennifer",
        "extras": {"source": "test"},
    }

    with (
        patch.object(entity, "_trigger_event") as trigger,
        patch.object(entity, "async_write_ha_state") as write_state,
    ):
        entity._async_handle_message(message)

    trigger.assert_called_once_with(
        EVENT_TYPE_MESSAGE,
        {
            "message_id": 42,
            "channel_id": 7,
            "title": "Door",
            "message": "Opened",
            "priority": 6,
            "date": "2026-09-26T23:00:00Z",
            "sender_user_id": 3,
            "sender_name": "Jennifer",
            "extras": {"source": "test"},
        },
    )
    write_state.assert_called_once_with()


def test_connection_binary_sensors_expose_runtime_health():
    """Connection sensors expose inbound and native bridge health."""
    bridge = SimpleNamespace(
        is_connected=False,
        status="repair_required",
        repair_required=True,
        queued_events=2,
        retry_count=3,
        dropped_events=4,
        last_sent_at=None,
        last_received_at=None,
        last_error="Rejected credential",
    )
    runtime = SimpleNamespace(
        channel_name="Home Assistant",
        stream_connected=True,
        stream_reconnects=5,
        last_stream_error=None,
        native_bridge=bridge,
    )
    entry = _entry(runtime)

    inbound = GotifyMUConnectionBinarySensor(entry)
    native = GotifyMUNativeBridgeBinarySensor(entry)

    assert inbound.is_on is True
    assert inbound.extra_state_attributes == {
        "reconnects": 5,
        "last_error": None,
    }
    assert native.is_on is False
    assert native.extra_state_attributes == {
        "status": "repair_required",
        "repair_required": True,
        "queued_events": 2,
        "retry_count": 3,
        "dropped_events": 4,
        "last_sent_at": None,
        "last_received_at": None,
        "last_error": "Rejected credential",
    }


async def test_send_service_stages_image_and_preserves_message_controls(hass):
    """Image sends stage bytes first and preserve extras, priority, and Markdown."""
    image = GotifyMUImage(
        content=b"\xff\xd8\xff\xe0jpeg",
        filename="front-door-20260927-090612.jpg",
        content_type="image/jpeg",
    )
    attachment = GotifyMUAttachment(
        id=123,
        filename=image.filename,
        content_type=image.content_type,
        size=len(image.content),
    )
    client = SimpleNamespace(
        async_upload_image=AsyncMock(return_value=attachment),
        async_send=AsyncMock(return_value={"id": 3}),
    )
    runtime = SimpleNamespace(client=client)
    entry = _entry(runtime)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_entity_image",
            new=AsyncMock(return_value=image),
        ) as acquire,
    ):
        assert await async_setup(hass, {})
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "title": "Front Door",
                "message": "**Person detected**",
                "priority": 9,
                "markdown": True,
                "image_entity": "camera.front_door",
                "extras": {
                    "custom::extra": {"value": 1},
                    INTEGRATION_ORIGIN_EXTRA: {"existing": "preserved"},
                },
            },
            blocking=True,
        )

    acquire.assert_awaited_once_with(hass, "camera.front_door")
    client.async_upload_image.assert_awaited_once_with(
        image.content,
        filename=image.filename,
        content_type=image.content_type,
    )
    client.async_send.assert_awaited_once_with(
        "**Person detected**",
        title="Front Door",
        priority=9,
        markdown=True,
        extras={
            "custom::extra": {"value": 1},
            INTEGRATION_ORIGIN_EXTRA: {
                "existing": "preserved",
                "entry_id": ENTRY_ID,
                "source": "gotify-mu-ha",
            },
        },
        attachment_ids=[123],
    )


async def test_image_upload_failure_prevents_message_send(hass):
    """A requested image can never silently degrade to a text-only message."""
    image = GotifyMUImage(
        content=b"\xff\xd8\xff\xe0jpeg",
        filename="front-door.jpg",
        content_type="image/jpeg",
    )
    client = SimpleNamespace(
        async_upload_image=AsyncMock(side_effect=GotifyMUError("upload rejected")),
        async_send=AsyncMock(),
    )
    runtime = SimpleNamespace(client=client)
    entry = _entry(runtime)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_entity_image",
            new=AsyncMock(return_value=image),
        ),
        pytest.raises(HomeAssistantError, match="Gotify MU rejected the image"),
    ):
        assert await async_setup(hass, {})
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "message": "Person detected",
                "image_entity": "camera.front_door",
            },
            blocking=True,
        )

    client.async_send.assert_not_awaited()


async def test_image_upload_auth_failure_starts_reauth(hass):
    """An app-token rejection during staging starts the normal reauth flow."""
    image = GotifyMUImage(
        content=b"\xff\xd8\xff\xe0jpeg",
        filename="front-door.jpg",
        content_type="image/jpeg",
    )
    client = SimpleNamespace(
        async_upload_image=AsyncMock(side_effect=GotifyMUAuthError("rejected")),
        async_send=AsyncMock(),
    )
    runtime = SimpleNamespace(client=client)
    entry = _entry(runtime)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_entity_image",
            new=AsyncMock(return_value=image),
        ),
        pytest.raises(HomeAssistantError, match="application token"),
    ):
        assert await async_setup(hass, {})
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "message": "Person detected",
                "image_entity": "camera.front_door",
            },
            blocking=True,
        )

    entry.async_start_reauth.assert_called_once_with(hass)
    client.async_send.assert_not_awaited()


async def test_message_failure_after_staging_leaves_server_orphan_for_expiry(hass):
    """A staged image is not destructively cleaned up when message creation fails."""
    image = GotifyMUImage(
        content=b"\xff\xd8\xff\xe0jpeg",
        filename="front-door.jpg",
        content_type="image/jpeg",
    )
    attachment = GotifyMUAttachment(
        id=321,
        filename=image.filename,
        content_type=image.content_type,
        size=len(image.content),
    )
    client = SimpleNamespace(
        async_upload_image=AsyncMock(return_value=attachment),
        async_send=AsyncMock(side_effect=GotifyMUConnectionError("offline")),
        async_delete_attachment=AsyncMock(),
    )
    runtime = SimpleNamespace(client=client)
    entry = _entry(runtime)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_entity_image",
            new=AsyncMock(return_value=image),
        ),
        pytest.raises(HomeAssistantError, match="Could not connect to Gotify MU"),
    ):
        assert await async_setup(hass, {})
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "message": "Person detected",
                "image_entity": "camera.front_door",
            },
            blocking=True,
        )

    client.async_upload_image.assert_awaited_once()
    client.async_send.assert_awaited_once()
    client.async_delete_attachment.assert_not_awaited()


async def test_image_url_honors_entry_tls_setting(hass):
    """Advanced URL retrieval uses the configured TLS verification behavior."""
    image = GotifyMUImage(
        content=b"\xff\xd8\xff\xe0jpeg",
        filename="remote-image.jpg",
        content_type="image/jpeg",
    )
    attachment = GotifyMUAttachment(
        id=444,
        filename=image.filename,
        content_type=image.content_type,
        size=len(image.content),
    )
    client = SimpleNamespace(
        async_upload_image=AsyncMock(return_value=attachment),
        async_send=AsyncMock(return_value={"id": 4}),
    )
    runtime = SimpleNamespace(client=client)
    entry = _entry(runtime)
    entry.data[CONF_VERIFY_SSL] = False

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_url_image",
            new=AsyncMock(return_value=image),
        ) as acquire,
    ):
        assert await async_setup(hass, {})
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "message": "Person detected",
                "image_url": "https://camera.example.test/current.jpg?token=secret",
            },
            blocking=True,
        )

    acquire.assert_awaited_once_with(
        hass,
        "https://camera.example.test/current.jpg?token=secret",
        verify_ssl=False,
    )
