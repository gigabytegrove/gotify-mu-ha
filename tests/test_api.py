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

    def _response(self, method: str, url: str, kwargs: dict[str, Any]):
        self.calls.append((method, url, kwargs))
        payload = self._payloads.popleft()
        if isinstance(payload, _FakeResponse):
            return payload
        return _FakeResponse(url, payload)

    def get(self, url: str, **kwargs):
        return self._response("GET", url, kwargs)

    def post(self, url: str, **kwargs):
        return self._response("POST", url, kwargs)


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


async def test_client_token_send_routes_to_selected_channel():
    """Server-centric sends use the client token and appid Channel routing."""
    session = _FakeSession([{"id": 3}])
    client = GotifyMUClient(
        session,
        SERVER,
        "",
        True,
        "client-secret",
    )

    await client.async_send(
        "Greenhouse alert",
        title="Greenhouse",
        priority=7,
        channel_id=8,
    )

    _, url, kwargs = session.calls[0]
    assert url == f"{SERVER}/message"
    assert kwargs["headers"] == {"X-Gotify-Key": "client-secret"}
    assert kwargs["json"] == {
        "message": "Greenhouse alert",
        "priority": 7,
        "title": "Greenhouse",
        "appid": 8,
    }


def test_channel_post_permissions_follow_monita_roles():
    """Channel metadata distinguishes push-capable and read-only roles."""
    assert GotifyMUClient._parse_channel(
        {"id": 1, "name": "Owner", "role": "owner"}
    ).can_post
    assert GotifyMUClient._parse_channel(
        {"id": 2, "name": "Publisher", "role": "publisher"}
    ).can_post
    assert GotifyMUClient._parse_channel(
        {
            "id": 3,
            "name": "Member",
            "role": "member",
            "allowMemberPost": True,
        }
    ).can_post
    assert not GotifyMUClient._parse_channel(
        {"id": 4, "name": "Read only", "role": "readonly"}
    ).can_post

async def test_capabilities_discovers_chat_images():
    """Server-centric setup discovers first-class Chat image support."""
    session = _FakeSession([{"features": {"chatImages": True}}])
    client = GotifyMUClient(session, SERVER, "", True, "client-secret")

    capabilities = await client.async_capabilities()

    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == f"{SERVER}/api/mu/v1/capabilities"
    assert kwargs["headers"] == {"X-Gotify-Key": "client-secret"}
    assert capabilities["features"]["chatImages"] is True


async def test_chat_image_send_uses_client_token_and_multipart():
    """Chat images use the Channel-scoped multipart endpoint."""
    session = _FakeSession([{"id": 9, "appid": 8, "message": "Person detected"}])
    client = GotifyMUClient(session, SERVER, "", True, "client-secret")

    result = await client.async_send_chat_image(
        "Person detected",
        channel_id=8,
        image=b"\xff\xd8\xff\xe0jpeg",
        filename="front-door.jpg",
        content_type="image/jpeg",
        priority=9,
        extras={"homeassistant::gotify_mu": {"entry_id": "entry-1"}},
    )

    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == f"{SERVER}/application/8/chat-message"
    assert kwargs["headers"] == {"X-Gotify-Key": "client-secret"}
    assert isinstance(kwargs["data"], FormData)
    assert "json" not in kwargs
    assert result["id"] == 9


async def test_capabilities_returns_chat_image_feature():
    """Capability discovery exposes the server's Chat image support."""
    session = _FakeSession(
        [{"product": "gotify-mu", "features": {"chatImages": True}}]
    )
    client = GotifyMUClient(session, SERVER, "", True, "client-secret")

    capabilities = await client.async_capabilities()

    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == f"{SERVER}/api/mu/v1/capabilities"
    assert kwargs["headers"] == {"X-Gotify-Key": "client-secret"}
    assert capabilities["features"]["chatImages"] is True


async def test_send_chat_image_uses_client_token_and_multipart():
    """A Chat image is posted directly to the selected Channel."""
    session = _FakeSession([{"id": 55, "appid": 8}])
    client = GotifyMUClient(session, SERVER, "", True, "client-secret")
    image = b"\xff\xd8\xff\xe0jpeg"

    result = await client.async_send_chat_image(
        "Person detected",
        channel_id=8,
        image=image,
        filename="front-door.jpg",
        content_type="image/jpeg",
        priority=9,
        extras={"homeassistant::gotify_mu": {"source": "monita-ha"}},
    )

    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == f"{SERVER}/application/8/chat-message"
    assert kwargs["headers"] == {"X-Gotify-Key": "client-secret"}
    assert isinstance(kwargs["data"], FormData)
    assert "json" not in kwargs
    assert result == {"id": 55, "appid": 8}
