# Monita for Home Assistant branding

**Monita for Home Assistant** is the active identity for the integration formerly known as **Gotify-MU for Home Assistant**.

The supplied Monita artwork and palette are the authoritative visual baseline.

## Brand palette

- Primary — `#2563EB`
- Blue — `#3B82F6`
- Cyan — `#06B6D4`
- Slate — `#0F172A`
- Gray — `#9CA3B8`

## Active assets

- `monita-ha-icon.png` — canonical Monita for Home Assistant integration icon
- `monita-ha-logo.png` — canonical active logo asset
- `icon.png` — Home Assistant/HACS compatibility alias
- `logo.png` — Home Assistant/HACS compatibility alias

The compatibility aliases are byte-identical to their Monita canonical counterparts.

Legacy Gotify-MU artwork has been removed from the active tree. Git history preserves it for provenance.

## Compatibility rule

The visual/product identity is Monita. The Home Assistant technical domain remains `gotify_mu` in this release only to preserve existing config entries, service calls, entities, automations, and HACS upgrades.

## Preservation rule

Do not regenerate, redraw, recolor, reinterpret, or silently replace approved Monita artwork during ordinary feature, bug-fix, documentation, CI, packaging, or release work.

Any future branding change must be explicit and must update `.github/branding-lock.json`.

## CI enforcement

`scripts/check_branding.py` verifies the approved asset hashes, dimensions, and compatibility aliases.
