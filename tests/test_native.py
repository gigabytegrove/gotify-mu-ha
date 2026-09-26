"""Tests for Gotify MU native Home Assistant pairing and event bridging."""

from unittest.mock import patch

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
from custom_components.gotify_mu.native import (
    GotifyMUNativeBridge,
    GotifyMUNativePairingError,
    async_pair_native,
)

SERVER = "http://gotify-mu.local:8080"
PAIR_URL = f"{SERVER}/integrations/home-assistant/native/pair"
EVENT_PATH = "/integrations/home-assistant/native/12/event"
EVENT_URL = f"{SERVER}{EVENT_PATH}"
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


async def test_native_pairing_success_stores_credentials(hass, aioclient_mock):
    """Options flow stores native credentials without replacing normal tokens."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home Assistant",
        unique_id=f"{SERVER}|channel:7",
        data=_entry_data(),
        options={},
    )
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
        assert result["type"] is FlowResultType.MENU
        assert result["description_placeholders"] == {"native_state": "Not paired"}

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "native_pairing"}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "native_pair"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_NATIVE_PAIRING_CODE: PAIRING_CODE}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_APP_TOKEN] == "gtfya.application-token"
    assert entry.data[CONF_NATIVE_INTEGRATION_ID] == 12
    assert entry.data[CONF_NATIVE_SECRET] == SHARED_SECRET
    assert entry.data[CONF_NATIVE_EVENT_PATH] == EVENT_PATH
    assert entry.data[CONF_NATIVE_WEBHOOK_ID] == WEBHOOK_ID
    assert entry.data[CONF_NATIVE_WEBHOOK_URL] == WEBHOOK_URL


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (400, "invalid_pairing_code"),
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
    finally:
        bridge.async_stop()


async def test_home_assistant_event_posts_to_gotify_mu(hass, aioclient_mock):
    """HA events are authenticated and posted to the native Gotify MU endpoint."""
    aioclient_mock.post(EVENT_URL, status=204)
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
        event = Event("state_changed", {"entity_id": "binary_sensor.front_door"})
        await bridge._async_post_event(event)
    finally:
        bridge.async_stop()

    assert len(aioclient_mock.mock_calls) == 1
    method, url, body, headers = aioclient_mock.mock_calls[0]
    assert method == "POST"
    assert str(url) == EVENT_URL
    assert headers["Authorization"] == f"Bearer {SHARED_SECRET}"
    assert headers["Content-Type"] == "application/json"
    assert b"state_changed" in body
    assert b"binary_sensor.front_door" in body
