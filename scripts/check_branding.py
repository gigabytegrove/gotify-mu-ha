#!/usr/bin/env python3
"""Verify Monita for Home Assistant branding against the supplied canonical SVG masters."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = ROOT / ".github" / "branding-lock.json"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise ValueError("not a valid PNG with an IHDR header")
    return struct.unpack(">II", data[16:24])


def main() -> None:
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    failures: list[str] = []

    for relative, expected in lock["sources"].items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"missing canonical source: {relative}")
            continue
        actual_sha = git_blob_sha(path.read_bytes())
        if actual_sha != expected["sha"]:
            failures.append(
                f"{relative}: canonical SVG changed "
                f"(expected {expected['sha']}, got {actual_sha})"
            )

    for relative, expected in lock["rasters"].items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"missing rendered branding asset: {relative}")
            continue
        try:
            size = png_size(path.read_bytes())
        except ValueError as err:
            failures.append(f"{relative}: {err}")
            continue
        expected_size = (expected["width"], expected["height"])
        if size != expected_size:
            failures.append(
                f"{relative}: dimensions changed "
                f"(expected {expected_size[0]}x{expected_size[1]}, got {size[0]}x{size[1]})"
            )

    for alias, canonical in lock["aliases"].items():
        alias_path = ROOT / alias
        canonical_path = ROOT / canonical
        if not alias_path.is_file():
            failures.append(f"missing branding alias: {alias}")
            continue
        if not canonical_path.is_file():
            failures.append(f"missing alias source: {canonical}")
            continue
        if alias_path.read_bytes() != canonical_path.read_bytes():
            failures.append(f"{alias}: no longer byte-identical to {canonical}")

    if failures:
        raise SystemExit("Branding integrity check failed:\n- " + "\n- ".join(failures))

    print(
        "Branding integrity OK: "
        f"{len(lock['sources'])} canonical SVG masters, "
        f"{len(lock['rasters'])} rendered canonical PNGs, and "
        f"{len(lock['aliases'])} byte-identical aliases verified."
    )


if __name__ == "__main__":
    main()
