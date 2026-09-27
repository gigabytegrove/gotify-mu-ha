"""Config flow for Monita."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    GotifyMUAuthError,
    GotifyMUChannel,
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
    CONF_FORCE_LOCAL_REMOVE,
    CONF_HOME_ASSISTANT_URL,
    CONF_INBOUND_ENABLED,
    CONF_NATIVE_INTEGRATION_ID,
    CONF_NATIVE_PAIRING_CODE,
    CONF_NATIVE_SECRET,
    CONF_REMOVE_CLIENT_TOKEN,
    CONF_SERVER_URL,
    CONF_VERIFY_SSL,
    DEFAULT_INBOUND_ENABLED,
    DEFAULT_NAME,
    DEFAULT_PRIORITY,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .helpers import channel_unique_id, fallback_unique_id, normalize_server_url
from .native import (
    GotifyMUNativePairingError,
    PendingNativeWebhook,
    async_pair_native,
    async_revoke_native,
    native_pairing_data,
    native_pairing_is_configured,
    remove_native_pairing_data,
)
from .repairs import async_delete_native_bridge_repair_issue


class GotifyMUConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Monita."""

    VERSION = 2
    MINOR_VERSION = 0

    def __init__(self) -> None:
        """Initialize flow state."""
        self._pending: dict[str, Any] | None = None
        self._channels: list[GotifyMUChannel] = []

    async def _async_validate(
        self,
        *,
        server_url: str,
        app_token: str,
        client_token: str | None,
        verify_ssl: bool,
    ) -> tuple[GotifyMUClient, GotifyMUChannel | None, list[GotifyMUChannel]]:
        """Validate credentials and discover MU metadata when possible."""
        client = GotifyMUClient(
            async_get_clientsession(self.hass),
            server_url,
            app_token,
            verify_ssl,
            client_token,
        )
        await client.async_health()
        application = await client.async_validate_application_token()

        channels: list[GotifyMUChannel] = []
        if client_token:
            await client.async_validate_client_token()
            channels = await client.async_get_channels()

        return client, application, channels

    @staticmethod
    def _client_can_access_channel(
        channel_id: int, channels: list[GotifyMUChannel]
    ) -> bool:
        """Return whether a client-token user can access a channel."""
        return any(channel.id == channel_id for channel in channels)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                server_url = normalize_server_url(user_input[CONF_SERVER_URL])
                app_token = user_input[CONF_APP_TOKEN].strip()
                client_token = user_input.get(CONF_CLIENT_TOKEN, "").strip() or None
                verify_ssl = user_input[CONF_VERIFY_SSL]
                if not app_token:
                    raise GotifyMUAuthError("Application token is empty")

                _, application, channels = await self._async_validate(
                    server_url=server_url,
                    app_token=app_token,
                    client_token=client_token,
                    verify_ssl=verify_ssl,
                )

                if (
                    application is not None
                    and client_token
                    and not self._client_can_access_channel(application.id, channels)
                ):
                    errors["base"] = "channel_not_accessible"
            except ValueError:
                errors["base"] = "invalid_url"
            except GotifyMUAuthError:
                errors["base"] = "invalid_auth"
            except GotifyMURateLimitError:
                errors["base"] = "rate_limited"
            except (GotifyMUConnectionError, GotifyMUError):
                errors["base"] = "cannot_connect"
            else:
                if not errors:
                    data: dict[str, Any] = {
                        CONF_SERVER_URL: server_url,
                        CONF_APP_TOKEN: app_token,
                        CONF_VERIFY_SSL: verify_ssl,
                    }
                    if client_token:
                        data[CONF_CLIENT_TOKEN] = client_token

                    if application is not None:
                        data[CONF_CHANNEL_ID] = application.id
                        data[CONF_CHANNEL_NAME] = application.name
                        await self.async_set_unique_id(
                            channel_unique_id(server_url, application.id)
                        )
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=application.name,
                            data=data,
                            options={
                                CONF_DEFAULT_PRIORITY: DEFAULT_PRIORITY,
                                CONF_INBOUND_ENABLED: bool(client_token),
                            },
                        )

                    self._pending = data
                    self._channels = channels
                    return await self.async_step_channel()

        schema = vol.Schema(
            {
                vol.Required(CONF_SERVER_URL): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
                vol.Required(CONF_APP_TOKEN): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(CONF_CLIENT_TOKEN, default=""): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_channel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select or name the channel on servers without app identity API."""
        if self._pending is None:
            return self.async_abort(reason="setup_state_lost")

        if user_input is not None:
            if self._channels:
                channel_id = int(user_input[CONF_CHANNEL_ID])
                selected = next(
                    (channel for channel in self._channels if channel.id == channel_id),
                    None,
                )
                if selected is None:
                    return self.async_abort(reason="channel_not_found")
                channel_name = selected.name
                unique_id = channel_unique_id(
                    self._pending[CONF_SERVER_URL], selected.id
                )
            else:
                channel_id = None
                channel_name = user_input[CONF_CHANNEL_NAME].strip() or DEFAULT_NAME
                unique_id = fallback_unique_id(
                    self._pending[CONF_SERVER_URL], self._pending[CONF_APP_TOKEN]
                )

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            data = dict(self._pending)
            data[CONF_CHANNEL_NAME] = channel_name
            if channel_id is not None:
                data[CONF_CHANNEL_ID] = channel_id

            return self.async_create_entry(
                title=channel_name,
                data=data,
                options={
                    CONF_DEFAULT_PRIORITY: DEFAULT_PRIORITY,
                    CONF_INBOUND_ENABLED: bool(data.get(CONF_CLIENT_TOKEN)),
                },
            )

        if self._channels:
            options = [
                {"value": str(channel.id), "label": channel.name}
                for channel in self._channels
            ]
            schema = vol.Schema(
                {
                    vol.Required(CONF_CHANNEL_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_CHANNEL_NAME, default=DEFAULT_NAME): TextSelector()
                }
            )

        return self.async_show_form(step_id="channel", data_schema=schema)

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reauthenticate an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        has_client_token = bool(entry.data.get(CONF_CLIENT_TOKEN))

        if user_input is not None:
            app_token = user_input[CONF_APP_TOKEN].strip()
            replacement_client_token = user_input.get(CONF_CLIENT_TOKEN, "").strip()
            remove_client_token = bool(
                user_input.get(CONF_REMOVE_CLIENT_TOKEN, False)
            )
            client_token = (
                None
                if remove_client_token
                else replacement_client_token or entry.data.get(CONF_CLIENT_TOKEN)
            )

            try:
                _, application, channels = await self._async_validate(
                    server_url=entry.data[CONF_SERVER_URL],
                    app_token=app_token,
                    client_token=client_token,
                    verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
                )
                configured_channel_id = entry.data.get(CONF_CHANNEL_ID)
                if (
                    application is not None
                    and configured_channel_id is not None
                    and application.id != configured_channel_id
                ):
                    errors["base"] = "wrong_channel"
                elif (
                    configured_channel_id is not None
                    and client_token
                    and not self._client_can_access_channel(
                        configured_channel_id, channels
                    )
                ):
                    errors["base"] = "channel_not_accessible"
            except GotifyMUAuthError:
                errors["base"] = "invalid_auth"
            except GotifyMURateLimitError:
                errors["base"] = "rate_limited"
            except (GotifyMUConnectionError, GotifyMUError):
                errors["base"] = "cannot_connect"
            else:
                if not errors:
                    await self.async_set_unique_id(entry.unique_id)
                    self._abort_if_unique_id_mismatch()

                    data = dict(entry.data)
                    data[CONF_APP_TOKEN] = app_token
                    if client_token:
                        data[CONF_CLIENT_TOKEN] = client_token
                    else:
                        data.pop(CONF_CLIENT_TOKEN, None)
                    if application is not None:
                        data[CONF_CHANNEL_ID] = application.id
                        data[CONF_CHANNEL_NAME] = application.name

                    options = dict(entry.options)
                    if not client_token:
                        options[CONF_INBOUND_ENABLED] = False

                    return self.async_update_reload_and_abort(
                        entry,
                        data=data,
                        options=options,
                    )

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_APP_TOKEN): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_CLIENT_TOKEN, default=""): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
        if has_client_token:
            schema_dict[
                vol.Optional(CONF_REMOVE_CLIENT_TOKEN, default=False)
            ] = BooleanSelector()

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure network settings, display name, and client token."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        has_client_token = bool(entry.data.get(CONF_CLIENT_TOKEN))

        if user_input is not None:
            replacement_client_token = user_input.get(CONF_CLIENT_TOKEN, "").strip()
            remove_client_token = bool(
                user_input.get(CONF_REMOVE_CLIENT_TOKEN, False)
            )
            client_token = (
                None
                if remove_client_token
                else replacement_client_token or entry.data.get(CONF_CLIENT_TOKEN)
            )
            try:
                server_url = normalize_server_url(user_input[CONF_SERVER_URL])
                _, application, channels = await self._async_validate(
                    server_url=server_url,
                    app_token=entry.data[CONF_APP_TOKEN],
                    client_token=client_token,
                    verify_ssl=user_input[CONF_VERIFY_SSL],
                )
                configured_channel_id = entry.data.get(CONF_CHANNEL_ID)
                if (
                    application is not None
                    and configured_channel_id is not None
                    and application.id != configured_channel_id
                ):
                    errors["base"] = "wrong_channel"
                elif (
                    configured_channel_id is not None
                    and client_token
                    and not self._client_can_access_channel(
                        configured_channel_id, channels
                    )
                ):
                    errors["base"] = "channel_not_accessible"
            except ValueError:
                errors["base"] = "invalid_url"
            except GotifyMUAuthError:
                errors["base"] = "invalid_auth"
            except GotifyMURateLimitError:
                errors["base"] = "rate_limited"
            except (GotifyMUConnectionError, GotifyMUError):
                errors["base"] = "cannot_connect"
            else:
                if not errors:
                    await self.async_set_unique_id(entry.unique_id)
                    self._abort_if_unique_id_mismatch()

                    channel_name = (
                        user_input[CONF_CHANNEL_NAME].strip()
                        or (application.name if application is not None else entry.title)
                    )
                    data = dict(entry.data)
                    data.update(
                        {
                            CONF_SERVER_URL: server_url,
                            CONF_CHANNEL_NAME: channel_name,
                            CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                        }
                    )
                    if application is not None:
                        data[CONF_CHANNEL_ID] = application.id
                    if client_token:
                        data[CONF_CLIENT_TOKEN] = client_token
                    else:
                        data.pop(CONF_CLIENT_TOKEN, None)

                    options = dict(entry.options)
                    if not client_token:
                        options[CONF_INBOUND_ENABLED] = False

                    return self.async_update_reload_and_abort(
                        entry,
                        title=channel_name,
                        data=data,
                        options=options,
                    )

        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_SERVER_URL, default=entry.data[CONF_SERVER_URL]
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            vol.Required(
                CONF_CHANNEL_NAME,
                default=entry.data.get(CONF_CHANNEL_NAME, entry.title),
            ): TextSelector(),
            vol.Required(
                CONF_VERIFY_SSL,
                default=entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            ): BooleanSelector(),
            vol.Optional(CONF_CLIENT_TOKEN, default=""): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
        if has_client_token:
            schema_dict[
                vol.Optional(CONF_REMOVE_CLIENT_TOKEN, default=False)
            ] = BooleanSelector()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> GotifyMUOptionsFlow:
        """Create the options flow."""
        return GotifyMUOptionsFlow()


class GotifyMUOptionsFlow(config_entries.OptionsFlowWithReload):
    """Handle Monita options and native pairing."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options navigation menu."""
        del user_input
        state = (
            "Paired"
            if native_pairing_is_configured(dict(self.config_entry.data))
            else "Not paired"
        )
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "native_pairing"],
            description_placeholders={"native_state": state},
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage existing notification and inbound stream options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_DEFAULT_PRIORITY,
                default=self.config_entry.options.get(
                    CONF_DEFAULT_PRIORITY, DEFAULT_PRIORITY
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=10,
                    step=1,
                    mode=NumberSelectorMode.SLIDER,
                )
            )
        }
        if self.config_entry.data.get(CONF_CLIENT_TOKEN):
            schema_dict[
                vol.Required(
                    CONF_INBOUND_ENABLED,
                    default=self.config_entry.options.get(
                        CONF_INBOUND_ENABLED, DEFAULT_INBOUND_ENABLED
                    ),
                )
            ] = BooleanSelector()

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(schema_dict),
        )

    async def async_step_native_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the native Monita pairing state."""
        del user_input
        if not native_pairing_is_configured(dict(self.config_entry.data)):
            return await self.async_step_native_pair()
        return self.async_show_menu(
            step_id="native_pairing",
            menu_options=["native_repair", "native_remove"],
        )

    async def async_step_native_repair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace an existing native pairing without deleting the integration."""
        return await self.async_step_native_pair(user_input)

    async def async_step_native_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pair this config entry with a Monita native HA connection."""
        errors: dict[str, str] = {}
        webhook_id = webhook.async_generate_id()
        auto_webhook_url: str | None
        try:
            auto_webhook_url = webhook.async_generate_url(
                self.hass,
                webhook_id,
                allow_internal=True,
                allow_external=True,
                prefer_external=True,
            )
        except NoURLAvailableError:
            auto_webhook_url = None

        if user_input is not None:
            pairing_code = user_input[CONF_NATIVE_PAIRING_CODE].strip()
            override_url = user_input.get(CONF_HOME_ASSISTANT_URL, "").strip()
            if not pairing_code:
                errors["base"] = "invalid_pairing_code"
            else:
                try:
                    if override_url:
                        base_url = normalize_server_url(override_url)
                        webhook_url = (
                            f"{base_url}{webhook.async_generate_path(webhook_id)}"
                        )
                    elif auto_webhook_url is not None:
                        webhook_url = auto_webhook_url
                    else:
                        raise ValueError("Home Assistant callback URL is required")

                    pending = PendingNativeWebhook(self.hass, webhook_id)
                    pending.async_register()
                    try:
                        result = await async_pair_native(
                            async_get_clientsession(self.hass),
                            server_url=self.config_entry.data[CONF_SERVER_URL],
                            verify_ssl=self.config_entry.data.get(
                                CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL
                            ),
                            pairing_code=pairing_code,
                            webhook_url=webhook_url,
                        )
                        pending.async_activate(result.secret)
                        data = remove_native_pairing_data(dict(self.config_entry.data))
                        data.update(
                            native_pairing_data(
                                result,
                                webhook_id=webhook_id,
                                webhook_url=webhook_url,
                            )
                        )
                        self.hass.config_entries.async_update_entry(
                            self.config_entry, data=data
                        )
                        async_delete_native_bridge_repair_issue(
                            self.hass, self.config_entry.entry_id
                        )
                    finally:
                        pending.async_unregister()
                except ValueError:
                    errors["base"] = "invalid_ha_url"
                except GotifyMUNativePairingError as err:
                    errors["base"] = err.reason
                else:
                    self.hass.config_entries.async_schedule_reload(
                        self.config_entry.entry_id
                    )
                    return self.async_create_entry(
                        data=dict(self.config_entry.options)
                    )

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_NATIVE_PAIRING_CODE): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            )
        }
        if auto_webhook_url is None:
            schema_dict[vol.Required(CONF_HOME_ASSISTANT_URL)] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            )
        else:
            schema_dict[vol.Optional(CONF_HOME_ASSISTANT_URL, default="")] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            )

        return self.async_show_form(
            step_id="native_pair",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "auto_url": auto_webhook_url or "Not available",
            },
        )

    async def async_step_native_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Revoke and remove native pairing while keeping the normal MU entry."""
        errors: dict[str, str] = {}
        if user_input is not None and user_input.get("confirm"):
            force_local = bool(user_input.get(CONF_FORCE_LOCAL_REMOVE, False))
            try:
                await async_revoke_native(
                    async_get_clientsession(self.hass),
                    server_url=self.config_entry.data[CONF_SERVER_URL],
                    verify_ssl=self.config_entry.data.get(
                        CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL
                    ),
                    integration_id=int(
                        self.config_entry.data[CONF_NATIVE_INTEGRATION_ID]
                    ),
                    secret=self.config_entry.data[CONF_NATIVE_SECRET],
                )
            except (KeyError, TypeError, ValueError):
                if not force_local:
                    errors["base"] = "unpair_failed"
            except GotifyMUNativePairingError as err:
                if not force_local:
                    errors["base"] = err.reason

            if not errors:
                data = remove_native_pairing_data(dict(self.config_entry.data))
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=data
                )
                async_delete_native_bridge_repair_issue(
                    self.hass, self.config_entry.entry_id
                )
                self.hass.config_entries.async_schedule_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(
                    data=dict(self.config_entry.options)
                )

        return self.async_show_form(
            step_id="native_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm", default=False): BooleanSelector(),
                    vol.Optional(
                        CONF_FORCE_LOCAL_REMOVE, default=False
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
        )
