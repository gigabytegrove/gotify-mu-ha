# Gotify-MU for Home Assistant branding

These are the canonical Gotify-MU for Home Assistant branding assets supplied for this project.

## Canonical assets

- `gotify-mu-ha-banner.png` — 1600×500 horizontal banner
- `gotify-mu-ha-logo.png` — 1024×1024 project logo
- `gotify-mu-ha-icon.png` — 1024×1024 integration icon
- `gotify-mu-ha-banner-q.png` — supplied alternate/optimized banner
- `gotify-mu-ha-logo-q.png` — supplied alternate/optimized logo
- `gotify-mu-ha-icon-q.png` — supplied alternate/optimized icon

## Compatibility aliases

Home Assistant and repository documentation may use:

- `banner.png` → exact canonical `gotify-mu-ha-banner.png`
- `logo.png` → exact canonical `gotify-mu-ha-logo.png`
- `icon.png` → exact canonical `gotify-mu-ha-icon.png`

## Preservation rule

Do not regenerate, redraw, recolor, crop differently, optimize in place, or silently replace these assets during ordinary application, documentation, CI, packaging, or release work.

A branding change must be an intentional branding-specific change using explicitly supplied replacement assets.


## CI enforcement

The exact approved branding is locked in `.github/branding-lock.json`.
`scripts/check_branding.py` verifies all six canonical PNG files by Git blob
hash and dimensions, and verifies that `banner.png`, `logo.png`, and
`icon.png` remain byte-for-byte aliases of the canonical non-`-q` files.

Normal feature, bug-fix, documentation, packaging, and release work must not
change the branding lock. Updating it is reserved for an explicitly approved
branding change.
