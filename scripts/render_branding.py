#!/usr/bin/env python3
"""Render Home Assistant/HACS PNGs from the supplied canonical SVG artwork.

The SVG files are the source of truth. Raster outputs are produced at their
native viewBox sizes only; this script does not crop, recolor, reshape, or redraw.
"""

from pathlib import Path
import cairosvg

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "custom_components/monita/brand/MonitaHomeAssistant_Full-01.svg"
ICON = ROOT / "custom_components/monita/brand/Monita_HA_Icon-01.svg"

def render(source: Path, destination: Path, width: int, height: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        url=str(source),
        write_to=str(destination),
        output_width=width,
        output_height=height,
    )

# HACS repository cards expect a square root logo.
for target in (ROOT / "logo.png", ROOT / "icon.png"):
    render(ICON, target, 512, 512)

for domain in ("monita", "gotify_mu"):
    brand = ROOT / "custom_components" / domain / "brand"
    for target in (brand / "monita-ha-icon.png", brand / "icon.png"):
        render(ICON, target, 512, 512)
    for target in (brand / "monita-ha-logo.png", brand / "logo.png"):
        render(FULL, target, 1413, 512)
