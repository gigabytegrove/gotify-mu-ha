"""Image acquisition regression tests for Gotify MU."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientError
from homeassistant.exceptions import HomeAssistantError
from yarl import URL

from custom_components.gotify_mu.media import (
    MAX_IMAGE_BYTES,
    async_acquire_entity_image,
    async_acquire_url_image,
)

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-image"
PNG = b"\x89PNG\r\n\x1a\n" + b"png-image"


class _Content:
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def iter_chunked(self, size: int):
        for start in range(0, len(self._body), size):
            yield self._body[start : start + size]


class _Response:
    def __init__(
        self,
        url: str,
        body: bytes,
        *,
        status: int = 200,
        content_type: str | None = "image/jpeg",
        content_length: int | None = None,
    ) -> None:
        self.url = URL(url)
        self.status = status
        self.content = _Content(body)
        self.headers: dict[str, str] = {}
        if content_type is not None:
            self.headers["Content-Type"] = content_type
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Session:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


async def test_camera_entity_captures_current_frame(hass):
    """Camera entities are captured through Home Assistant's camera API."""
    with patch(
        "custom_components.gotify_mu.media._async_get_camera_image",
        new=AsyncMock(
            return_value=SimpleNamespace(content=JPEG, content_type="image/jpeg")
        ),
    ) as get_image:
        result = await async_acquire_entity_image(hass, "camera.front_door")

    get_image.assert_awaited_once_with(hass, "camera.front_door")
    assert result.content == JPEG
    assert result.content_type == "image/jpeg"
    assert result.filename.startswith("front-door-")
    assert result.filename.endswith(".jpg")


async def test_image_entity_uses_supported_image_api(hass):
    """Image entities are retrieved through Home Assistant's image API."""
    with patch(
        "custom_components.gotify_mu.media._async_get_image_entity",
        new=AsyncMock(
            return_value=SimpleNamespace(content=PNG, content_type="image/png")
        ),
    ) as get_image:
        result = await async_acquire_entity_image(hass, "image.latest_snapshot")

    get_image.assert_awaited_once_with(hass, "image.latest_snapshot")
    assert result.content == PNG
    assert result.content_type == "image/png"
    assert result.filename.startswith("latest-snapshot-")
    assert result.filename.endswith(".png")


async def test_http_image_is_downloaded_into_home_assistant(hass):
    """HTTP source bytes are downloaded instead of forwarding the source URL."""
    source = "https://camera.example.test/current.jpg?token=private"
    session = _Session(_Response(source, JPEG))

    with patch(
        "custom_components.gotify_mu.media.async_get_clientsession",
        return_value=session,
    ):
        result = await async_acquire_url_image(hass, source)

    assert result.content == JPEG
    assert result.content_type == "image/jpeg"
    assert result.filename.startswith("remote-image-")
    assert session.calls[0][0] == source
    assert session.calls[0][1]["allow_redirects"] is True


async def test_oversized_http_image_is_rejected_before_upload(hass):
    """An oversized Content-Length fails before image bytes can be staged."""
    source = "https://camera.example.test/huge.jpg"
    session = _Session(
        _Response(
            source,
            b"",
            content_length=MAX_IMAGE_BYTES + 1,
        )
    )

    with (
        patch(
            "custom_components.gotify_mu.media.async_get_clientsession",
            return_value=session,
        ),
        pytest.raises(HomeAssistantError, match="Image exceeded upload limit"),
    ):
        await async_acquire_url_image(hass, source)


async def test_non_image_mime_is_rejected(hass):
    """HTML and other non-image MIME responses are never treated as images."""
    source = "https://camera.example.test/login"
    session = _Session(
        _Response(
            source,
            b"<html>login</html>",
            content_type="text/html",
        )
    )

    with (
        patch(
            "custom_components.gotify_mu.media.async_get_clientsession",
            return_value=session,
        ),
        pytest.raises(HomeAssistantError, match="Unsupported image type"),
    ):
        await async_acquire_url_image(hass, source)


async def test_html_pretending_to_be_jpeg_is_rejected(hass):
    """A forged image Content-Type must also match the actual byte signature."""
    source = "https://camera.example.test/current.jpg"
    session = _Session(
        _Response(
            source,
            b"<html>unauthorized</html>",
            content_type="image/jpeg",
        )
    )

    with (
        patch(
            "custom_components.gotify_mu.media.async_get_clientsession",
            return_value=session,
        ),
        pytest.raises(HomeAssistantError, match="Unsupported image type"),
    ):
        await async_acquire_url_image(hass, source)


async def test_source_url_secrets_are_not_exposed_in_errors_or_logs(hass, caplog):
    """Client failures must not leak a query-string credential."""
    source = "https://camera.example.test/current.jpg?token=super-secret"
    session = _Session(
        error=ClientError(
            "request failed for https://camera.example.test/current.jpg?token=super-secret"
        )
    )

    with (
        patch(
            "custom_components.gotify_mu.media.async_get_clientsession",
            return_value=session,
        ),
        pytest.raises(HomeAssistantError) as error,
    ):
        await async_acquire_url_image(hass, source)

    assert "super-secret" not in str(error.value)
    assert "super-secret" not in caplog.text
