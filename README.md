# Gotify MU for Home Assistant

A Home Assistant custom integration for [Gotify MU](https://github.com/gigabytegrove/gotify-mu).

## Features

- UI-based setup through **Settings → Devices & services**
- Standard Home Assistant `notify` entity for automations and scripts
- Native `gotify_mu.send` action with priority and Markdown support
- Multiple Gotify MU channels by adding multiple integration entries
- Uses the existing Gotify-compatible `POST /message` API
- Application-token authentication via `X-Gotify-Key`
- Configurable TLS certificate verification
- No YAML configuration required
- HACS-compatible repository layout

## Install manually

Copy:

```text
custom_components/gotify_mu
```

to:

```text
/config/custom_components/gotify_mu
```

Restart Home Assistant.

Then open:

**Settings → Devices & services → Add integration → Gotify MU**

Enter:

- Server URL, such as `https://gotify.example.com`
- Gotify MU application token for the Channel
- Channel name
- TLS verification preference
- Default priority

## HACS

Add this repository to HACS as a **Custom repository** with category **Integration**, then install **Gotify MU** and restart Home Assistant.

## Using the notify entity

After setup, Home Assistant creates a `notify` entity for the configured Gotify MU Channel.

Example:

```yaml
action:
  - action: notify.send_message
    target:
      entity_id: notify.gotify_mu
    data:
      title: "Gigabyte Grove"
      message: "Home Assistant is online."
```

The final entity ID is assigned by Home Assistant and may include the configured Channel name.

## Native Gotify MU action

The integration also exposes:

```text
gotify_mu.send
```

Example:

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Greenhouse Alert"
      message: "**Temperature is above 100°F.**"
      priority: 8
      markdown: true
```

If multiple Gotify MU config entries exist, `entry_id` can be supplied to select a specific one. If omitted, the first configured entry is used.

## Compatibility

Gotify MU intentionally preserves Gotify's application-token message API. This integration sends JSON to:

```text
POST /message
X-Gotify-Key: <application-token>
```

so the integration remains compatible with Gotify MU while using the same stable publishing interface as standard Gotify.

## Security

Application tokens are stored in Home Assistant's config-entry storage. They are not written to `configuration.yaml`.

Use HTTPS for remote Gotify MU servers. Disable TLS verification only for trusted private-network deployments where certificate verification is intentionally unavailable.

## License

MIT
