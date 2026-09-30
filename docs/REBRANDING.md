# Monita for Home Assistant rebrand

**Monita for Home Assistant** is the new product name for **Gotify-MU for Home Assistant**.

This rebrand is designed as an in-place upgrade, not a replacement integration.

## What users will see change

- Home Assistant integration name: **Monita for Home Assistant**
- HACS display name: **Monita for Home Assistant**
- setup, options, Repairs, diagnostics, and action-editor wording: **Monita**
- device manufacturer: **Monita**
- GitHub release titles: **Monita for Home Assistant**
- documentation and examples: **Monita**
- approved visual identity: the supplied Monita for Home Assistant branding

During the transition, documentation may include **formerly Gotify-MU for Home Assistant** to make the rename clear to existing users.

## What intentionally does not change in 1.3.0

The following technical identifiers are compatibility contracts and remain unchanged:

| Existing identifier | 1.3.0 behavior | Why |
| --- | --- | --- |
| `gotify_mu` | Retained | Home Assistant integration domain and stored config-entry compatibility |
| `custom_components/gotify_mu` | Retained | Prevents HACS/manual upgrades from becoming a second integration |
| `monita.send` | Retained | Existing automations and scripts continue to run |
| `homeassistant::gotify_mu` | Retained | Existing message-origin/loop-prevention contract |
| Stored config entries | Retained | No delete/re-add process |
| Entity unique IDs | Retained | Dashboards and automations keep their entity registry relationships |
| Application/client tokens | Retained | No credential reset solely because of the rename |
| Native pairing credentials | Retained | Existing paired bridges do not need to be rebuilt |

A future technical namespace migration, if ever introduced, must include an explicit migration layer and compatibility period. A brand rename alone is not sufficient reason to break existing Home Assistant YAML.

## Existing automations

This remains valid after the rebrand:

```yaml
action:
  - action: monita.send
    data:
      title: "Front Door"
      message: "Person detected."
      priority: 9
      image_entity: camera.front_door
```

The Home Assistant action editor displays Monita branding even though the compatibility-safe action ID remains `monita.send`.

## Server/API terminology

Monita continues to use the established compatible HTTP/WebSocket contracts used by this integration.

Documentation retains the word **Gotify** only when it is technically necessary to describe:

- upstream/legacy Gotify API compatibility
- an established API header or wire-format convention
- legacy product/version history in the changelog
- compatibility identifiers that cannot be renamed without breaking upgrades

Those references do not represent the active product name.

## Visual identity

Approved palette:

- Primary: `#2563EB`
- Blue: `#3B82F6`
- Cyan: `#06B6D4`
- Slate: `#0F172A`
- Gray: `#9CA3B8`

The supplied Monita for Home Assistant brand sheet is the design authority. The artwork must not be redesigned, recolored, or regenerated as part of ordinary software work.

The active binary icon/logo/banner replacement and branding-lock update should use assets derived directly from the approved supplied artwork, not a newly interpreted design.
