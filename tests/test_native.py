"""Tests for Gotify MU native Home Assistant pairing and event bridging."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Event
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gotify_mu.const import (
    CONF_APP_TOKEN,
    CONF_CHANNEL_ID,
    CONF_CHANNEL_NAME,
    CONF_FORCE_LOCAL_REMOVE,
    CONF_HOME_ASSISTANT_URL,
    CONF_NATIVE_EVENT_PATH,
    CONF_NATIVE_INTEGRATION_ID,
    CONF_NATIVE_PAIRING_CODE,
    CONF_NATIVE_SECRET,
    CONF_NATIVE_WEBHOOK_ID,
    CONF_NATIVE_WEBHOOK_URL,
    CONF_SERVER_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.gotify_mu.diagnostics import async_get_config_entry_diagnostics
from custom_components.gotify_mu.native import (
    GotifyMUNativeBridge,
    GotifyMUNativePairingError,
    _NativeDeliveryResult,
    async_pair_native,
)

SERVER = "http://gotify-mu.local:8080"
PAIR_URL = f"{SERVER}/integrations/home-assistant/native/pair"
EVENT_PATH = "/integrations/home-assistant/native/12/event"
EVENT_URL = f"{SERVER}{EVENT_PATH}"
REVOKE_URL = f"{SERVER}/integrations/home-assistant/native/12"
PAIRING_CODE = "12.one-time-secret"
SHARED_SECRET = "native-shared-secret"
WEBHOOK_ID = "native-webhook-test"
WEBHOOK_URL = f"http://homeassistant.local:8123/api/webhook/{WEBHOOK_ID}"


def _entry_data(*, paired: bool = False) -> dict:
    data = {
        CONF_SERVER_URL: SERVER,
        CONF_APP_TOKEN: "gtfya.application-token",
        CONF_VERIFY_SSL: True,
        CONF_CHANNEL_ID: 7,
        CONF_CHANNEL_NAME: "Home Assistant",
    }
    if paired:
        data.update(
            {
                CONF_NATIVE_INTEGRATION_ID: 12,
                CONF_NATIVE_SECRET: SHARED_SECRET,
                CONF_NATIVE_EVENT_PATH: EVENT_PATH,
                CONF_NATIVE_WEBHOOK_ID: WEBHOOK_ID,
                CONF_NATIVE_WEBHOOK_URL: WEBHOOK_URL,
            }
        )
    return data


def _entry(*, paired: bool = False) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Home Assistant",
        unique_id=f"{SERVER}|channel:7",
        data=_entry_data(paired=paired),
        options={},
    )


async def _open_native_pair_flow(hass, entry: MockConfigEntry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "native_pairing"}
    )
    return result


async def test_native_pairing_success_stores_credentials(hass, aioclient_mock):
    """Options flow stores native credentials without replacing normal tokens."""
    entry = _entry()
    entry.add_to_hass(hass)
    aioclient_mock.post(
        PAIR_URL,
        json={
            "integrationId": 12,
            "secret": SHARED_SECRET,
            "eventPath": EVENT_PATH,
        },
    )

    with (
        patch(
            "custom_components.gotify_mu.config_flow.webhook.async_generate_id",
            return_value=WEBHOOK_ID,
        ),
        patch(
            "custom_components.gotify_mu.config_flow.webhook.async_generate_url",
            return_value=WEBHOOK_URL,
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["description_placeholders"] == {"native_state": "Not paired"}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "native_pairing"}
        )
        assert result["step_id"] == "native_pair"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_NATIVE_PAIRING_CODE: PAIRING_CODE,
                CONF_HOME_ASSISTANT_URL: "",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_APP_TOKEN] == "gtfya.application-token"
    assert entry.data[CONF_NATIVE_INTEGRATION_ID] == 12
    assert entry.data[CONF_NATIVE_SECRET] == SHARED_SECRET
    assert entry.data[CONF_NATIVE_EVENT_PATH] == EVENT_PATH
    assert entry.data[CONF_NATIVE_WEBHOOK_ID] == WEBHOOK_ID
    assert entry.data[CONF_NATIVE_WEBHOOK_URL] == WEBHOOK_URL


async def test_native_pairing_manual_callback_override(hass, aioclient_mock):
    """A manual HA URL overrides an automatically detected but unreachable URL."""
    entry = _entry()
    entry.add_to_hass(hass)
    aioclient_mock.post(
        PAIR_URL,
        json={
            "integrationId": 12,
            "secret": SHARED_SECRET,
            "eventPath": EVENT_PATH,
        },
    )

    with (
        patch(
            "custom_components.gotify_mu.config_flow.webhook.async_generate_id",
            return_value=WEBHOOK_ID,
        ),
        patch(
            "custom_components.gotify_mu.config_flow.webhook.async_generate_url",
            return_value="http://unreachable.local:8123/api/webhook/native-webhook-test",
        ),
    ):
        result = await _open_native_pair_flow(hass, entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_NATIVE_PAIRING_CODE: PAIRING_CODE,
                CONF_HOME_ASSISTANT_URL: "http://reachable-ha.local:8123",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert (
        entry.data[CONF_NATIVE_WEBHOOK_URL]
        == "http://reachable-ha.local:8123/api/webhook/native-webhook-test"
    )


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (400, "invalid_pairing_code"),
        (401, "invalid_pairing_code"),
        (404, "invalid_pairing_code"),
        (410, "pairing_expired"),
        (422, "pairing_failed"),
    ],
)
async def test_native_pairing_errors(hass, aioclient_mock, status, reason):
    """Bad, expired, and otherwise failed pairing responses are explicit."""
    aioclient_mock.post(PAIR_URL, status=status)

    with pytest.raises(GotifyMUNativePairingError) as err:
        await async_pair_native(
            async_get_clientsession(hass),
            server_url=SERVER,
            verify_ssl=True,
            pairing_code=PAIRING_CODE,
            webhook_url=WEBHOOK_URL,
        )

    assert err.value.reason == reason


async def test_native_repair_replaces_only_native_credentials(hass, aioclient_mock):
    """Repairing native pairing preserves the normal Gotify MU integration."""
    entry = _entry(paired=True)
    entry.add_to_hass(hass)
    aioclient_mock.post(
        PAIR_URL,
        json={
            "integrationId": 12,
            "secret": "replacement-secret",
            "eventPath": EVENT_PATH,
        },
    )

    with (
        patch(
            "custom_components.gotify_mu.config_flow.webhook.async_generate_id",
            return_value="replacement-webhook",
        ),
        patch(
            "custom_components.gotify_mu.config_flow.webhook.async_generate_url",
            return_value="http://homeassistant.local:8123/api/webhook/replacement-webhook",
        ),
    ):
        result = await _open_native_pair_flow(hass, entry)
        assert result["type"] is FlowResultType.MENU
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "native_repair"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_NATIVE_PAIRING_CODE: PAIRING_CODE,
                CONF_HOME_ASSISTANT_URL: "",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_APP_TOKEN] == "gtfya.application-token"
    assert entry.data[CONF_NATIVE_SECRET] == "replacement-secret"
    assert entry.data[CONF_NATIVE_WEBHOOK_ID] == "replacement-webhook"


async def test_native_remove_revokes_remote_bridge(hass, aioclient_mock):
    """Removing native pairing revokes Gotify MU before clearing local credentials."""
    entry = _entry(paired=True)
    entry.add_to_hass(hass)
    aioclient_mock.delete(REVOKE_URL, status=204)

    result = await _open_native_pair_flow(hass, entry)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "native_remove"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"confirm": True, CONF_FORCE_LOCAL_REMOVE: False},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_APP_TOKEN] == "gtfya.application-token"
    assert CONF_NATIVE_SECRET not in entry.data
    assert CONF_NATIVE_WEBHOOK_ID not in entry.data
    method, url, _body, headers = aioclient_mock.mock_calls[-1]
    assert method == "DELETE"
    assert str(url) == REVOKE_URL
    assert headers["Authorization"] == f"Bearer {SHARED_SECRET}"


async def test_native_remove_requires_force_when_revoke_fails(hass, aioclient_mock):
    """Remote revoke failures do not silently leave stale credentials on Gotify MU."""
    entry = _entry(paired=True)
    entry.add_to_hass(hass)
    aioclient_mock.delete(REVOKE_URL, status=401)

    result = await _open_native_pair_flow(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "native_remove"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"confirm": True, CONF_FORCE_LOCAL_REMOVE: False},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unpair_auth_failed"}
    assert entry.data[CONF_NATIVE_SECRET] == SHARED_SECRET


async def test_native_force_local_remove_recovers_from_remote_revoke_failure(
    hass, aioclient_mock
):
    """Force-local removal is an explicit recovery path for a stale remote pairing."""
    entry = _entry(paired=True)
    entry.add_to_hass(hass)
    aioclient_mock.delete(REVOKE_URL, status=401)

    result = await _open_native_pair_flow(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "native_remove"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"confirm": True, CONF_FORCE_LOCAL_REMOVE: True},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_APP_TOKEN] == "gtfya.application-token"
    assert CONF_NATIVE_SECRET not in entry.data


async def test_native_webhook_rejects_invalid_bearer(hass, hass_client):
    """The HA webhook rejects a request with the wrong shared secret."""
    assert await async_setup_component(hass, "webhook", {})
    client = await hass_client()
    bridge = GotifyMUNativeBridge(
        hass,
        async_get_clientsession(hass),
        name="Home Assistant",
        server_url=SERVER,
        verify_ssl=True,
        secret=SHARED_SECRET,
        event_path=EVENT_PATH,
        webhook_id=WEBHOOK_ID,
    )
    bridge.async_start()
    try:
        response = await client.post(
            f"/api/webhook/{WEBHOOK_ID}",
            headers={"Authorization": "Bearer wrong-secret"},
            json={"eventType": "gotify_mu_test", "data": {"message": "blocked"}},
        )
        assert response.status == 401
        assert bridge.status == "paired"
    finally:
        bridge.async_stop()


async def test_native_webhook_fires_home_assistant_event(hass, hass_client):
    """A valid Gotify MU webhook payload is emitted onto the HA event bus."""
    assert await async_setup_component(hass, "webhook", {})
    client = await hass_client()
    received = []
    hass.bus.async_listen("gotify_mu_test", received.append)
    bridge = GotifyMUNativeBridge(
        hass,
        async_get_clientsession(hass),
        name="Home Assistant",
        server_url=SERVER,
        verify_ssl=True,
        secret=SHARED_SECRET,
        event_path=EVENT_PATH,
        webhook_id=WEBHOOK_ID,
    )
    bridge.async_start()
    try:
        response = await client.post(
            f"/api/webhook/{WEBHOOK_ID}",
            headers={"Authorization": f"Bearer {SHARED_SECRET}"},
            json={
                "eventType": "gotify_mu_test",
                "data": {"message": "Gotify MU connection test"},
            },
        )
        await hass.async_block_till_done()
        assert response.status == 200
        assert len(received) == 1
        assert received[0].data == {"message": "Gotify MU connection test"}
        assert bridge.status == "connected"
        assert bridge.last_received_at is not None
    finally:
        bridge.async_stop()


async def test_home_assistant_event_bus_posts_to_gotify_mu(hass, aioclient_mock):
    """A real HA event-bus event is authenticated and posted to Gotify MU."""
    aioclient_mock.post(EVENT_URL, status=202)
    bridge = GotifyMUNativeBridge(
        hass,
        async_get_clientsession(hass),
        name="Home Assistant",
        server_url=SERVER,
        verify_ssl=True,
        secret=SHARED_SECRET,
        event_path=EVENT_PATH,
        webhook_id=WEBHOOK_ID,
    )
    bridge.async_start()
    try:
        hass.bus.async_fire(
            "state_changed", {"entity_id": "binary_sensor.front_door"}
        )
        for _ in range(100):
            if aioclient_mock.mock_calls:
                break
            await asyncio.sleep(0.01)
        assert aioclient_mock.mock_calls
        method, url, body, headers = aioclient_mock.mock_calls[-1]
        assert method == "POST"
        assert str(url) == EVENT_URL
        assert headers["Authorization"] == f"Bearer {SHARED_SECRET}"
        assert headers["Content-Type"] == "application/json"
        assert b"state_changed" in body
        assert b"binary_sensor.front_door" in body
        assert bridge.last_sent_at is not None
    finally:
        bridge.async_stop()


async def test_native_event_delivery_retries_transient_failure(hass):
    """Transient failures use bounded retry and recover without dropping the event."""
    bridge = GotifyMUNativeBridge(
        hass,
        async_get_clientsession(hass),
        name="Home Assistant",
        server_url=SERVER,
        verify_ssl=True,
        secret=SHARED_SECRET,
        event_path=EVENT_PATH,
        webhook_id=WEBHOOK_ID,
    )
    event = Event("state_changed", {"entity_id": "binary_sensor.front_door"})
    attempts = AsyncMock(
        side_effect=[
            _NativeDeliveryResult(
                success=False,
                retryable=True,
                error="Gotify MU returned HTTP 503 for native event delivery",
            ),
            _NativeDeliveryResult(success=True),
        ]
    )
    with (
        patch.object(bridge, "_async_post_body", attempts),
        patch("custom_components.gotify_mu.native.asyncio.sleep", new=AsyncMock()),
    ):
        assert await bridge._async_post_event(event)

    assert attempts.await_count == 2
    assert bridge.retry_count == 1
    assert bridge.dropped_events == 0
    assert bridge.status == "connected"


async def test_native_event_auth_failure_marks_repair_required(hass, aioclient_mock):
    """A rejected native secret is visible as repair-required state."""
    aioclient_mock.post(EVENT_URL, status=401)
    bridge = GotifyMUNativeBridge(
        hass,
        async_get_clientsession(hass),
        name="Home Assistant",
        server_url=SERVER,
        verify_ssl=True,
        secret=SHARED_SECRET,
        event_path=EVENT_PATH,
        webhook_id=WEBHOOK_ID,
    )
    event = Event("state_changed", {"entity_id": "binary_sensor.front_door"})
    assert not await bridge._async_post_event(event)
    assert bridge.repair_required
    assert bridge.status == "repair_required"
    assert bridge.dropped_events == 1


async def test_diagnostics_redact_native_credentials(hass):
    """Diagnostics never expose native secrets or private webhook details."""
    entry = _entry(paired=True)
    entry.runtime_data = SimpleNamespace(
        channel_id=7,
        channel_name="Home Assistant",
        inbound_enabled=False,
        stream_connected=False,
        stream_reconnects=0,
        last_stream_error=None,
        native_bridge=None,
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    rendered = repr(diagnostics)
    assert SHARED_SECRET not in rendered
    assert WEBHOOK_ID not in rendered
    assert WEBHOOK_URL not in rendered
    assert diagnostics["runtime"]["native_paired"] is True
