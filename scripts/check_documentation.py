"""Verify that user-facing Gotify MU features remain documented."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
GUIDE = ROOT / "docs" / "FEATURES.md"
SERVICES = ROOT / "custom_components" / "gotify_mu" / "services.yaml"
TRANSLATIONS = ROOT / "custom_components" / "gotify_mu" / "translations" / "en.json"

REQUIRED_GUIDE_MARKERS = (
    "Application token validation",
    "Client token validation",
    "Multiple Channels",
    "Standard Home Assistant notify entity",
    "`gotify_mu.send` action",
    "Image notifications",
    "Realtime inbound Channel messages",
    "Messages event entity",
    "Inbound connection sensor",
    "Native Home Assistant pairing",
    "Native bridge health sensor",
    "Repairing native pairing",
    "Removing native pairing",
    "Reauthentication",
    "Reconfiguration",
    "Integration options",
    "TLS verification",
    "Diagnostics",
    "Security model",
    "Compatibility",
    "Common workflows",
)


def _service_fields(text: str) -> set[str]:
    """Return top-level fields exposed by gotify_mu.send in services.yaml."""
    fields: set[str] = set()
    in_fields = False
    for line in text.splitlines():
        if line == "  fields:":
            in_fields = True
            continue
        if in_fields and line and not line.startswith("    "):
            break
        if in_fields:
            match = re.fullmatch(r"    ([a-zA-Z0-9_]+):", line)
            if match:
                fields.add(match.group(1))
    return fields


def _entity_names(translations: dict) -> set[str]:
    """Return translated names for entities exposed by the integration."""
    names: set[str] = set()
    for platform in translations.get("entity", {}).values():
        for entity in platform.values():
            name = entity.get("name")
            if isinstance(name, str) and name:
                names.add(name)
    return names


def main() -> None:
    """Validate feature documentation coverage."""
    readme = README.read_text(encoding="utf-8")
    guide = GUIDE.read_text(encoding="utf-8")
    services = SERVICES.read_text(encoding="utf-8")
    translations = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))

    errors: list[str] = []

    if "docs/FEATURES.md" not in readme:
        errors.append("README.md does not link to docs/FEATURES.md")

    for marker in REQUIRED_GUIDE_MARKERS:
        if marker not in guide:
            errors.append(f"Feature guide is missing required topic: {marker}")

    for field in sorted(_service_fields(services)):
        if f"`{field}`" not in guide:
            errors.append(
                f"Feature guide does not document gotify_mu.send field: {field}"
            )

    guide_lower = guide.lower()
    for name in sorted(_entity_names(translations)):
        if name.lower() not in guide_lower:
            errors.append(f"Feature guide does not document entity: {name}")

    if errors:
        raise SystemExit("\\n".join(f"ERROR: {error}" for error in errors))

    print(
        "Feature documentation OK: README linkage, required topics, "
        f"{len(_service_fields(services))} service fields, and "
        f"{len(_entity_names(translations))} entity names verified."
    )


if __name__ == "__main__":
    main()
