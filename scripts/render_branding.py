#!/usr/bin/env python3
"""Render Home Assistant/HACS PNG copies from the user-supplied canonical SVG masters."""
from pathlib import Path
import shutil
import cairosvg
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "branding" / "MonitaHomeAssistant_Full-01.svg"
ICON = ROOT / "branding" / "Monita_HA_Icon-01.svg"

CANON_ICON = ROOT / "custom_components" / "monita" / "brand" / "monita-ha-icon.png"
CANON_LOGO = ROOT / "custom_components" / "monita" / "brand" / "monita-ha-logo.png"

def _remove_connected_canvas_background(path: Path) -> None:
    """Make only a solid edge-connected canvas background transparent.

    If the rendered SVG already has transparent corners, this is a no-op. If all
    four corners are the same opaque color, only pixels connected to those
    corners with that exact color are cleared. Artwork pixels are never
    recolored, resized, blurred, recompressed through JPEG, or otherwise altered.
    """
    with Image.open(path) as source:
        image = source.convert("RGBA")

    corners = [
        image.getpixel((0, 0)),
        image.getpixel((image.width - 1, 0)),
        image.getpixel((0, image.height - 1)),
        image.getpixel((image.width - 1, image.height - 1)),
    ]

    if all(pixel[3] == 0 for pixel in corners):
        return

    if not all(pixel[3] == 255 for pixel in corners):
        raise RuntimeError(f"Icon canvas has mixed corner alpha; refusing to alter artwork: {path}")

    background = corners[0]
    if any(pixel[:3] != background[:3] for pixel in corners[1:]):
        raise RuntimeError(f"Icon canvas corners do not share one background color: {path}")

    transparent = (background[0], background[1], background[2], 0)
    for point in (
        (0, 0),
        (image.width - 1, 0),
        (0, image.height - 1),
        (image.width - 1, image.height - 1),
    ):
        if image.getpixel(point)[:3] == background[:3]:
            ImageDraw.floodfill(image, point, transparent, thresh=0)

    image.save(path, format="PNG")


def render(src: Path, dst: Path, width: int, height: int, *, transparent_canvas: bool = False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        bytestring=src.read_bytes(),
        write_to=str(dst),
        output_width=width,
        output_height=height,
    )
    if transparent_canvas:
        _remove_connected_canvas_background(dst)

render(ICON, CANON_ICON, 512, 512, transparent_canvas=True)
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
