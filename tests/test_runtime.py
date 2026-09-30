"""Regression tests for Monita runtime entities and services."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.gotify_mu import (
    GotifyMURuntimeData,
    _async_stream_loop,
    async_setup,
)
from custom_components.gotify_mu.api import (
    GotifyMUAttachment,
    GotifyMUAuthError,
    GotifyMUChannel,
    GotifyMUConnectionError,
    GotifyMUError,
)
from custom_components.gotify_mu.binary_sensor import (
    GotifyMUConnectionBinarySensor,
    GotifyMUNativeBridgeBinarySensor,
)
from custom_components.gotify_mu.const import (
    CONF_CHANNEL_ID,
    CONF_DEFAULT_PRIORITY,
    CONF_SERVER_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
    EVENT_TYPE_MESSAGE,
    INTEGRATION_ORIGIN_EXTRA,
    SERVICE_DOMAIN,
    SERVICE_SEND,
)
from custom_components.gotify_mu.event import GotifyMUMessageEventEntity
from custom_components.gotify_mu.media import GotifyMUImage
from custom_components.gotify_mu.notify import GotifyMUNotifyEntity

SERVER = "http://monita.local:8080"
ENTRY_ID = "entry-runtime-test"
UNIQUE_ID = f"{SERVER}|channel:7"


def _channel(
    channel_id: int = 7,
    name: str = "Security",
    *,
    role: str = "owner",
    allow_member_post: bool = False,
    channel_type: str = "notification",
) -> GotifyMUChannel:
    return GotifyMUChannel(
        id=channel_id,
        name=name,
        role=role,
        allow_member_post=allow_member_post,
        channel_type=channel_type,
    )


def _entry(runtime, *, options=None, legacy=True):
    data = {CONF_SERVER_URL: SERVER}
    if legacy:
        data[CONF_CHANNEL_ID] = 7
    return SimpleNamespace(
        runtime_data=runtime,
        unique_id=UNIQUE_ID if legacy else f"{SERVER}|server",
        entry_id=ENTRY_ID,
        title="Monita — monita.local:8080" if not legacy else "Security",
        data=data,
        options=options or {},
        state=ConfigEntryState.LOADED,
        async_start_reauth=MagicMock(),
    )


def _legacy_runtime(client, *, channel_name="Security"):
    channel = _channel(name=channel_name)
    return SimpleNamespace(
        client=client,
        channel_id=7,
        channel_name=channel_name,
        active_channel_ids=(7,),
        channels={7: channel},
        channel=lambda channel_id: channel if channel_id == 7 else None,
    )


async def test_notify_entity_sends_with_default_priority_and_origin():
    """Legacy notify entity keeps its app-token send behavior and identity."""
    client = SimpleNamespace(
        app_token="app-token",
        client_token=None,
        async_send=AsyncMock(return_value={"id": 1}),
    )
    runtime = _legacy_runtime(client)
    entry = _entry(runtime, options={CONF_DEFAULT_PRIORITY: 8})
    entity = GotifyMUNotifyEntity(entry, _channel())

    await entity.async_send_message("Door opened", title="Home")

    client.async_send.assert_awaited_once_with(
        "Door opened",
        title="Home",
        priority=8,
        extras={
            INTEGRATION_ORIGIN_EXTRA: {
                "entry_id": ENTRY_ID,
                "channel_id": 7,
                "source": "monita-ha",
            }
        },
    )


async def test_server_notify_entity_routes_with_client_token_channel_id():
    """Server-centric notify entities route through the selected Channel ID."""
    client = SimpleNamespace(
        app_token="",
        client_token="client-token",
        async_send=AsyncMock(return_value={"id": 1}),
    )
    channel = _channel(8, "Greenhouse", role="publisher")
    runtime = SimpleNamespace(
        client=client,
        channel_id=8,
        channel_name=channel.name,
        active_channel_ids=(7, 8),
        channels={8: channel},
        channel=lambda channel_id: channel if channel_id == 8 else None,
    )
    entry = _entry(runtime, legacy=False)
    entity = GotifyMUNotifyEntity(entry, channel)

    await entity.async_send_message("Temperature high", title="Greenhouse")

    client.async_send.assert_awaited_once_with(
        "Temperature high",
        title="Greenhouse",
        priority=5,
        extras={
            INTEGRATION_ORIGIN_EXTRA: {
                "entry_id": ENTRY_ID,
                "channel_id": 8,
                "source": "monita-ha",
            },
            "monita::controls": ["assign", "resolve", "attach"],
        },
        channel_id=8,
    )


async def test_push_message_supports_priority_markdown_and_channel_selection(hass):
    """Push Message targets one selected Channel with the server credential."""
    client = SimpleNamespace(
        app_token="",
        client_token="client-token",
        async_send=AsyncMock(return_value={"id": 2}),
    )
    runtime = SimpleNamespace(
        client=client,
        channel_id=7,
        channel_name="Security",
        active_channel_ids=(7, 8),
    )
    entry = _entry(runtime, legacy=False)

    with patch.object(
        hass.config_entries, "async_entries", return_value=[entry]
    ):
        assert await async_setup(hass, {})
        assert hass.services.has_service(SERVICE_DOMAIN, SERVICE_SEND)
        assert hass.services.has_service(DOMAIN, SERVICE_SEND)
        await hass.services.async_call(
            SERVICE_DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "channel_id": 8,
                "title": "Alert",
                "message": "**High temperature**",
                "priority": 9,
                "markdown": True,
                "controls": ["assign", "resolve", "attach"],
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
                "channel_id": 8,
                "source": "monita-ha",
            }
        },
        channel_id=8,
    )


async def test_push_message_requires_channel_when_server_exposes_many(hass):
    """Push Message never guesses when one server exposes multiple Channels."""
    client = SimpleNamespace(
        app_token="",
        client_token="client-token",
        async_send=AsyncMock(),
    )
    runtime = SimpleNamespace(
        client=client,
        channel_id=7,
        channel_name="Security",
        active_channel_ids=(7, 8),
    )
    entry = _entry(runtime, legacy=False)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        pytest.raises(
            ServiceValidationError,
            match="Choose a Monita Channel",
        ),
    ):
        assert await async_setup(hass, {})
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "message": "Destination must be explicit",
            },
            blocking=True,
        )

    client.async_send.assert_not_awaited()


async def test_stream_filters_to_selected_channels_and_self_origin(hass):
    """One server stream accepts selected Channels and filters everything else."""
    messages = [
        {"id": 1, "appid": 9, "message": "Unselected"},
        {
            "id": 2,
            "appid": 7,
            "message": "Loopback",
            "extras": {
                INTEGRATION_ORIGIN_EXTRA: {
                    "entry_id": ENTRY_ID,
                    "channel_id": 7,
                    "source": "monita-ha",
                }
            },
        },
        {"id": 3, "appid": 8, "message": "Greenhouse external"},
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
        channel_name="Security",
        entry_id=ENTRY_ID,
        inbound_enabled=True,
        channels={
            7: _channel(7, "Security"),
            8: _channel(8, "Greenhouse", role="publisher"),
        },
        selected_channel_ids=(7, 8),
    )
    received = []

    def receive(message):
        received.append(message)
        runtime.async_stop()

    runtime.async_subscribe(receive)
    entry = _entry(runtime, legacy=False)

    await _async_stream_loop(hass, entry)

    assert received == [{"id": 3, "appid": 8, "message": "Greenhouse external"}]
    assert runtime.stream_connected is False


def test_event_entity_maps_inbound_message_and_channel_fields():
    """Inbound Monita messages include both Channel ID and Channel name."""
    channel = _channel(7, "Security")
    runtime = SimpleNamespace(
        channel_name="Security",
        channel=lambda channel_id: channel if channel_id == 7 else None,
    )
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
            "channel_name": "Security",
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
        channel_name="Security",
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
    """Legacy image sends stage bytes first and preserve message controls."""
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
        app_token="app-token",
        client_token=None,
        async_upload_image=AsyncMock(return_value=attachment),
        async_send=AsyncMock(return_value={"id": 3}),
    )
    runtime = _legacy_runtime(client)
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
                "channel_id": 7,
                "source": "monita-ha",
            },
        },
        attachment_ids=[123],
    )


async def test_server_chat_image_routes_directly_to_chat_channel(hass):
    """Server-centric Chat images use Monita's direct Chat image endpoint."""
    image = GotifyMUImage(
        content=b"\xff\xd8\xff\xe0jpeg",
        filename="front-door.jpg",
        content_type="image/jpeg",
    )
    client = SimpleNamespace(
        app_token="",
        client_token="client-token",
        async_send_chat_image=AsyncMock(return_value={"id": 55}),
        async_upload_image=AsyncMock(),
        async_send=AsyncMock(),
    )
    chat = _channel(
        8,
        "Doorbell Chat",
        role="publisher",
        allow_member_post=True,
        channel_type="chat",
    )
    runtime = SimpleNamespace(
        client=client,
        channel_id=7,
        channel_name="Security",
        active_channel_ids=(7, 8),
        capabilities={"features": {"chatImages": True}},
        channel=lambda channel_id: chat if channel_id == 8 else None,
    )
    entry = _entry(runtime, legacy=False)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_entity_image",
            new=AsyncMock(return_value=image),
        ),
    ):
        assert await async_setup(hass, {})
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "channel_id": 8,
                "message": "Person detected",
                "priority": 9,
                "markdown": True,
                "image_entity": "camera.front_door",
            },
            blocking=True,
        )

    client.async_send_chat_image.assert_awaited_once_with(
        "Person detected",
        channel_id=8,
        image=image.content,
        filename=image.filename,
        content_type=image.content_type,
        title=None,
        priority=9,
        extras={
            INTEGRATION_ORIGIN_EXTRA: {
                "entry_id": ENTRY_ID,
                "channel_id": 8,
                "source": "monita-ha",
            },
            "client::display": {"contentType": "text/markdown"},
        },
    )
    client.async_upload_image.assert_not_awaited()
    client.async_send.assert_not_awaited()


