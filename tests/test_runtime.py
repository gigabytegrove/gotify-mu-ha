"""Regression tests for Gotify MU runtime entities and services."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState

from custom_components.gotify_mu import (
    GotifyMURuntimeData,
    _async_stream_loop,
    async_setup,
)
from custom_components.gotify_mu.binary_sensor import (
    GotifyMUConnectionBinarySensor,
    GotifyMUNativeBridgeBinarySensor,
)
from custom_components.gotify_mu.const import (
    CONF_DEFAULT_PRIORITY,
    CONF_SERVER_URL,
    DOMAIN,
    EVENT_TYPE_MESSAGE,
    INTEGRATION_ORIGIN_EXTRA,
    SERVICE_SEND,
)
from custom_components.gotify_mu.event import GotifyMUMessageEventEntity
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
