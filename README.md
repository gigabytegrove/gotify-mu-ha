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
- Camera/image notifications that upload real image bytes to Gotify MU for mobile and remote access
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

The standard Home Assistant notify entity intentionally remains a text/title path. Use `gotify_mu.send` for image notifications so the integration can capture, validate, stage, and attach the image using Gotify MU's media contract.

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

### Doorbell and camera image notifications

For a camera entity, use `image_entity`. Home Assistant captures a fresh frame at the moment the action runs, uploads the actual image bytes to Gotify MU using the configured application token, and then sends the message with the returned staged attachment ID.

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Front Door"
      message: "Someone is at the door."
      priority: 8
      image_entity: camera.front_door
```

The phone never needs access to the Home Assistant camera URL. Gotify MU hosts the staged image, generates its canonical image extras, and serves the same attachment to Gotify MU Web, Channel/Chat history, and Android's normal Big Image notification path. This means the image remains available while the phone is on cellular even when Home Assistant and the camera are LAN-only.

Home Assistant `image.*` entities use the same `image_entity` field:

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Latest Snapshot"
      message: "A new snapshot is available."
      image_entity: image.latest_snapshot
```

For an advanced HTTP/HTTPS source, use `image_url`:

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Driveway"
      message: "Motion detected."
      priority: 7
      image_url: "https://camera.example.com/current.jpg"
```

The integration downloads the URL inside Home Assistant, validates that the response is a supported image, enforces a bounded size, and uploads the bytes to Gotify MU. The original URL is not forwarded to the phone or written into Gotify extras. `image_entity` and `image_url` are mutually exclusive.

If image capture, download, validation, or upload fails, the action fails clearly instead of silently sending a text-only notification. A message-send failure after successful staging leaves the normal temporary server-side orphan for Gotify MU to expire; the integration does not attempt destructive cleanup.

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

### Home Assistant Repairs

If Gotify MU rejects the stored native bridge credential, the integration creates an actionable **Repairs** issue in Home Assistant. The issue directs the user to repair native pairing with a new one-time Gotify MU pairing code. The repair issue is cleared automatically after the bridge successfully reconnects, after a successful re-pair, when native pairing is removed, or when the integration entry itself is removed.

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

The integration publishes text notifications through Gotify's compatible API:

```text
POST /message
X-Gotify-Key: <application-token>
```

Image notifications additionally use Gotify MU's staged attachment endpoint:

```text
POST /application/current/attachment
X-Gotify-Key: <application-token>
Content-Type: multipart/form-data
```

The returned staged attachment ID is supplied to `POST /message` as `attachmentIds`. The integration does not invent public media URLs or manually build `gotify-mu::display.images` / `client::notification.bigImageUrl`; Gotify MU owns that canonical contract.

Gotify MU-specific capabilities are additive. Text-only outbound operation remains compatible with Gotify-style servers that do not expose the MU identity or staged attachment endpoints.

## Development

The repository includes:

- Python compile and JSON validation
- Ruff linting
- Hassfest validation
- Home Assistant config-flow and native-pairing tests
- Runtime regression tests for notification delivery, service actions, inbound streaming, event entities, and connection sensors
- Home Assistant Repairs regression coverage
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
