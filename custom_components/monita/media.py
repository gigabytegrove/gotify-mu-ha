"""Image acquisition helpers for Monita notifications."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from aiohttp import ClientConnectionError, ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 20
_READ_CHUNK_BYTES = 64 * 1024

_SUPPORTED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


@dataclass(frozen=True, slots=True)
class MonitaImage:
    """Validated image ready to be staged on Monita."""

    content: bytes
    filename: str
    content_type: str


def _normalize_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized == "image/jpg":
        return "image/jpeg"
    return normalized or None


def _detect_content_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _validate_image(content: bytes, content_type: str | None) -> tuple[bytes, str]:
    if not content:
        raise HomeAssistantError("Image source returned no image data")
    if len(content) > MAX_IMAGE_BYTES:
        raise HomeAssistantError("Image exceeded upload limit")

    detected = _detect_content_type(content)
    declared = _normalize_content_type(content_type)

    if declared is not None and declared not in _SUPPORTED_CONTENT_TYPES:
        raise HomeAssistantError("Unsupported image type")
    if detected is None:
        raise HomeAssistantError("Unsupported image type")
    if declared is not None and declared != detected:
        raise HomeAssistantError("Image content did not match its declared image type")

    return content, declared or detected


def _filename(name: str, content_type: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9.-]+", "-", name.replace("_", "-")).strip("-.")
    if not safe_name:
        safe_name = "image"
    timestamp = dt_util.now().strftime("%Y%m%d-%H%M%S")
    return f"{safe_name}-{timestamp}{_SUPPORTED_CONTENT_TYPES[content_type]}"


async def _async_get_camera_image(hass: HomeAssistant, entity_id: str):
    """Retrieve a camera frame through Home Assistant without eager camera imports."""
    from homeassistant.components.camera import async_get_image

    return await async_get_image(hass, entity_id)


async def _async_get_image_entity(hass: HomeAssistant, entity_id: str):
    """Retrieve an image entity through Home Assistant without eager image imports."""
    from homeassistant.components.image import async_get_image

    return await async_get_image(hass, entity_id)


async def async_acquire_entity_image(
    hass: HomeAssistant,
    entity_id: str,
) -> MonitaImage:
    """Capture a current image from a camera or image entity."""
    domain, separator, object_id = entity_id.partition(".")
    if not separator or not object_id:
        raise HomeAssistantError("Invalid image entity")

    try:
        if domain == "camera":
            result = await _async_get_camera_image(hass, entity_id)
        elif domain == "image":
            result = await _async_get_image_entity(hass, entity_id)
        else:
            raise HomeAssistantError("Image entity must be a camera or image entity")
    except HomeAssistantError as err:
        if domain == "camera":
            raise HomeAssistantError("Could not capture camera image") from err
        if domain == "image":
            raise HomeAssistantError("Could not retrieve image entity image") from err
        raise
    except (KeyError, ValueError) as err:
        if domain == "camera":
            raise HomeAssistantError("Could not capture camera image") from err
        raise HomeAssistantError("Could not retrieve image entity image") from err

    content, content_type = _validate_image(result.content, result.content_type)
    return MonitaImage(
        content=content,
        filename=_filename(object_id, content_type),
        content_type=content_type,
    )


async def async_acquire_url_image(
    hass: HomeAssistant,
    url: str,
    *,
    verify_ssl: bool = True,
) -> MonitaImage:
    """Download and validate an HTTP(S) image without exposing its source URL."""
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise HomeAssistantError("Image URL must use HTTP or HTTPS")

    session = async_get_clientsession(hass)
    timeout = ClientTimeout(total=IMAGE_DOWNLOAD_TIMEOUT_SECONDS)

    try:
        async with session.get(
            url,
            allow_redirects=True,
            ssl=verify_ssl,
            timeout=timeout,
        ) as response:
            if response.status < 200 or response.status >= 300:
                raise HomeAssistantError(
                    f"Could not download image: HTTP {response.status}"
                )

            final_scheme = response.url.scheme.lower()
            if final_scheme not in {"http", "https"}:
                raise HomeAssistantError("Image URL redirected to an unsupported scheme")

            header_type = _normalize_content_type(response.headers.get("Content-Type"))
            if header_type is not None and header_type not in _SUPPORTED_CONTENT_TYPES:
                raise HomeAssistantError("Unsupported image type")

            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > MAX_IMAGE_BYTES:
                        raise HomeAssistantError("Image exceeded upload limit")
                except ValueError:
                    pass

            body = bytearray()
            async for chunk in response.content.iter_chunked(_READ_CHUNK_BYTES):
                body.extend(chunk)
                if len(body) > MAX_IMAGE_BYTES:
                    raise HomeAssistantError("Image exceeded upload limit")
    except HomeAssistantError:
        raise
    except (ClientConnectionError, ClientError, TimeoutError):
        raise HomeAssistantError("Could not download image from URL") from None

    content, content_type = _validate_image(bytes(body), header_type)
    return MonitaImage(
        content=content,
        filename=_filename("remote-image", content_type),
        content_type=content_type,
    )
