"""Shared helpers for Monita."""

from __future__ import annotations

from hashlib import sha256
from urllib.parse import urlsplit


def normalize_server_url(value: str) -> str:
    """Normalize and validate a Monita base URL."""
    url = value.strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Server URL must start with http:// or https://")
    if parsed.username or parsed.password:
        raise ValueError("Credentials must not be embedded in the server URL")
    if parsed.query or parsed.fragment:
        raise ValueError("Server URL must not contain a query string or fragment")
    return url


def fallback_unique_id(server_url: str, app_token: str) -> str:
    """Build a non-secret fallback ID when the server lacks app identity API."""
    fingerprint = sha256(app_token.encode("utf-8")).hexdigest()[:32]
    return f"{server_url}|application:{fingerprint}"


def channel_unique_id(server_url: str, channel_id: int) -> str:
    """Build a stable ID from the Monita channel ID when available."""
    return f"{server_url}|channel:{channel_id}"


def server_unique_id(server_url: str) -> str:
    """Build a stable ID for one Monita server connection."""
    return f"{server_url}|server"
