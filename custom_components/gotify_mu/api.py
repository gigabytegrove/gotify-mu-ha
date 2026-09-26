"""Small async API client for Gotify MU."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession


class GotifyMUError(Exception):
    """Base Gotify MU API error."""


class GotifyMUAuthError(GotifyMUError):
    """Authentication failed."""


class GotifyMUConnectionError(GotifyMUError):
    """Connection failed."""


@dataclass(slots=True)
class GotifyMUClient:
    """Async Gotify MU API client."""

    session: ClientSession
    server_url: str
    app_token: str
    verify_ssl: bool = True

    def __post_init__(self) -> None:
        self.server_url = self.server_url.rstrip("/")

    async def health(self) -> bool:
        """Return True when the Gotify MU health endpoint is reachable."""
        try:
            async with self.session.get(
                f"{self.server_url}/health",
                ssl=self.verify_ssl,
            ) as response:
                response.raise_for_status()
                return True
        except (ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err

    async def send(
        self,
        message: str,
        *,
        title: str | None = None,
        priority: int = 5,
        markdown: bool = False,
        extras: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a notification through the Gotify-compatible message API."""
        payload: dict[str, Any] = {
            "message": message,
            "priority": priority,
        }
        if title:
            payload["title"] = title

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
                headers={"X-Gotify-Key": self.app_token},
                json=payload,
                ssl=self.verify_ssl,
            ) as response:
                if response.status in (401, 403):
                    raise GotifyMUAuthError(
                        f"Gotify MU rejected the application token ({response.status})"
                    )
                response.raise_for_status()
                data = await response.json(content_type=None)
                return data if isinstance(data, dict) else {}
        except GotifyMUAuthError:
            raise
        except ClientResponseError as err:
            raise GotifyMUError(
                f"Gotify MU returned HTTP {err.status}: {err.message}"
            ) from err
        except (ClientError, TimeoutError) as err:
            raise GotifyMUConnectionError(str(err)) from err
