"""Tests for the Gotify MU config flow."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.gotify_mu.config_flow import GotifyMUOptionsFlow
from custom_components.gotify_mu.const import (
    CONF_APP_TOKEN,
    CONF_CHANNEL_ID,
    CONF_CHANNEL_NAME,
    CONF_CLIENT_TOKEN,
    CONF_INBOUND_ENABLED,
    CONF_SERVER_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
)

SERVER = "http://gotify-mu.local:8080"
APP_TOKEN = "gtfya.test-private-token"
CLIENT_TOKEN = "gtfyc.test-private-token"


def _app_payload(channel_id: int = 7, name: str = "Home Assistant") -> dict:
    return {
        "id": channel_id,
        "name": name,
        "description": "Automation messages",
        "allowMemberPost": True,
        "autoAssign": True,
        "image": "static/defaultapp.png",
    }


async def _start_user_flow(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_current_mu_server_identifies_channel_automatically(hass, aioclient_mock):
    """Current MU servers identify the app-token Channel without a test message."""
    aioclient_mock.get(f"{SERVER}/health", json={"health": "green"})
    aioclient_mock.get(f"{SERVER}/application/current", json=_app_payload())

    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERVER_URL: SERVER,
            CONF_APP_TOKEN: APP_TOKEN,
            CONF_CLIENT_TOKEN: "",
            CONF_VERIFY_SSL: True,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home Assistant"
    assert result["result"].unique_id == f"{SERVER}|channel:7"
    assert result["data"][CONF_CHANNEL_ID] == 7
    assert result["data"][CONF_CHANNEL_NAME] == "Home Assistant"
    assert CONF_CLIENT_TOKEN not in result["data"]
    assert result["options"][CONF_INBOUND_ENABLED] is False


async def test_legacy_server_outbound_only_uses_safe_validation(hass, aioclient_mock):
    """Legacy Gotify-compatible servers validate app tokens without a real message."""
    aioclient_mock.get(f"{SERVER}/health", json={"health": "green"})
    aioclient_mock.get(f"{SERVER}/application/current", status=404)
    aioclient_mock.post(f"{SERVER}/message", status=400)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERVER_URL: SERVER,
            CONF_APP_TOKEN: APP_TOKEN,
            CONF_CLIENT_TOKEN: "",
            CONF_VERIFY_SSL: True,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "channel"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CHANNEL_NAME: "Home Assistant"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home Assistant"
    assert result["data"][CONF_SERVER_URL] == SERVER
    assert CONF_CLIENT_TOKEN not in result["data"]
    assert APP_TOKEN not in result["result"].unique_id


async def test_legacy_server_client_token_enables_channel_discovery(
    hass, aioclient_mock
):
    """A client token enables Channel discovery on older MU servers."""
    aioclient_mock.get(f"{SERVER}/health", json={"health": "green"})
    aioclient_mock.get(f"{SERVER}/application/current", status=404)
    aioclient_mock.post(f"{SERVER}/message", status=400)
    aioclient_mock.get(f"{SERVER}/current/user", json={"id": 1, "name": "admin"})
    aioclient_mock.get(f"{SERVER}/application", json=[_app_payload()])

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERVER_URL: SERVER,
            CONF_APP_TOKEN: APP_TOKEN,
            CONF_CLIENT_TOKEN: CLIENT_TOKEN,
            CONF_VERIFY_SSL: True,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "channel"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CHANNEL_ID: "7"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == f"{SERVER}|channel:7"
    assert result["data"][CONF_CLIENT_TOKEN] == CLIENT_TOKEN
    assert result["options"][CONF_INBOUND_ENABLED] is True


async def test_current_server_client_token_must_access_app_channel(
    hass, aioclient_mock
):
    """Reject a client token that cannot subscribe to the app-token Channel."""
    aioclient_mock.get(f"{SERVER}/health", json={"health": "green"})
    aioclient_mock.get(f"{SERVER}/application/current", json=_app_payload(channel_id=7))
    aioclient_mock.get(f"{SERVER}/current/user", json={"id": 1, "name": "admin"})
    aioclient_mock.get(
        f"{SERVER}/application",
        json=[_app_payload(channel_id=8, name="Different Channel")],
    )

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERVER_URL: SERVER,
            CONF_APP_TOKEN: APP_TOKEN,
            CONF_CLIENT_TOKEN: CLIENT_TOKEN,
            CONF_VERIFY_SSL: True,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "channel_not_accessible"}


async def test_invalid_application_token(hass, aioclient_mock):
    """Invalid application tokens are rejected during setup."""
    aioclient_mock.get(f"{SERVER}/health", json={"health": "green"})
    aioclient_mock.get(f"{SERVER}/application/current", status=401)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SERVER_URL: SERVER,
            CONF_APP_TOKEN: APP_TOKEN,
            CONF_CLIENT_TOKEN: "",
            CONF_VERIFY_SSL: True,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


def test_options_flow_uses_reload_helper():
    """Options changes must reload the entry so inbound stream changes apply."""
    assert issubclass(GotifyMUOptionsFlow, config_entries.OptionsFlowWithReload)
