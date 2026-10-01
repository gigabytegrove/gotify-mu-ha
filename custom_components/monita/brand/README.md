# Monita for Home Assistant branding

The artwork in this directory is the approved **Monita for Home Assistant** identity supplied on **2026-10-01**.

## Canonical source files

- `MonitaHomeAssistant_Full-01.svg` — supplied full Monita for Home Assistant logo
- `Monita_HA_Icon-01.svg` — supplied Monita for Home Assistant icon

These SVGs are authoritative. Do not redraw, simplify, recolor, crop, stretch, remove backgrounds from, reinterpret, or recreate them.

## Active platform assets

- `monita-ha-logo.png` and `logo.png` — faithful raster renders of the supplied full logo
- `monita-ha-icon.png` and `icon.png` — faithful raster renders of the supplied icon

Home Assistant and HACS still require PNGs on some surfaces. `scripts/render_branding.py` creates those raster files directly from the source SVGs at the source artwork's native dimensions.

## Compatibility

The canonical Home Assistant domain is `monita`. The separate `gotify_mu` component remains only so existing installations created under the historical technical domain continue to load without losing config entries, entities, actions, credentials, or automations.

## Preservation rule

Any future branding change must start with newly supplied canonical artwork and update the branding lock. Ordinary feature, bug-fix, CI, packaging, or documentation work must not regenerate the visual design from colors or shapes.
