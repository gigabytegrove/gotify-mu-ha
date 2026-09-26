"""Native Home Assistant bridge support for Gotify MU."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientConnectionError, ClientError, ClientSession, ClientTimeout, web
from homeassistant.components import webhook
from homeassistant.const import MATCH_ALL
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers.json import json_bytes

from .const import (
    CONF_NATIVE_EVENT_PATH,
    CONF_NATIVE_INTEGRATION_ID,
    CONF_NATIVE_SECRET,
    CONF_NATIVE_WEBHOOK_ID,
    CONF_NATIVE_WEBHOOK_URL,
    DOMAIN,
    REQUEST_TIMEOUT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

NATIVE_PAIR_PATH = "/integrations/home-assistant/native/pair"
_NATIVE_QUEUE_MAXSIZE = 4096


class GotifyMUNativeError(Exception):
    """Base native bridge error."""


class GotifyMUNativePairingError(GotifyMUNativeError):
    """Native pairing failed with a user-facing reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class NativePairingResult:
    """Native pairing credentials returned by Gotify MU."""

    integration_id: int
    secret: str
    event_path: str


def native_pairing_is_configured(data: dict[str, Any]) -> bool:
    """Return whether all native bridge credentials are stored."""
    return bool(
        data.get(CONF_NATIVE_INTEGRATION_ID) is not None
        and data.get(CONF_NATIVE_SECRET)
        and data.get(CONF_NATIVE_EVENT_PATH)
        and data.get(CONF_NATIVE_WEBHOOK_ID)
        and data.get(CONF_NATIVE_WEBHOOK_URL)
    )


def native_pairing_data(
    result: NativePairingResult,
    *,
    webhook_id: str,
    webhook_url: str,
) -> dict[str, Any]:
    """Build config-entry data for a successful native pairing."""
    return {
        CONF_NATIVE_INTEGRATION_ID: result.integration_id,
        CONF_NATIVE_SECRET: result.secret,
        CONF_NATIVE_EVENT_PATH: result.event_path,
        CONF_NATIVE_WEBHOOK_ID: webhook_id,
        CONF_NATIVE_WEBHOOK_URL: webhook_url,
    }


