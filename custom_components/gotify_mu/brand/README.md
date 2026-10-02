# Monita for Home Assistant branding

The supplied SVG files are the authoritative visual source for Monita for Home Assistant.

## Canonical masters

- `branding/MonitaHomeAssistant_Full-01.svg` — full Monita for Home Assistant logo
- `branding/Monita_HA_Icon-01.svg` — Monita for Home Assistant icon

The artwork is used exactly as supplied. It must not be redrawn, recolored, cropped, have its canvas background removed, have its proportions changed, be traced, simplified, or otherwise reinterpreted.

## Home Assistant / HACS raster copies

Home Assistant and HACS surfaces require PNG assets. `scripts/render_branding.py` renders those PNGs directly from the supplied SVG masters at the required pixel dimensions.

- `monita-ha-icon.png` / `icon.png` — direct render of the supplied HA icon
- `monita-ha-logo.png` / `logo.png` — direct render of the supplied full HA logo

The historical `gotify_mu` component keeps byte-identical branding aliases only for existing-install compatibility. It does not use separate artwork.
