# Gotify MU for Home Assistant

<p align="center">
  <img src="https://raw.githubusercontent.com/gigabytegrove/gotify-mu-ha/main/custom_components/gotify_mu/brand/gotify-mu-ha-banner.png" alt="Gotify MU for Home Assistant" width="900">
</p>


A Home Assistant custom integration for [Gotify MU](https://github.com/gigabytegrove/gotify-mu).

It provides native Home Assistant notification entities for Gotify MU Channels and optional realtime inbound Channel messages for two-way automations.

## Features

- UI setup through **Settings → Devices & services**
- No `configuration.yaml` changes required
- Standard Home Assistant `notify` entity
- Native `gotify_mu.send` action with priority and Markdown support
- Exact application-token validation without creating a test notification
- Stable Channel identity on current Gotify MU servers
- Optional client token for realtime inbound messages
- Home Assistant `event` entity containing inbound Channel messages
- Connection-status binary sensor for the inbound WebSocket
- Automatic reconnect with bounded backoff
- Reauthentication and reconfiguration flows
- Optional native Home Assistant pairing with Gotify MU, with no Home Assistant Long-Lived Access Token required
- Authenticated Gotify MU → Home Assistant webhook events and Home Assistant → Gotify MU event forwarding
- Native pairing can be repaired or removed without deleting the normal Gotify MU integration
- Native bridge health sensor with Paired / Connected / Degraded / Repair required visibility
- Bounded retry/backoff for transient Home Assistant → Gotify MU event-delivery failures
- Authenticated remote revoke when native pairing is removed
- Multiple Gotify MU Channels by adding multiple integration entries
- Config-entry diagnostics with credentials redacted
- TLS verification control for private/self-signed deployments
- HACS-compatible repository layout
- Legacy fallback for Gotify-compatible servers without the MU identity endpoint

## Requirements

Outbound notifications require:

- a Gotify MU server URL
- an application token for the Channel

Realtime inbound messages additionally require a Gotify MU **client token** belonging to a user who can access the Channel.

Current Gotify MU builds expose `GET /application/current`, allowing this integration to identify the application token's exact Channel automatically. Older Gotify-compatible servers still work for outbound notifications using a safe validation fallback.

## Installation

### HACS

Add this repository to HACS as a **Custom repository** with category **Integration**:

```text
https://github.com/gigabytegrove/gotify-mu-ha
```

Install **Gotify MU**, then restart Home Assistant.

### Manual

Copy:

```text
custom_components/gotify_mu
```

to:

```text
/config/custom_components/gotify_mu
```

Restart Home Assistant.

## Setup

Open:

**Settings → Devices & services → Add integration → Gotify MU**

Enter:

- **Server URL** — for example `https://push.example.com`
- **Application token** — the application token for the Gotify MU Channel
- **Client token** — optional; required only for inbound/two-way messages
- **Verify TLS certificate** — keep enabled unless you deliberately use a trusted private certificate that Home Assistant cannot validate

On current Gotify MU builds, the Channel is detected automatically from the application token. On older servers, the integration asks you to choose or name the Channel after credential validation.

### Native Gotify MU pairing

Native pairing is optional and additive. The application token remains the credential used by the notify entity and `gotify_mu.send`, while native pairing adds an authenticated event bridge between Gotify MU and Home Assistant.

In Gotify MU, create or open a Home Assistant connection using **Native gotify-mu-ha integration** and generate its one-time pairing code. The code has the form:

```text
12.<random-secret>
```

Then in Home Assistant open the configured **Gotify MU** integration, choose **Configure → Native Home Assistant pairing → Pair with Gotify MU server**, and enter the pairing code.

Home Assistant generates a random private webhook ID automatically. It shows the callback URL it detected and always allows an optional base-URL override, which is useful when Home Assistant chooses an internal address that the Gotify MU server cannot actually reach. If no usable URL can be determined automatically, the override becomes required.

A successful pairing stores only the native integration ID, shared secret, event path, and webhook details in Home Assistant config-entry storage. The one-time pairing code is never stored.

The native bridge supports both directions:

- **Gotify MU → Home Assistant:** Gotify MU posts authenticated payloads to the private HA webhook. The integration validates the Bearer secret and fires the supplied `eventType` on the Home Assistant event bus with the supplied `data`.
- **Home Assistant → Gotify MU:** Home Assistant events are posted to the paired Gotify MU event endpoint using the shared Bearer secret. Gotify MU applies its configured event type, entity ID, field, and value filters before routing matching events into the selected Channel.

Inbound native bridge payloads are events only. They are never converted into arbitrary Home Assistant service calls.

## Sending notifications

Home Assistant creates a notification entity for each configured Gotify MU Channel.

```yaml
action:
  - action: notify.send_message
    target:
      entity_id: notify.gotify_mu_notifications
    data:
      title: "Gigabyte Grove"
      message: "Home Assistant is online."
```

Home Assistant chooses the final entity ID, so use the entity picker rather than assuming the example ID.

### Gotify MU action

For Gotify-specific priority and Markdown controls, use:

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Greenhouse Alert"
      message: "**Temperature is above 100°F.**"
      priority: 8
      markdown: true
```

If multiple Gotify MU entries are configured, the action UI can target a specific config entry. If no entry is specified, the first loaded Gotify MU entry is used.

## Inbound / two-way messages

When a client token is configured and **Enable inbound messages** is on, the integration maintains a Gotify MU WebSocket connection.

Each incoming message from the configured Channel updates the integration's **Messages** event entity with:

- message ID
- Channel ID
- title
- message body
- priority
- date
- sender user ID
- sender name
- Gotify extras

The integration also creates an **Inbound connection** binary sensor. Its attributes expose reconnect count and the most recent stream error.

Messages sent by the same Home Assistant config entry are tagged and ignored by that entry's inbound stream, preventing an immediate send → receive automation loop.

### Safety behavior

Inbound Gotify MU messages are **events only**. The integration never interprets message text as a Home Assistant command and never executes services automatically. If you want a Chat Channel message to perform an action, create an explicit Home Assistant automation with the conditions and permissions appropriate for that action.

## Credential validation

Current Gotify MU servers provide a token-identity endpoint that returns the authenticated Channel metadata with the token redacted.

For older Gotify-compatible servers, application-token validation does **not** send a visible test message. The integration submits an intentionally incomplete `/message` request. Gotify authenticates before validating the body, so a valid token fails safely with HTTP 400 before message creation while an invalid token fails with HTTP 401/403.

## Reauthentication and reconfiguration

If Gotify MU rejects a stored token, Home Assistant starts a reauthentication flow instead of requiring the integration to be deleted and recreated.

**Reconfigure** allows you to change the server URL, display name, TLS validation, or replace/remove the optional client token. Removing the client token automatically disables inbound streaming while keeping outbound notifications intact.

The integration options expose the native pairing state as **Paired** or **Not paired**. A native pairing can be repaired with a new Gotify MU pairing code or removed independently without deleting the normal notification integration.

Removing a native pairing first revokes the shared bridge credential on Gotify MU. A force-local-remove recovery option is available when the remote server is unavailable or the remote pairing has already been replaced; use it only when the Gotify MU side will be cleaned up separately.

A paired entry also exposes a **Native bridge** connectivity binary sensor. Its attributes include bridge status, repair-required state, queued events, retry count, dropped-event count, last sent/received timestamps, and the last delivery error. Transient outbound failures use bounded exponential retry before an event is counted as dropped.

## Security

- Tokens are stored in Home Assistant config-entry storage, not `configuration.yaml`.
- Diagnostics redact application tokens, client tokens, the native shared secret, and private webhook identifiers/URLs.
- The application token is never included in the config-entry unique ID.
- Current Gotify MU servers return application identity with the token field removed.
- Use HTTPS when the Gotify MU server is reached over an untrusted network.
- Disable TLS verification only when you intentionally trust the target server/network.
- Inbound messages never execute Home Assistant actions on their own.
- Native webhook requests require the exact shared Bearer secret and only fire Home Assistant events.
- The one-time Gotify MU pairing code is never persisted by Home Assistant.

## Compatibility

The integration publishes through Gotify's compatible API:

```text
POST /message
X-Gotify-Key: <application-token>
```

Gotify MU-specific capabilities are additive. Outbound-only operation remains compatible with Gotify-style servers that do not expose the MU identity endpoint.

## Development

The repository includes:

- Python compile and JSON validation
- Ruff linting
- Hassfest validation
- Home Assistant config-flow tests
- Locked branding integrity validation

See [CHANGELOG.md](CHANGELOG.md) for release history.

### 1.0 release

Gotify MU for Home Assistant 1.0 is the stable integration baseline for Gotify MU 1.0. The native pairing contract is versioned and validated together with the server release, while the existing application-token notification and optional client-token inbound-message paths remain supported.

## License

MIT

## Branding

The branding in this repository is the canonical **Gotify-MU for Home Assistant** artwork supplied for this project. These files must not be regenerated, recolored, redrawn, or silently replaced during normal code, documentation, CI, or release work.

Canonical source assets:

- `custom_components/gotify_mu/brand/gotify-mu-ha-banner.png` — full horizontal banner, 1600×500
- `custom_components/gotify_mu/brand/gotify-mu-ha-logo.png` — full project logo, 1024×1024
- `custom_components/gotify_mu/brand/gotify-mu-ha-icon.png` — square integration icon, 1024×1024
- `custom_components/gotify_mu/brand/gotify-mu-ha-banner-q.png` — alternate/optimized banner supplied with the branding set
- `custom_components/gotify_mu/brand/gotify-mu-ha-logo-q.png` — alternate/optimized logo supplied with the branding set
- `custom_components/gotify_mu/brand/gotify-mu-ha-icon-q.png` — alternate/optimized icon supplied with the branding set

Compatibility aliases used by Home Assistant and repository documentation:

- `custom_components/gotify_mu/brand/banner.png`
- `custom_components/gotify_mu/brand/logo.png`
- `custom_components/gotify_mu/brand/icon.png`

The aliases above point to the exact canonical non-`-q` artwork.

Branding integrity is enforced by CI using `.github/branding-lock.json` and `scripts/check_branding.py`. Any unexpected change to one of the six approved assets, its dimensions, or one of the compatibility aliases fails validation. Intentional future branding changes therefore require an explicit update to both the assets and the branding lock.

<p align="center">
  <img src="https://raw.githubusercontent.com/gigabytegrove/gotify-mu-ha/main/custom_components/gotify_mu/brand/gotify-mu-ha-icon.png" alt="Gotify MU for Home Assistant icon" width="220">
</p>