async def test_server_notification_channel_image_routes_directly_when_supported(hass):
    """Monita 1.1.9+ accepts direct images on Notification Channels."""
    image = GotifyMUImage(
        content=b"\xff\xd8\xff\xe0jpeg",
        filename="front-door.jpg",
        content_type="image/jpeg",
    )
    client = SimpleNamespace(
        app_token="",
        client_token="client-token",
        async_send_chat_image=AsyncMock(return_value={"id": 56}),
        async_upload_image=AsyncMock(),
        async_send=AsyncMock(),
    )
    channel = _channel(8, "Important Notices", role="publisher")
    runtime = SimpleNamespace(
        client=client,
        channel_id=7,
        channel_name="Security",
        active_channel_ids=(7, 8),
        capabilities={"features": {"notificationImages": True}},
        channel=lambda channel_id: channel if channel_id == 8 else None,
    )
    entry = _entry(runtime, legacy=False)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_entity_image",
            new=AsyncMock(return_value=image),
        ),
    ):
        assert await async_setup(hass, {})
        await hass.services.async_call(
            SERVICE_DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "channel_id": 8,
                "title": "Back Doorbell Rung",
                "message": "Someone is at the back door.",
                "priority": 8,
                "image_entity": "camera.back_door_fluent",
            },
            blocking=True,
        )

    client.async_send_chat_image.assert_awaited_once_with(
        "Someone is at the back door.",
        channel_id=8,
        image=image.content,
        filename=image.filename,
        content_type=image.content_type,
        title="Back Doorbell Rung",
        priority=8,
        extras={
            INTEGRATION_ORIGIN_EXTRA: {
                "entry_id": ENTRY_ID,
                "channel_id": 8,
                "source": "monita-ha",
            }
        },
    )
    client.async_upload_image.assert_not_awaited()
    client.async_send.assert_not_awaited()


