"""API regression tests for Gotify MU attachment publishing."""

from __future__ import annotations

from collections import deque
from typing import Any

from aiohttp import FormData
from yarl import URL

from custom_components.gotify_mu.api import GotifyMUClient

SERVER = "https://push.example.test"
APP_TOKEN = "app-secret"


class _FakeResponse:
    def __init__(self, url: str, payload: Any, status: int = 200) -> None:
        self.url = URL(url)
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return ""

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise AssertionError(f"Unexpected HTTP {self.status} in fake response")


class _FakeSession:
    def __init__(self, payloads: list[Any]) -> None:
        self._payloads = deque(payloads)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs):
        self.calls.append(("POST", url, kwargs))
        payload = self._payloads.popleft()
        if isinstance(payload, _FakeResponse):
            return payload
        return _FakeResponse(url, payload)


async def test_text_only_send_payload_is_unchanged():
    """Text-only sends do not gain attachment fields."""
    session = _FakeSession([{"id": 1}])
    client = GotifyMUClient(session, SERVER, APP_TOKEN)

    await client.async_send(
        "Door opened",
        title="Home",
        priority=8,
        extras={"custom": {"value": True}},
    )

    _, url, kwargs = session.calls[0]
    assert url == f"{SERVER}/message"
    assert kwargs["headers"] == {"X-Gotify-Key": APP_TOKEN}
    assert kwargs["json"] == {
        "message": "Door opened",
        "priority": 8,
        "title": "Home",
        "extras": {"custom": {"value": True}},
    }
    assert "attachmentIds" not in kwargs["json"]


async def test_upload_image_uses_application_token_and_multipart_form():
    """Images are staged with the app token as multipart data."""
    session = _FakeSession(
        [{"id": 123, "filename": "front-door.jpg", "contentType": "image/jpeg"}]
    )
    client = GotifyMUClient(session, SERVER, APP_TOKEN)
    image = b"\xff\xd8\xff\xe0jpeg"

    attachment = await client.async_upload_image(
        image,
        filename="front-door.jpg",
        content_type="image/jpeg",
    )

    _, url, kwargs = session.calls[0]
    assert url == f"{SERVER}/application/current/attachment"
    assert kwargs["headers"] == {"X-Gotify-Key": APP_TOKEN}
    assert isinstance(kwargs["data"], FormData)
    assert "json" not in kwargs
    assert attachment.id == 123
    assert attachment.filename == "front-door.jpg"
    assert attachment.content_type == "image/jpeg"
    assert attachment.size == len(image)


async def test_send_includes_attachment_ids_and_preserves_markdown_extras():
    """Staged IDs are additive to priority, Markdown, and caller extras."""
    session = _FakeSession([{"id": 2}])
    client = GotifyMUClient(session, SERVER, APP_TOKEN)

    await client.async_send(
        "**Person detected**",
        title="Front Door",
        priority=9,
        markdown=True,
        extras={"custom::extra": {"enabled": True}},
        attachment_ids=[123, 456],
    )

    payload = session.calls[0][2]["json"]
    assert payload == {
        "message": "**Person detected**",
        "priority": 9,
        "title": "Front Door",
        "attachmentIds": [123, 456],
        "extras": {
            "custom::extra": {"enabled": True},
            "client::display": {"contentType": "text/markdown"},
        },
    }
