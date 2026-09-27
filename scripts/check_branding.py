#!/usr/bin/env python3
"""Verify the immutable Gotify-MU for Home Assistant branding baseline."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = ROOT / ".github" / "branding-lock.json"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def git_blob_sha(data: bytes) -> str:
    """Return the Git blob SHA-1 for raw file bytes."""
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def png_size(data: bytes) -> tuple[int, int]:
    """Read PNG dimensions directly from the IHDR chunk."""
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise ValueError("not a valid PNG with an IHDR header")
    return struct.unpack(">II", data[16:24])


def main() -> None:
    """Validate canonical assets and compatibility aliases."""
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    failures: list[str] = []

    for relative, expected in lock["assets"].items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"missing canonical asset: {relative}")
            continue

        data = path.read_bytes()
        actual_sha = git_blob_sha(data)
        if actual_sha != expected["sha"]:
            failures.append(
                f"{relative}: blob SHA changed "
                f"(expected {expected['sha']}, got {actual_sha})"
            )

        try:
            width, height = png_size(data)
        except ValueError as err:
            failures.append(f"{relative}: {err}")
            continue

        expected_size = (expected["width"], expected["height"])
        if (width, height) != expected_size:
            failures.append(
                f"{relative}: dimensions changed "
                f"(expected {expected_size[0]}x{expected_size[1]}, "
                f"got {width}x{height})"
            )

    for alias, canonical in lock["aliases"].items():
        alias_path = ROOT / alias
        canonical_path = ROOT / canonical
        if not alias_path.is_file():
            failures.append(f"missing compatibility alias: {alias}")
            continue
        if not canonical_path.is_file():
            failures.append(f"missing alias source: {canonical}")
            continue
        if alias_path.read_bytes() != canonical_path.read_bytes():
            failures.append(f"{alias}: no longer byte-identical to {canonical}")

    if failures:
        raise SystemExit(
            "Branding integrity check failed:\n- " + "\n- ".join(failures)
        )

    print(
        "Branding integrity OK: "
        f"{len(lock['assets'])} canonical assets and "
        f"{len(lock['aliases'])} compatibility aliases verified."
    )


if __name__ == "__main__":
    main()
