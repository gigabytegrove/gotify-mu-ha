"""Async API client for Gotify MU."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aiohttp import (
    ClientConnectionError,
    ClientError,
    FormData,
    ClientResponse,
    ClientResponseError,
    ClientSession,
    ClientTimeout,
    WSMsgType,
)

from .const import REQUEST_TIMEOUT_SECONDS


class GotifyMUError(Exception):
    """Base Gotify MU API error."""


class GotifyMUAuthError(GotifyMUError):
    """Authentication failed."""


class GotifyMUConnectionError(GotifyMUError):
    """Connection failed."""


class GotifyMURateLimitError(GotifyMUError):
    """The server rate limited the request."""


class GotifyMUServerError(GotifyMUError):
    """The server returned an unexpected error."""


@dataclass(frozen=True, slots=True)
class GotifyMUAttachment:
    """Staged Gotify MU attachment metadata."""

    id: int
    filename: str
    content_type: str
    size: int


@dataclass(frozen=True, slots=True)
class GotifyMUChannel:
    """Gotify MU channel metadata."""

    id: int
    name: str
    description: str = ""
    allow_member_post: bool = False
    auto_assign: bool = False


@dataclass(slots=True)
class GotifyMUClient:
    """Async Gotify MU API client."""

    session: ClientSession
    server_url: str
    app_token: str
    verify_ssl: bool = True
    client_token: str | None = None

    def __post_init__(self) -> None:
        """Normalize constructor values."""
        self.server_url = self.server_url.strip().rstrip("/")
        self.app_token = self.app_token.strip()
        if self.client_token is not None:
            self.client_token = self.client_token.strip() or None

    @property
    def _timeout(self) -> ClientTimeout:
        return ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"X-Gotify-Key": token}

    async def _error_detail(self, response: ClientResponse) -> str:
        try:
            body = (await response.text()).strip()
        except (ClientError, UnicodeError):
            return ""
        if len(body) > 500:
            body = body[:500] + "…"
        return body

    async def _read_json(self, response: ClientResponse) -> Any:
        """Decode a JSON response with a useful server error on malformed data."""
        try:
            return await response.json(content_type=None)
        except (ClientError, UnicodeError, json.JSONDecodeError) as err:
            raise GotifyMUServerError(
                f"Gotify MU returned invalid JSON from {response.url.path}"
            ) from err

    async def _raise_for_status(
        self,
        response: ClientResponse,
        *,
        auth_context: str | None = None,
    ) -> None:
        if response.status in (401, 403):
            context = f" ({auth_context})" if auth_context else ""
            raise GotifyMUAuthError(
                f"Gotify MU rejected authentication{context}: HTTP {response.status}"
            )
        if response.status == 429:
            raise GotifyMURateLimitError("Gotify MU rate limited the request")
        if response.status >= 500:
            detail = await self._error_detail(response)
            suffix = f": {detail}" if detail else ""
            raise GotifyMUServerError(
                f"Gotify MU returned HTTP {response.status}{suffix}"
            )
        try:
            response.raise_for_status()
        except ClientResponseError as err:
            detail = await self._error_detail(response)
            suffix = f": {detail}" if detail else ""
            raise GotifyMUError(
                f"Gotify MU returned HTTP {response.status}{suffix}"
            ) from err

    @staticmethod
    def _parse_channel(data: Any) -> GotifyMUChannel:
        if not isinstance(data, dict):
            raise GotifyMUServerError("Gotify MU returned invalid channel metadata")
        try:
            channel_id = int(data["id"])
            name = str(data["name"])
        except (KeyError, TypeError, ValueError) as err:
            raise GotifyMUServerError(
                "Gotify MU returned incomplete channel metadata"
            ) from err
        return GotifyMUChannel(
            id=channel_id,
            name=name,
            description=str(data.get("description", "")),
            allow_member_post=bool(data.get("allowMemberPost", False)),
            auto_assign=bool(data.get("autoAssign", False)),
        )

    async def async_health(self) -> dict[str, Any]:
        """Return health information from the server."""
        try:
            async with self.session.get(
                f"{self.server_url}/health",
                ssl=self.verify_ssl,
                timeout=self._timeout,
            ) as response:
                await self._raise_for_status(response)
                data = await self._read_json(response)
                return data if isinstance(data, dict) else {}
        except GotifyMUError:
            raise
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err

    async def async_version(self) -> dict[str, Any]:
        """Return server version information when available."""
        try:
            async with self.session.get(
                f"{self.server_url}/version",
                ssl=self.verify_ssl,
                timeout=self._timeout,
            ) as response:
                await self._raise_for_status(response)
                data = await self._read_json(response)
                return data if isinstance(data, dict) else {}
        except GotifyMUError:
            raise
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err

    async def async_validate_application_token(self) -> GotifyMUChannel | None:
        """Validate the application token without creating a notification.

        Newer Gotify MU versions expose GET /application/current for exact token
        identity. Older versions are validated safely by POSTing an empty JSON
        body to /message. Gotify authenticates before binding that request body,
        so a valid token returns HTTP 400 before message persistence while an
        invalid token returns HTTP 401/403.
        """
        try:
            async with self.session.get(
                f"{self.server_url}/application/current",
                headers=self._headers(self.app_token),
                ssl=self.verify_ssl,
                timeout=self._timeout,
            ) as response:
                if response.status == 404:
                    return await self._async_validate_application_token_legacy()
                await self._raise_for_status(response, auth_context="application token")
                data = await self._read_json(response)
                return self._parse_channel(data)
        except GotifyMUError:
            raise
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err

    async def _async_validate_application_token_legacy(self) -> None:
        """Validate an app token against Gotify-compatible servers without identity API."""
        try:
            async with self.session.post(
                f"{self.server_url}/message",
                headers=self._headers(self.app_token),
                json={},
                ssl=self.verify_ssl,
                timeout=self._timeout,
            ) as response:
                if response.status in (401, 403):
                    raise GotifyMUAuthError(
                        f"Gotify MU rejected the application token: HTTP {response.status}"
                    )
                if response.status == 400:
                    return None
                await self._raise_for_status(response, auth_context="application token")
                raise GotifyMUServerError(
                    "Gotify MU unexpectedly accepted an empty message payload"
                )
        except GotifyMUError:
            raise
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err

    async def async_validate_client_token(self) -> dict[str, Any]:
        """Validate the optional client token and return the current user."""
        if not self.client_token:
            raise GotifyMUAuthError("No Gotify MU client token is configured")
        try:
            async with self.session.get(
                f"{self.server_url}/current/user",
                headers=self._headers(self.client_token),
                ssl=self.verify_ssl,
                timeout=self._timeout,
            ) as response:
                await self._raise_for_status(response, auth_context="client token")
                data = await self._read_json(response)
                if not isinstance(data, dict):
                    raise GotifyMUServerError("Gotify MU returned invalid user metadata")
                return data
        except GotifyMUError:
            raise
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err

    async def async_get_channels(self) -> list[GotifyMUChannel]:
        """Return channels accessible to the client-token user."""
        if not self.client_token:
            return []
        try:
            async with self.session.get(
                f"{self.server_url}/application",
                headers=self._headers(self.client_token),
                ssl=self.verify_ssl,
                timeout=self._timeout,
            ) as response:
                await self._raise_for_status(response, auth_context="client token")
                raw = await self._read_json(response)
                if not isinstance(raw, list):
                    raise GotifyMUServerError("Gotify MU returned invalid channel metadata")
                channels: list[GotifyMUChannel] = []
                for item in raw:
                    try:
                        channels.append(self._parse_channel(item))
                    except GotifyMUServerError:
                        continue
                return channels
        except GotifyMUError:
            raise
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err

    async def async_upload_image(
        self,
        image: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> GotifyMUAttachment:
        """Upload image bytes to the staged attachment endpoint."""
        form = FormData()
        form.add_field(
            "file",
            image,
            filename=filename,
            content_type=content_type,
        )

        try:
            async with self.session.post(
                f"{self.server_url}/application/current/attachment",
                headers=self._headers(self.app_token),
                data=form,
                ssl=self.verify_ssl,
                timeout=self._timeout,
            ) as response:
                await self._raise_for_status(response, auth_context="application token")
                data = await self._read_json(response)
                if not isinstance(data, dict):
                    raise GotifyMUServerError(
                        "Gotify MU returned invalid attachment metadata"
                    )

                raw_id = data.get("id", data.get("attachmentId"))
                try:
                    attachment_id = int(raw_id)
                except (TypeError, ValueError) as err:
                    raise GotifyMUServerError(
                        "Gotify MU returned attachment metadata without a staged ID"
                    ) from err

                returned_filename = data.get("filename")
                returned_content_type = data.get(
                    "contentType",
                    data.get("content_type"),
                )
                return GotifyMUAttachment(
                    id=attachment_id,
                    filename=(
                        str(returned_filename)
                        if returned_filename
                        else filename
                    ),
                    content_type=(
                        str(returned_content_type)
                        if returned_content_type
                        else content_type
                    ),
                    size=len(image),
                )
        except GotifyMUError:
            raise
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err

    async def async_send(
        self,
        message: str,
        *,
        title: str | None = None,
        priority: int = 5,
        markdown: bool = False,
        extras: dict[str, Any] | None = None,
        attachment_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Send a notification through the Gotify-compatible message API."""
        payload: dict[str, Any] = {
            "message": message,
            "priority": priority,
        }
        if title:
            payload["title"] = title
        if attachment_ids:
            payload["attachmentIds"] = [int(attachment_id) for attachment_id in attachment_ids]

        merged_extras: dict[str, Any] = {}
        if extras:
            merged_extras.update(extras)
        if markdown:
            merged_extras.setdefault(
                "client::display",
                {"contentType": "text/markdown"},
            )
        if merged_extras:
            payload["extras"] = merged_extras

        try:
            async with self.session.post(
                f"{self.server_url}/message",
                headers=self._headers(self.app_token),
                json=payload,
                ssl=self.verify_ssl,
                timeout=self._timeout,
            ) as response:
                await self._raise_for_status(response, auth_context="application token")
                data = await self._read_json(response)
                return data if isinstance(data, dict) else {}
        except GotifyMUError:
            raise
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err

    def _stream_url(self) -> str:
        parsed = urlsplit(self.server_url)
        if parsed.scheme not in ("http", "https"):
            raise GotifyMUConnectionError(
                "Gotify MU server URL must use http:// or https://"
            )
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = parsed.path.rstrip("/") + "/stream"
        return urlunsplit((scheme, parsed.netloc, path, "", ""))

    async def async_messages(
        self,
        *,
        on_connected: Callable[[], None] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield realtime messages from the Gotify MU WebSocket stream."""
        if not self.client_token:
            raise GotifyMUAuthError(
                "A Gotify MU client token is required for inbound messages"
            )

        try:
            async with self.session.ws_connect(
                self._stream_url(),
                headers=self._headers(self.client_token),
                ssl=self.verify_ssl,
                heartbeat=30,
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as websocket:
                if on_connected is not None:
                    on_connected()
                async for msg in websocket:
                    if msg.type == WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                        except (TypeError, json.JSONDecodeError):
                            continue
                        if isinstance(data, dict):
                            yield data
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED):
                        return
                    elif msg.type == WSMsgType.ERROR:
                        error = websocket.exception()
                        raise GotifyMUConnectionError(
                            str(error or "Gotify MU WebSocket error")
                        )
        except GotifyMUError:
            raise
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise GotifyMUAuthError(
                    f"Gotify MU rejected the client token: HTTP {err.status}"
                ) from err
            if err.status == 429:
                raise GotifyMURateLimitError(
                    "Gotify MU rate limited the WebSocket connection"
                ) from err
            raise GotifyMUConnectionError(str(err)) from err
        except (ClientConnectionError, ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err