def remove_native_pairing_data(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of config-entry data with native credentials removed."""
    cleaned = dict(data)
    for key in (
        CONF_NATIVE_INTEGRATION_ID,
        CONF_NATIVE_SECRET,
        CONF_NATIVE_EVENT_PATH,
        CONF_NATIVE_WEBHOOK_ID,
        CONF_NATIVE_WEBHOOK_URL,
    ):
        cleaned.pop(key, None)
    return cleaned


async def async_pair_native(
    session: ClientSession,
    *,
    server_url: str,
    verify_ssl: bool,
    pairing_code: str,
    webhook_url: str,
) -> NativePairingResult:
    """Exchange a one-time Gotify MU pairing code for bridge credentials."""
    try:
        async with session.post(
            f"{server_url.rstrip('/')}{NATIVE_PAIR_PATH}",
            json={"pairingCode": pairing_code, "webhookUrl": webhook_url},
            ssl=verify_ssl,
            timeout=ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
        ) as response:
            if response.status == 400:
                raise GotifyMUNativePairingError("invalid_pairing_code")
            if response.status == 410:
                raise GotifyMUNativePairingError("pairing_expired")
            if response.status == 429:
                raise GotifyMUNativePairingError("rate_limited")
            if response.status >= 500:
                raise GotifyMUNativePairingError("cannot_connect")
            if response.status < 200 or response.status >= 300:
                raise GotifyMUNativePairingError("pairing_failed")

            try:
                payload = await response.json(content_type=None)
            except (ClientError, UnicodeError, json.JSONDecodeError) as err:
                raise GotifyMUNativePairingError("pairing_failed") from err

            if not isinstance(payload, dict):
                raise GotifyMUNativePairingError("pairing_failed")

            try:
                integration_id = int(payload["integrationId"])
                secret = str(payload["secret"]).strip()
                event_path = str(payload["eventPath"]).strip()
            except (KeyError, TypeError, ValueError) as err:
                raise GotifyMUNativePairingError("pairing_failed") from err

            if integration_id < 1 or not secret or not event_path.startswith("/"):
                raise GotifyMUNativePairingError("pairing_failed")

            return NativePairingResult(
                integration_id=integration_id,
                secret=secret,
                event_path=event_path,
            )
    except GotifyMUNativePairingError:
        raise
    except (ClientConnectionError, ClientError, TimeoutError) as err:
        raise GotifyMUNativePairingError("cannot_connect") from err


def _bearer_token(request: web.Request) -> str | None:
    """Extract a Bearer token without logging or transforming it."""
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        return None
    token = header[len(prefix) :]
    return token if token else None


async def async_handle_native_webhook(
    hass: HomeAssistant,
    request: web.Request,
    *,
    secret: str,
    suppress_context_ids: set[str] | None = None,
) -> web.Response:
    """Validate and deliver one Gotify MU -> Home Assistant event."""
    supplied = _bearer_token(request)
    if supplied is None or not secrets.compare_digest(supplied, secret):
        return web.Response(status=401)

    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError, TypeError):
        return web.Response(status=400)

    if not isinstance(payload, dict):
        return web.Response(status=400)
    event_type = payload.get("eventType")
    data = payload.get("data", {})
    if (
        not isinstance(event_type, str)
        or not event_type.strip()
        or not isinstance(data, dict)
    ):
        return web.Response(status=400)

    context = Context()
    if suppress_context_ids is not None:
        suppress_context_ids.add(context.id)

    try:
        hass.bus.async_fire(event_type.strip(), data, context=context)
    except (TypeError, ValueError):
        if suppress_context_ids is not None:
            suppress_context_ids.discard(context.id)
        return web.Response(status=400)

    if suppress_context_ids is not None:
        hass.loop.call_soon(suppress_context_ids.discard, context.id)
    return web.Response(status=200)


class PendingNativeWebhook:
    """Temporary webhook registration used while a pairing request is in flight."""

    def __init__(self, hass: HomeAssistant, webhook_id: str) -> None:
        self._hass = hass
        self._webhook_id = webhook_id
        self._secret: str | None = None
        self._registered = False

    @callback
    def async_register(self) -> None:
        """Register the temporary endpoint before contacting Gotify MU."""
        webhook.async_register(
            self._hass,
            DOMAIN,
            "Gotify MU native pairing",
            self._webhook_id,
            self._async_handle,
            local_only=False,
            allowed_methods=["POST"],
        )
        self._registered = True

    @callback
    def async_activate(self, secret: str) -> None:
        """Allow the just-issued secret during the short pairing handoff window."""
        self._secret = secret

    async def _async_handle(
        self,
        hass: HomeAssistant,
        webhook_id: str,
        request: web.Request,
    ) -> web.Response:
        del webhook_id
        if self._secret is None:
            return web.Response(status=503)
        return await async_handle_native_webhook(hass, request, secret=self._secret)

    @callback
    def async_unregister(self) -> None:
        """Remove the temporary endpoint."""
        if self._registered:
            webhook.async_unregister(self._hass, self._webhook_id)
            self._registered = False


class GotifyMUNativeBridge:
    """Persistent bidirectional event bridge for one paired config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        *,
        name: str,
        server_url: str,
        verify_ssl: bool,
        secret: str,
        event_path: str,
        webhook_id: str,
    ) -> None:
        self._hass = hass
        self._session = session
        self._name = name
        self._server_url = server_url.rstrip("/")
        self._verify_ssl = verify_ssl
        self._secret = secret
        self._event_path = event_path
        self._webhook_id = webhook_id
        self._queue: asyncio.Queue[Event[Any] | None] = asyncio.Queue(
            maxsize=_NATIVE_QUEUE_MAXSIZE
        )
        self._remove_listener: Callable[[], None] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._suppress_context_ids: set[str] = set()
        self._stopped = False
        self._queue_warning_emitted = False

    @callback
    def async_start(self) -> None:
        """Register the webhook and start forwarding Home Assistant events."""
        webhook.async_register(
            self._hass,
            DOMAIN,
            f"Gotify MU native bridge: {self._name}",
            self._webhook_id,
            self._async_handle_webhook,
            local_only=False,
            allowed_methods=["POST"],
        )
        self._remove_listener = self._hass.bus.async_listen(
            MATCH_ALL, self._async_queue_event
        )
        self._worker = self._hass.async_create_background_task(
            self._async_worker(), f"Gotify MU native bridge: {self._name}"
        )

    async def _async_handle_webhook(
        self,
        hass: HomeAssistant,
        webhook_id: str,
        request: web.Request,
    ) -> web.Response:
        del webhook_id
        return await async_handle_native_webhook(
            hass,
            request,
            secret=self._secret,
            suppress_context_ids=self._suppress_context_ids,
        )

    @callback
    def _async_queue_event(self, event: Event[Any]) -> None:
        if self._stopped or event.context.id in self._suppress_context_ids:
            return
        try:
            self._queue.put_nowait(event)
            self._queue_warning_emitted = False
        except asyncio.QueueFull:
            if not self._queue_warning_emitted:
                _LOGGER.warning(
                    "Gotify MU native event queue is full for %s; new events are being dropped",
                    self._name,
                )
                self._queue_warning_emitted = True

    async def _async_worker(self) -> None:
        try:
            while True:
                event = await self._queue.get()
                if event is None:
                    return
                try:
                    await self._async_post_event(event)
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # Defensive: never destabilize the HA event bus.
                    _LOGGER.debug(
                        "Gotify MU native event delivery failed for %s: %s",
                        self._name,
                        err,
                    )
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            raise

    async def _async_post_event(self, event: Event[Any]) -> None:
        try:
            body = json_bytes(
                {"eventType": event.event_type, "data": dict(event.data)}
            )
        except (TypeError, ValueError) as err:
            _LOGGER.debug(
                "Skipping unserializable Home Assistant event %s for %s: %s",
                event.event_type,
                self._name,
                err,
            )
            return

        try:
            async with self._session.post(
                f"{self._server_url}{self._event_path}",
                data=body,
                headers={
                    "Authorization": f"Bearer {self._secret}",
                    "Content-Type": "application/json",
                },
                ssl=self._verify_ssl,
                timeout=ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as response:
                if response.status in (401, 403):
                    _LOGGER.warning(
                        "Gotify MU rejected the native bridge credential for %s; repair pairing",
                        self._name,
                    )
                    return
                if response.status == 429:
                    _LOGGER.debug(
                        "Gotify MU rate limited a native Home Assistant event for %s",
                        self._name,
                    )
                    return
                if response.status < 200 or response.status >= 300:
                    _LOGGER.debug(
                        "Gotify MU returned HTTP %s for a native Home Assistant event for %s",
                        response.status,
                        self._name,
                    )
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            _LOGGER.debug(
                "Could not deliver native Home Assistant event to Gotify MU for %s: %s",
                self._name,
                err,
            )

    @callback
    def async_stop(self) -> None:
        """Unregister listeners/webhook and stop the worker."""
        if self._stopped:
            return
        self._stopped = True
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        webhook.async_unregister(self._hass, self._webhook_id)
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
        self._suppress_context_ids.clear()
