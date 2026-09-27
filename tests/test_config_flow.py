"""Tests for Monita server-centric configuration."""

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gotify_mu.config_flow import GotifyMUOptionsFlow
from custom_components.gotify_mu.const import (
    CONF_CHANNEL_IDS,
    CONF_CLIENT_TOKEN,
    CONF_DEFAULT_PRIORITY,
    CONF_INBOUND_ENABLED,
    CONF_SERVER_URL,
    CONF_VERIFY_SSL,
    DEFAULT_PRIORITY,
    DOMAIN,
)

SERVER = "http://monita.local:8080"
CLIENT_TOKEN = "gtfyc.test-private-token"


def _channel_payload(
    channel_id: int = 7,
    name: str = "Security",
    *,
    role: str = "owner",
    allow_member_post: bool = False,
) -> dict:
    return {
        "id": channel_id,
        "name": name,
        "description": f"{name} messages",
        "allowMemberPost": allow_member_post,
        "autoAssign": False,
        "channelType": "notification",
        "receiveNotifications": True,
        "role": role,
        "image": "static/defaultapp.png",
    }


async def _start_user_flow(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


def _mock_server(aioclient_mock, channels: list[dict]) -> None:
    aioclient_mock.get(f"{SERVER}/health", json={"health": "green"})
    aioclient_mock.get(
        f"{SERVER}/current/user",
        json={"id": 1, "name": "homeassistant"},
    )
    aioclient_mock.get(f"{SERVER}/application", json=channels)


async def test_server_setup_discovers_and_selects_multiple_channels(
    hass, aioclient_mock
):
    """One Monita server entry exposes multiple selected Channels."""
    _mock_server(
        aioclient_mock,
        [
            _channel_payload(7, "Security", role="owner"),
            _channel_payload(8, "Greenhouse", role="publisher"),
            _channel_payload(9, "Archive", role="readonly"),
        ],
    )

    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERVER_URL: SERVER,
            CONF_CLIENT_TOKEN: CLIENT_TOKEN,
            CONF_VERIFY_SSL: True,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "channels"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CHANNEL_IDS: ["7", "8", "9"]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Monita — monita.local:8080"
    assert result["result"].unique_id == f"{SERVER}|server"
    assert result["data"] == {
        CONF_SERVER_URL: SERVER,
        CONF_CLIENT_TOKEN: CLIENT_TOKEN,
        CONF_VERIFY_SSL: True,
    }
    assert result["options"][CONF_CHANNEL_IDS] == [7, 8, 9]
    assert result["options"][CONF_DEFAULT_PRIORITY] == DEFAULT_PRIORITY
    assert result["options"][CONF_INBOUND_ENABLED] is True


async def test_server_setup_rejects_invalid_client_token(hass, aioclient_mock):
    """Server setup validates the client credential before Channel selection."""
    aioclient_mock.get(f"{SERVER}/health", json={"health": "green"})
    aioclient_mock.get(f"{SERVER}/current/user", status=401)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERVER_URL: SERVER,
            CONF_CLIENT_TOKEN: CLIENT_TOKEN,
            CONF_VERIFY_SSL: True,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_server_setup_requires_at_least_one_accessible_channel(
    hass, aioclient_mock
):
    """An account with no accessible Channels cannot create an unusable entry."""
    _mock_server(aioclient_mock, [])

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERVER_URL: SERVER,
            CONF_CLIENT_TOKEN: CLIENT_TOKEN,
            CONF_VERIFY_SSL: True,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "no_channels"}


async def test_channel_selection_rejects_unknown_channel(hass, aioclient_mock):
    """A stale/unknown Channel ID cannot be saved."""
    _mock_server(aioclient_mock, [_channel_payload(7, "Security")])

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERVER_URL: SERVER,
            CONF_CLIENT_TOKEN: CLIENT_TOKEN,
            CONF_VERIFY_SSL: True,
        },
    )
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CHANNEL_IDS: ["99"]},
        )


async def test_manage_channels_refreshes_live_server_list(hass, aioclient_mock):
    """Options UI can rescan Monita and change the exposed Channel set."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Monita — monita.local:8080",
        unique_id=f"{SERVER}|server",
        data={
            CONF_SERVER_URL: SERVER,
            CONF_CLIENT_TOKEN: CLIENT_TOKEN,
            CONF_VERIFY_SSL: True,
        },
        options={
            CONF_CHANNEL_IDS: [7],
            CONF_DEFAULT_PRIORITY: DEFAULT_PRIORITY,
            CONF_INBOUND_ENABLED: True,
        },
        version=3,
    )
    entry.add_to_hass(hass)
    _mock_server(
        aioclient_mock,
        [
            _channel_payload(7, "Security"),
            _channel_payload(8, "Greenhouse", role="publisher"),
        ],
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert "channels" in result["menu_options"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "channels"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "channels"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CHANNEL_IDS: ["7", "8"]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_CHANNEL_IDS] == [7, 8]


def test_options_flow_uses_reload_helper():
    """Channel/option changes reload the integration automatically."""
    assert issubclass(GotifyMUOptionsFlow, config_entries.OptionsFlowWithReload)
