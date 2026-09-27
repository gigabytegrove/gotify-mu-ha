"""Unit tests for non-network helpers."""

import pytest

from custom_components.gotify_mu.helpers import (
    channel_unique_id,
    fallback_unique_id,
    normalize_server_url,
    server_unique_id,
)


def test_normalize_server_url() -> None:
    """Normalize a valid URL."""
    assert normalize_server_url("https://push.example.com/") == "https://push.example.com"


@pytest.mark.parametrize(
    "url",
    [
        "push.example.com",
        "ftp://push.example.com",
        "https://user:pass@push.example.com",
        "https://push.example.com/?token=secret",
        "https://push.example.com/#fragment",
    ],
)
def test_reject_invalid_server_url(url: str) -> None:
    """Reject unsupported or unsafe server URLs."""
    with pytest.raises(ValueError):
        normalize_server_url(url)


def test_token_fingerprint_unique_id_does_not_expose_token() -> None:
    """Never place the application token itself in a config-entry unique ID."""
    token = "super-secret-application-token"
    unique_id = fallback_unique_id("https://push.example.com", token)
    assert token not in unique_id
    assert unique_id.startswith("https://push.example.com|application:")


def test_channel_unique_id() -> None:
    """Build stable channel IDs when Gotify MU exposes application identity."""
    assert (
        channel_unique_id("https://push.example.com", 42)
        == "https://push.example.com|channel:42"
    )


def test_server_unique_id() -> None:
    """Build one stable config-entry identity per Monita server."""
    assert (
        server_unique_id("https://push.example.com")
        == "https://push.example.com|server"
    )
