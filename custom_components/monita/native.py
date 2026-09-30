"""Native Home Assistant bridge support for Monita."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
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
from .repairs import (
    async_create_native_bridge_repair_issue,
    async_delete_native_bridge_repair_issue,
)

_LOGGER = logging.getLogger(__name__)

NATIVE_PAIR_PATH = "/integrations/home-assistant/native/pair"
_NATIVE_QUEUE_MAXSIZE = 4096
_NATIVE_RETRY_ATTEMPTS = 4
_NATIVE_RETRY_BASE_SECONDS = 1
_NATIVE_RETRY_MAX_SECONDS = 8

BridgeStatusCallback = Callable[[], None]


class MonitaNativeError(Exception):
    """Base native bridge error."""


class MonitaNativePairingError(MonitaNativeError):
    """Native pairing or unpairing failed with a user-facing reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class NativePairingResult:
    """Native pairing credentials returned by Monita."""

    integration_id: int
    secret: str
    event_path: str


@dataclass(frozen=True, slots=True)
class _NativeDeliveryResult:
    """Result of one native event delivery attempt."""

    success: bool
    retryable: bool = False
    repair_required: bool = False
    error: str | None = None


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
    """Exchange a one-time Monita pairing code for bridge credentials."""
    try:
        async with session.post(
            f"{server_url.rstrip('/')}{NATIVE_PAIR_PATH}",
            json={"pairingCode": pairing_code, "webhookUrl": webhook_url},
            ssl=verify_ssl,
            timeout=ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
        ) as response:
            if response.status in (400, 401, 403, 404):
                raise MonitaNativePairingError("invalid_pairing_code")
            if response.status == 410:
                raise MonitaNativePairingError("pairing_expired")
            if response.status == 429:
                raise MonitaNativePairingError("rate_limited")
            if response.status >= 500:
                raise MonitaNativePairingError("cannot_connect")
            if response.status < 200 or response.status >= 300:
                raise MonitaNativePairingError("pairing_failed")

            try:
                payload = await response.json(content_type=None)
            except (ClientError, UnicodeError, json.JSONDecodeError) as err:
                raise MonitaNativePairingError("pairing_failed") from err

            if not isinstance(payload, dict):
                raise MonitaNativePairingError("pairing_failed")

            try:
                integration_id = int(payload["integrationId"])
                secret = str(payload["secret"]).strip()
                event_path = str(payload["eventPath"]).strip()
            except (KeyError, TypeError, ValueError) as err:
                raise MonitaNativePairingError("pairing_failed") from err

            if integration_id < 1 or not secret or not event_path.startswith("/"):
                raise MonitaNativePairingError("pairing_failed")

            return NativePairingResult(
                integration_id=integration_id,
                secret=secret,
                event_path=event_path,
            )
    except MonitaNativePairingError:
        raise
    except (ClientConnectionError, ClientError, TimeoutError) as err:
        raise MonitaNativePairingError("cannot_connect") from err