async def test_server_notification_image_falls_back_to_text_on_older_server(hass):
    """Older Monita servers still deliver the alert instead of dropping it."""
    image = GotifyMUImage(
        content=b"\xff\xd8\xff\xe0jpeg",
        filename="front-door.jpg",
        content_type="image/jpeg",
    )
    client = SimpleNamespace(
        app_token="",
        client_token="client-token",
        async_send_chat_image=AsyncMock(),
        async_upload_image=AsyncMock(),
        async_send=AsyncMock(return_value={"id": 57}),
    )
    channel = _channel(8, "Important Notices", role="publisher")
    runtime = SimpleNamespace(
        client=client,
        channel_id=7,
        channel_name="Security",
        active_channel_ids=(7, 8),
        capabilities={"features": {"chatImages": True}},
        channel=lambda channel_id: channel if channel_id == 8 else None,
    )
    entry = _entry(runtime, legacy=False)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_entity_image",
            new=AsyncMock(return_value=image),
        ),
    ):
        assert await async_setup(hass, {})
        await hass.services.async_call(
            SERVICE_DOMAIN,
            SERVICE_SEND,
            {
                "entry_id": ENTRY_ID,
                "channel_id": 8,
                "title": "Back Doorbell Rung",
                "message": "Someone is at the back door.",
                "priority": 8,
                "image_entity": "camera.back_door_fluent",
            },
            blocking=True,
        )

    client.async_send_chat_image.assert_not_awaited()
    client.async_upload_image.assert_not_awaited()
    client.async_send.assert_awaited_once_with(
        "Someone is at the back door.",
        title="Back Doorbell Rung",
        priority=8,
        markdown=False,
        extras={
            INTEGRATION_ORIGIN_EXTRA: {
                "entry_id": ENTRY_ID,
                "channel_id": 8,
                "source": "monita-ha",
            }
        },
        channel_id=8,
    )


