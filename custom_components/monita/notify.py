"""Notify platform for Monita."""

from __future__ import annotations

from typing import override

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MonitaConfigEntry
from .api import (
    MonitaAuthError,
    MonitaChannel,
    MonitaConnectionError,
    MonitaError,
    MonitaRateLimitError,
)
from .const import (
    CONF_CHANNEL_ID,
    CONF_DEFAULT_PRIORITY,
    CONF_SERVER_URL,
    DEFAULT_PRIORITY,
    DOMAIN,
    INTEGRATION_ORIGIN_EXTRA,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MonitaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Expose one notification entity for every selected push-capable Channel."""
    runtime = entry.runtime_data
    entities: list[MonitaNotifyEntity] = []

    for channel_id in runtime.active_channel_ids:
        channel = runtime.channel(channel_id)
        if channel is None:
            if channel_id != runtime.channel_id:
                continue
            channel = MonitaChannel(
                id=channel_id,
                name=runtime.channel_name,
                role="owner",
            )

        legacy_app_channel = bool(
            runtime.client.app_token
            and runtime.channel_id is not None
            and channel.id == runtime.channel_id
        )
        if (
            runtime.client.client_token
            and not channel.can_post
            and not legacy_app_channel
        ):
            continue

        entities.append(
            MonitaNotifyEntity(
                entry,
                channel,
                use_legacy_app_token=legacy_app_channel,
            )
        )

    if entities:
        async_add_entities(entities)


class MonitaNotifyEntity(NotifyEntity):
    """One Monita Channel exposed as a Home Assistant notify entity."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:message-badge"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(
        self,
        entry: MonitaConfigEntry,
        channel: MonitaChannel,
        *,
        use_legacy_app_token: bool = False,
    ) -> None:
        """Initialize the notify entity."""
        self._entry = entry
        self._channel = channel
        self._use_legacy_app_token = use_legacy_app_token
        self._attr_name = channel.name

        legacy_channel_id = entry.data.get(CONF_CHANNEL_ID)
        if (
            legacy_channel_id is not None
            and int(legacy_channel_id) == channel.id
            and entry.unique_id
            and "|channel:" in entry.unique_id
        ):
            self._attr_unique_id = f"{entry.unique_id}_notify"
        else:
            self._attr_unique_id = f"{entry.unique_id}_channel_{channel.id}_notify"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Monita",
            model="Notification Server",
            configuration_url=entry.data[CONF_SERVER_URL],
        )

    @property
    def channel_id(self) -> int:
        """Return the Monita Channel ID represented by this entity."""
        return self._channel.id

    @property
    @override
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose non-secret Channel metadata."""
        return {
            "channel_id": self._channel.id,
            "channel_name": self._channel.name,
            "channel_role": self._channel.role or None,
            "channel_type": self._channel.channel_type or None,
        }

    @override
    async def async_send_message(
        self,
        message: str,
        title: str | None = None,
    ) -> None:
        """Push a message to this Monita Channel."""
        priority = self._entry.options.get(
            CONF_DEFAULT_PRIORITY,
            DEFAULT_PRIORITY,
        )
        try:
            kwargs = {
                "title": title,
                "priority": priority,
                "extras": {
                    INTEGRATION_ORIGIN_EXTRA: {
                        "entry_id": self._entry.entry_id,
                        "channel_id": self._channel.id,
                        "source": "monita-ha",
                    }
                },
            }
            if (
                self._entry.runtime_data.client.client_token
                and not self._use_legacy_app_token
            ):
                kwargs["channel_id"] = self._channel.id

            await self._entry.runtime_data.client.async_send(
                message,
                **kwargs,
            )
        except MonitaAuthError as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Monita rejected the configured credential") from err
        except MonitaRateLimitError as err:
            raise HomeAssistantError("Monita rate limited the notification") from err
        except MonitaConnectionError as err:
            raise HomeAssistantError(f"Could not connect to Monita: {err}") from err
        except MonitaError as err:
            raise HomeAssistantError(str(err)) from err
