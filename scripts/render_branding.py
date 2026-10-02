#!/usr/bin/env python3
"""Render Home Assistant/HACS PNG copies from the exact supplied SVG masters."""

from pathlib import Path
import shutil
import cairosvg

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "branding" / "MonitaHomeAssistant_Full-01.svg"
ICON = ROOT / "branding" / "Monita_HA_Icon-01.svg"

CANON_ICON = ROOT / "custom_components" / "monita" / "brand" / "monita-ha-icon.png"
CANON_LOGO = ROOT / "custom_components" / "monita" / "brand" / "monita-ha-logo.png"


def render(src: Path, dst: Path, width: int, height: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        bytestring=src.read_bytes(),
        write_to=str(dst),
        output_width=width,
        output_height=height,
    )


render(ICON, CANON_ICON, 512, 512)
render(FULL, CANON_LOGO, 1413, 512)

aliases = {
    CANON_ICON: [
        ROOT / "custom_components" / "monita" / "brand" / "icon.png",
        ROOT / "custom_components" / "gotify_mu" / "brand" / "monita-ha-icon.png",
        ROOT / "custom_components" / "gotify_mu" / "brand" / "icon.png",
        ROOT / "icon.png",
    ],
    CANON_LOGO: [
        ROOT / "custom_components" / "monita" / "brand" / "logo.png",
        ROOT / "custom_components" / "gotify_mu" / "brand" / "monita-ha-logo.png",
        ROOT / "custom_components" / "gotify_mu" / "brand" / "logo.png",
        ROOT / "logo.png",
    ],
}

for source, destinations in aliases.items():
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