async def async_revoke_native(
    session: ClientSession,
    *,
    server_url: str,
    verify_ssl: bool,
    integration_id: int,
    secret: str,
) -> None:
    """Revoke a native bridge on Monita before clearing local credentials."""
    try:
        async with session.delete(
            f"{server_url.rstrip('/')}/integrations/home-assistant/native/{integration_id}",
            headers={"Authorization": f"Bearer {secret}"},
            ssl=verify_ssl,
            timeout=ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
        ) as response:
            if 200 <= response.status < 300:
                return
            if response.status in (401, 403):
                raise MonitaNativePairingError("unpair_auth_failed")
            if response.status == 404:
                raise MonitaNativePairingError("unpair_not_found")
            if response.status == 429:
                raise MonitaNativePairingError("rate_limited")
            if response.status >= 500:
                raise MonitaNativePairingError("cannot_unpair")
            raise MonitaNativePairingError("unpair_failed")
    except MonitaNativePairingError:
        raise
    except (ClientConnectionError, ClientError, TimeoutError) as err:
        raise MonitaNativePairingError("cannot_unpair") from err


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
    on_received: Callable[[], None] | None = None,
) -> web.Response:
    """Validate and deliver one Monita -> Home Assistant event."""
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

    if on_received is not None:
        on_received()
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
        """Register the temporary endpoint before contacting Monita."""
        webhook.async_register(
            self._hass,
            DOMAIN,
            "Monita native pairing",
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


class MonitaNativeBridge:
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
        entry_id: str | None = None,
    ) -> None:
        self._hass = hass
        self._session = session
        self._name = name
        self._server_url = server_url.rstrip("/")
        self._verify_ssl = verify_ssl
        self._secret = secret
        self._event_path = event_path
        self._webhook_id = webhook_id
        self._entry_id = entry_id or webhook_id
        self._queue: asyncio.Queue[Event[Any]] = asyncio.Queue(
            maxsize=_NATIVE_QUEUE_MAXSIZE
        )
        self._remove_listener: Callable[[], None] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._suppress_context_ids: set[str] = set()
        self._status_listeners: set[BridgeStatusCallback] = set()
        self._stopped = False
        self._queue_warning_emitted = False
        self.status = "paired"
        self.last_sent_at: datetime | None = None
        self.last_received_at: datetime | None = None
        self.last_error: str | None = None
        self.retry_count = 0
        self.dropped_events = 0

    @property
    def is_connected(self) -> bool:
        """Return whether the native bridge is presently healthy."""
        return self.status in ("paired", "connected")

    @property
    def repair_required(self) -> bool:
        """Return whether Monita rejected the stored native credential."""
        return self.status == "repair_required"

    @property
    def queued_events(self) -> int:
        """Return the number of Home Assistant events waiting for delivery."""
        return self._queue.qsize()

    @callback
    def async_subscribe_status(
        self, listener: BridgeStatusCallback
    ) -> Callable[[], None]:
        """Subscribe to native bridge status changes."""
        self._status_listeners.add(listener)

        @callback
        def remove_listener() -> None:
            self._status_listeners.discard(listener)

        return remove_listener

    @callback
    def _async_notify_status(self) -> None:
        for listener in tuple(self._status_listeners):
            listener()

    @callback
    def _async_mark_connected(
        self, *, sent: bool = False, received: bool = False
    ) -> None:
        async_delete_native_bridge_repair_issue(self._hass, self._entry_id)
        changed = self.status != "connected" or self.last_error is not None
        self.status = "connected"
        self.last_error = None
        now = _utcnow()
        if sent:
            self.last_sent_at = now
            changed = True
        if received:
            self.last_received_at = now
            changed = True
        if changed:
            self._async_notify_status()

    @callback
    def _async_mark_degraded(self, error: str) -> None:
        if self.status != "degraded" or self.last_error != error:
            self.status = "degraded"
            self.last_error = error
            self._async_notify_status()

    @callback
    def _async_mark_repair_required(self, error: str) -> None:
        async_create_native_bridge_repair_issue(
            self._hass,
            entry_id=self._entry_id,
            name=self._name,
        )
        if self.status != "repair_required" or self.last_error != error:
            self.status = "repair_required"
            self.last_error = error
            self._async_notify_status()

    @callback
    def async_start(self) -> None:
        """Register the webhook and start forwarding Home Assistant events."""
        webhook.async_register(
            self._hass,
            DOMAIN,
            f"Monita native bridge: {self._name}",
            self._webhook_id,
            self._async_handle_webhook,
            local_only=False,
            allowed_methods=["POST"],
        )
        self._remove_listener = self._hass.bus.async_listen(
            MATCH_ALL, self._async_queue_event
        )
        self._worker = self._hass.async_create_background_task(
            self._async_worker(), f"Monita native bridge: {self._name}"
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
            on_received=lambda: self._async_mark_connected(received=True),
        )

    @callback
    def _async_queue_event(self, event: Event[Any]) -> None:
        if self._stopped or event.context.id in self._suppress_context_ids:
            return
        try:
            self._queue.put_nowait(event)
            self._queue_warning_emitted = False
            self._async_notify_status()
        except asyncio.QueueFull:
            self.dropped_events += 1
            error = "Native event queue is full; new events are being dropped"
            self._async_mark_degraded(error)
            if not self._queue_warning_emitted:
                _LOGGER.warning("%s for %s", error, self._name)
                self._queue_warning_emitted = True

    async def _async_worker(self) -> None:
        try:
            while True:
                event = await self._queue.get()
                try:
                    await self._async_post_event(event)
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # Defensive: never destabilize the HA event bus.
                    self.dropped_events += 1
                    self._async_mark_degraded(str(err))
                    _LOGGER.debug(
                        "Monita native event delivery failed for %s: %s",
                        self._name,
                        err,
                    )
                finally:
                    self._queue.task_done()
                    self._async_notify_status()
        except asyncio.CancelledError:
            raise

    async def _async_post_event(self, event: Event[Any]) -> bool:
        """Post an event with bounded retry/backoff for transient failures."""
        try:
            body = json_bytes(
                {"eventType": event.event_type, "data": dict(event.data)}
            )
        except (TypeError, ValueError) as err:
            self.dropped_events += 1
            self._async_mark_degraded(
                f"Could not serialize Home Assistant event {event.event_type}"
            )
            _LOGGER.debug(
                "Skipping unserializable Home Assistant event %s for %s: %s",
                event.event_type,
                self._name,
                err,
            )
            return False

        delay = _NATIVE_RETRY_BASE_SECONDS
        last_error = "Native event delivery failed"
        for attempt in range(1, _NATIVE_RETRY_ATTEMPTS + 1):
            result = await self._async_post_body(body)
            if result.success:
                self._async_mark_connected(sent=True)
                return True
            last_error = result.error or last_error
            if result.repair_required:
                self.dropped_events += 1
                self._async_mark_repair_required(last_error)
                return False
            if not result.retryable:
                self.dropped_events += 1
                self._async_mark_degraded(last_error)
                return False
            if attempt < _NATIVE_RETRY_ATTEMPTS:
                self.retry_count += 1
                self._async_notify_status()
                await asyncio.sleep(delay)
                delay = min(delay * 2, _NATIVE_RETRY_MAX_SECONDS)

        self.dropped_events += 1
        self._async_mark_degraded(last_error)
        return False

    async def _async_post_body(self, body: bytes) -> _NativeDeliveryResult:
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
                if 200 <= response.status < 300:
                    return _NativeDeliveryResult(success=True)
                error = f"Monita returned HTTP {response.status} for native event delivery"
                if response.status in (401, 403):
                    return _NativeDeliveryResult(
                        success=False,
                        repair_required=True,
                        error=error,
                    )
                if response.status in (408, 429) or response.status >= 500:
                    return _NativeDeliveryResult(
                        success=False,
                        retryable=True,
                        error=error,
                    )
                return _NativeDeliveryResult(success=False, error=error)
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            return _NativeDeliveryResult(
                success=False,
                retryable=True,
                error=f"Could not connect to Monita: {err}",
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
        self._status_listeners.clear()