async def test_image_upload_failure_prevents_message_send(hass):
    """A requested legacy image can never silently degrade to text-only."""
    image = GotifyMUImage(
        content=b"\xff\xd8\xff\xe0jpeg",
        filename="front-door.jpg",
        content_type="image/jpeg",
    )
    client = SimpleNamespace(
        app_token="app-token",
        client_token=None,
        async_upload_image=AsyncMock(side_effect=GotifyMUError("upload rejected")),
        async_send=AsyncMock(),
    )
    runtime = _legacy_runtime(client)
    entry = _entry(runtime)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_entity_image",
            new=AsyncMock(return_value=image),
        ),
        pytest.raises(HomeAssistantError, match="Monita rejected the image"),
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
    """An app-token rejection during legacy image staging starts reauth."""
    image = GotifyMUImage(
        content=b"\xff\xd8\xff\xe0jpeg",
        filename="front-door.jpg",
        content_type="image/jpeg",
    )
    client = SimpleNamespace(
        app_token="app-token",
        client_token=None,
        async_upload_image=AsyncMock(side_effect=GotifyMUAuthError("rejected")),
        async_send=AsyncMock(),
    )
    runtime = _legacy_runtime(client)
    entry = _entry(runtime)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_entity_image",
            new=AsyncMock(return_value=image),
        ),
        pytest.raises(HomeAssistantError, match="configured credential"),
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
    """A staged legacy image is not destructively cleaned up on send failure."""
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
        app_token="app-token",
        client_token=None,
        async_upload_image=AsyncMock(return_value=attachment),
        async_send=AsyncMock(side_effect=GotifyMUConnectionError("offline")),
        async_delete_attachment=AsyncMock(),
    )
    runtime = _legacy_runtime(client)
    entry = _entry(runtime)

    with (
        patch.object(hass.config_entries, "async_entries", return_value=[entry]),
        patch(
            "custom_components.gotify_mu.async_acquire_entity_image",
            new=AsyncMock(return_value=image),
        ),
        pytest.raises(HomeAssistantError, match="Could not connect to Monita"),
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
    """Advanced legacy URL retrieval uses the configured TLS behavior."""
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
        app_token="app-token",
        client_token=None,
        async_upload_image=AsyncMock(return_value=attachment),
        async_send=AsyncMock(return_value={"id": 4}),
    )
    runtime = _legacy_runtime(client)
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
