# Monita for Home Assistant branding

Monita for Home Assistant is the successor brand to **Gotify-MU for Home Assistant**.

The artwork supplied for the Monita rebrand is the authoritative visual identity for this integration. During the transition, the Home Assistant integration domain remains `gotify_mu` so existing installations, entities, services, config entries, and automations continue to work.

## Brand palette

- Primary — `#2563EB`
- Blue — `#3B82F6`
- Cyan — `#06B6D4`
- Slate — `#0F172A`
- Gray — `#9CA3B8`

## Canonical Monita assets

The rebrand uses:

- `monita-ha-banner.png` — horizontal Monita for Home Assistant banner
- `monita-ha-logo.png` — full Monita for Home Assistant logo
- `monita-ha-icon.png` — square Monita for Home Assistant app/integration icon

Home Assistant/repository compatibility aliases remain:

- `banner.png`
- `logo.png`
- `icon.png`

The aliases must be byte-identical to their Monita canonical counterparts.

## Legacy artwork

Files named `gotify-mu-ha-*.png` are historical pre-Monita assets. They may remain in Git history for provenance, but they are no longer the active product identity once the Monita assets are committed.

## Preservation rule

Do not regenerate, redraw, recolor, reinterpret, or silently replace the approved Monita artwork during normal feature, bug-fix, documentation, CI, packaging, or release work.

A branding change must be an intentional branding-specific change using artwork explicitly approved for Monita.

## CI enforcement

The exact approved active branding is locked in `.github/branding-lock.json`.
`scripts/check_branding.py` verifies canonical asset hashes and dimensions and verifies that the Home Assistant compatibility aliases remain byte-for-byte identical.
