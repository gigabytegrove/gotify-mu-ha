# Monita for Home Assistant

<p align="center">
  <img src="https://raw.githubusercontent.com/gigabytegrove/monita-ha/main/custom_components/gotify_mu/brand/monita-ha-icon.png" alt="Monita for Home Assistant" width="220"><br>
  <strong>Monita for Home Assistant</strong><br>
  <em>formerly Gotify-MU for Home Assistant</em>
</p>


A Home Assistant custom integration for **Monita**, the successor to Gotify-MU. It connects Home Assistant directly to the self-hosted Monita notification, messaging, and automation platform.

It provides native Home Assistant notification entities for Monita Channels, image notifications, optional realtime inbound Channel messages, and an authenticated native event bridge for two-way automations.

## Documentation

- **[Complete Feature & Usage Guide](docs/FEATURES.md)** — configuration, every supported feature, image-notification behavior, examples, security, troubleshooting-oriented health information, and credential requirements.
- **[Changelog](CHANGELOG.md)** — version-by-version changes and compatibility notes.
- **[Monita Rebrand & Upgrade Guide](docs/REBRANDING.md)** — explains the Gotify-MU → Monita transition and which technical identifiers intentionally remain unchanged.

The README covers installation and the most common workflows. The complete guide is the canonical reference for all supported functionality.

## Features

- UI setup through **Settings → Devices & services**
- No `configuration.yaml` changes required
- Standard Home Assistant `notify` entity
- **Push Message** action (`gotify_mu.send`) with Channel targeting, priority, Markdown, and advanced extras
- Camera/image notifications that upload real image bytes to Monita for mobile and remote access
- Exact application-token validation without creating a test notification
- Stable Channel identity on current Monita servers
- One Monita server connection can discover and expose multiple Channels through a client token
- Home Assistant `event` entity containing inbound Channel messages
- Connection-status binary sensor for the inbound WebSocket
- Automatic reconnect with bounded backoff
- Reauthentication and reconfiguration flows
- Optional native Home Assistant pairing with Monita, with no Home Assistant Long-Lived Access Token required
- Authenticated Monita → Home Assistant webhook events and Home Assistant → Monita event forwarding
- Native pairing can be repaired or removed without deleting the normal Monita integration
- Native bridge health sensor with Paired / Connected / Degraded / Repair required visibility
- Bounded retry/backoff for transient Home Assistant → Monita event-delivery failures
- Authenticated remote revoke when native pairing is removed
- Live **Manage Channels** UI to add or remove exposed Channels without adding another integration entry
- Config-entry diagnostics with credentials redacted
- TLS verification control for private/self-signed deployments
- HACS-compatible repository layout
- Legacy fallback for Gotify-compatible servers without the MU identity endpoint

### Feature documentation map

Every user-facing feature above is documented in the [Complete Feature & Usage Guide](docs/FEATURES.md):

| Area | Documentation |
| --- | --- |
| Setup, token roles, Channel identity, legacy validation | [Connection and credential model](docs/FEATURES.md#1-connection-and-credential-model) |
| Multiple Monita Channels | [Multiple Channels](docs/FEATURES.md#2-multiple-channels) |
| Standard Home Assistant notify entity | [Standard notify entity](docs/FEATURES.md#3-standard-home-assistant-notify-entity) |
| `gotify_mu.send`, priority, Markdown, extras | [Monita action](docs/FEATURES.md#4-gotify_musend-action) |
| Camera, image entity, and image URL notifications | [Image notifications](docs/FEATURES.md#5-image-notifications) |
| Realtime inbound Channel messages | [Realtime inbound messages](docs/FEATURES.md#6-realtime-inbound-channel-messages) |
| Native bidirectional Home Assistant bridge | [Native pairing](docs/FEATURES.md#7-native-home-assistant-pairing) |
| Connection and native bridge health sensors | [Native bridge health](docs/FEATURES.md#8-native-bridge-health-sensor) |
| Repairs, pairing repair/removal, force-local recovery | [Repairing native pairing](docs/FEATURES.md#9-repairing-native-pairing) |
| Reauthentication and reconfiguration | [Reauthentication](docs/FEATURES.md#11-reauthentication) |
| Default priority and inbound options | [Integration options](docs/FEATURES.md#13-integration-options) |
| TLS, diagnostics, credential redaction, security | [Security model](docs/FEATURES.md#16-security-model) |
| API/server compatibility and feature requirements | [Compatibility](docs/FEATURES.md#17-compatibility) |
| Copyable everyday examples | [Common workflows](docs/FEATURES.md#18-common-workflows) |

## Rebrand and upgrade compatibility

**Monita for Home Assistant was formerly Gotify-MU for Home Assistant.** The rebrand is intentionally non-destructive.

Existing installations keep the technical Home Assistant integration domain and service namespace:

- integration domain: `gotify_mu`
- custom component directory: `custom_components/gotify_mu`
- service action: `gotify_mu.send`
- existing config entries, entity unique IDs, automations, scripts, and stored credentials remain valid

You do **not** need to delete and recreate the integration just because the display name changed to Monita. The legacy technical identifiers remain in place for upgrade compatibility and may be migrated only through a separately documented compatibility-safe migration in a future release.

The underlying HTTP/WebSocket API remains Gotify-compatible where documented. References to Gotify in protocol field names or compatibility notes are technical compatibility references, not the active product name.

## Requirements

For new installations, Home Assistant connects to **one Monita server** with:

- the Monita server URL
- a Monita **client token** for the account Home Assistant should use
- TLS verification enabled unless you deliberately use a trusted private/self-signed deployment

Home Assistant uses that credential to query the server for every Channel the account can access. You then choose which Channels should be exposed to Home Assistant.

The selected Channel list is not permanent. Open **Settings → Devices & services → Monita → Configure → Manage Channels** at any time to query the server again and add or remove Channels.

Legacy per-Channel application-token entries remain supported so existing installs and automations are not broken.

## Installation

### HACS

Add this repository to HACS as a **Custom repository** with category **Integration**:

```text
https://github.com/gigabytegrove/monita-ha
```

Install **Monita for Home Assistant**, then restart Home Assistant.

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

**Settings → Devices & services → Add integration → Monita for Home Assistant**

Enter:

- **Server URL** — for example `https://push.example.com`
- **Client token** — a Monita client token for the account Home Assistant should use
- **Verify TLS certificate** — keep enabled unless you deliberately use a trusted private certificate that Home Assistant cannot validate

To create the credential in Monita, open **Clients → Create Client**, give it a recognizable name such as **Home Assistant**, choose the desired inactivity expiration, create it, and copy the token Monita displays. Paste that token into the Home Assistant setup form.

Home Assistant immediately queries Monita for the Channels that account can access. The next screen is **Choose Channels**, where you can select one, several, or all of them.

For every selected Channel that the account is allowed to post to, Home Assistant creates its own notification entity. Selected read-only Channels remain available to inbound message handling but do not get a push-capable notification entity.

### Managing Channels later

You do not need to add Monita again when the server grows.

Open:

**Settings → Devices & services → Monita → Configure → Manage Channels**

The integration queries Monita live and refreshes the Channel list. Select the Channels you want Home Assistant to expose and save. The integration reloads automatically.

### Native Monita pairing

Native pairing is optional and additive. The application token remains the credential used by the notify entity and `gotify_mu.send`, while native pairing adds an authenticated event bridge between Monita and Home Assistant.

In Monita, create or open a Home Assistant connection using the **Monita for Home Assistant** native integration and generate its one-time pairing code. The code has the form:

```text
12.<random-secret>
```

Then in Home Assistant open the configured **Monita** integration, choose **Configure → Native Home Assistant pairing → Pair with Monita server**, and enter the pairing code.

Home Assistant generates a random private webhook ID automatically. It shows the callback URL it detected and always allows an optional base-URL override, which is useful when Home Assistant chooses an internal address that the Monita server cannot actually reach. If no usable URL can be determined automatically, the override becomes required.

A successful pairing stores only the native integration ID, shared secret, event path, and webhook details in Home Assistant config-entry storage. The one-time pairing code is never stored.

The native bridge supports both directions:

- **Monita → Home Assistant:** Monita posts authenticated payloads to the private HA webhook. The integration validates the Bearer secret and fires the supplied `eventType` on the Home Assistant event bus with the supplied `data`.
- **Home Assistant → Monita:** Home Assistant events are posted to the paired Monita event endpoint using the shared Bearer secret. Monita applies its configured event type, entity ID, field, and value filters before routing matching events into the selected Channel.

Inbound native bridge payloads are events only. They are never converted into arbitrary Home Assistant service calls.

## Sending notifications

Home Assistant creates a separate notification entity for every selected Monita Channel that your account can post to. That means Channels such as **Security**, **Home**, **Greenhouse**, and **Server Alerts** can all be targets from one Monita server connection.

The standard Home Assistant path remains available:

```yaml
action:
  - action: notify.send_message
    target:
      entity_id: notify.security
    data:
      title: "Security"
      message: "Front door opened."
```

Use Home Assistant's entity picker rather than assuming the generated entity ID.

### Push Message

Monita also exposes a dedicated **Push Message** action in Home Assistant. Its compatibility-safe technical action ID remains `gotify_mu.send`.

The action editor includes a **Channel** picker. Choose the Monita notification entity for the destination Channel, then set the title, message, priority, Markdown, or advanced extras.

```yaml
action:
  - action: gotify_mu.send
    data:
      channel: notify.security
      title: "Security Alert"
      message: "**Front door opened.**"
      priority: 9
      markdown: true
```

When one server exposes several Channels, the Channel target is required. Existing automations that use the older `entry_id` targeting remain supported for compatibility.

### Doorbell and camera image notifications

For a camera entity, use `image_entity`. Home Assistant captures a fresh frame at the moment the action runs, uploads the actual image bytes to Monita using the configured application token, and then sends the message with the returned staged attachment ID.

**When to use it:** choose `image_entity` for doorbells and Home Assistant-managed cameras/images. It is the preferred workflow because Home Assistant performs the capture directly; the phone never needs a camera URL, Home Assistant login, or LAN access.

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Front Door"
      message: "Someone is at the door."
      priority: 8
      image_entity: camera.front_door
```

The phone never needs access to the Home Assistant camera URL. Monita hosts the staged image, generates its canonical image extras, and serves the same attachment to Monita Web, Channel/Chat history, and Android's normal Big Image notification path. This means the image remains available while the phone is on cellular even when Home Assistant and the camera are LAN-only.

Home Assistant `image.*` entities use the same `image_entity` field:

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Latest Snapshot"
      message: "A new snapshot is available."
      image_entity: image.latest_snapshot
```

For an advanced HTTP/HTTPS source, use `image_url`. Use this only when the image already exists at a URL that Home Assistant itself can retrieve; `image_entity` is preferred for Home Assistant camera/image entities:

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Driveway"
      message: "Motion detected."
      priority: 7
      image_url: "https://camera.example.com/current.jpg"
```

The integration downloads the URL inside Home Assistant, validates that the response is a supported image, enforces a 10 MiB maximum, and uploads the bytes to Monita. JPEG, PNG, GIF, and WebP are supported. The original URL is not forwarded to the phone or written into Gotify extras. `image_entity` and `image_url` are mutually exclusive.

For the complete image lifecycle, security behavior, failure semantics, use cases, and compatibility requirements, see [Image notifications](docs/FEATURES.md#5-image-notifications).

If image capture, download, validation, or upload fails, the action fails clearly instead of silently sending a text-only notification. A message-send failure after successful staging leaves the normal temporary server-side orphan for Monita to expire; the integration does not attempt destructive cleanup.

## Inbound / two-way messages

When **Enable inbound messages** is on, the integration maintains one Monita WebSocket connection for the server. Messages are filtered to the Channels selected in **Manage Channels**.

Each incoming message from a selected Channel updates the integration's **Messages** event entity with:

- message ID
- Channel ID
- Channel name
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

Inbound Monita messages are **events only**. The integration never interprets message text as a Home Assistant command and never executes services automatically. If you want a Chat Channel message to perform an action, create an explicit Home Assistant automation with the conditions and permissions appropriate for that action.

## Credential validation

New server-centric connections validate the client token against Monita's current-user endpoint and then retrieve the accessible Channel list from `GET /application`.

Monita returns Channel role information with that list. Home Assistant uses it to distinguish push-capable Channels from read-only Channels.

Legacy application-token entries continue using the application identity endpoint and safe Gotify-compatible fallback introduced in earlier releases.

## Reauthentication and reconfiguration

If Monita rejects a stored token, Home Assistant starts a reauthentication flow instead of requiring the integration to be deleted and recreated.

**Reconfigure** allows a server-centric entry to change the server URL, TLS validation, or replace its client token. **Manage Channels** controls the Channel list independently. Legacy per-Channel entries retain their older reconfiguration behavior.

The integration options expose the native pairing state as **Paired** or **Not paired**. A native pairing can be repaired with a new Monita pairing code or removed independently without deleting the normal notification integration.

Removing a native pairing first revokes the shared bridge credential on Monita. A force-local-remove recovery option is available when the remote server is unavailable or the remote pairing has already been replaced; use it only when the Monita side will be cleaned up separately.

A paired entry also exposes a **Native bridge** connectivity binary sensor. Its attributes include bridge status, repair-required state, queued events, retry count, dropped-event count, last sent/received timestamps, and the last delivery error. Transient outbound failures use bounded exponential retry before an event is counted as dropped.

### Home Assistant Repairs

If Monita rejects the stored native bridge credential, the integration creates an actionable **Repairs** issue in Home Assistant. The issue directs the user to repair native pairing with a new one-time Monita pairing code. The repair issue is cleared automatically after the bridge successfully reconnects, after a successful re-pair, when native pairing is removed, or when the integration entry itself is removed.

## Security

- Tokens are stored in Home Assistant config-entry storage, not `configuration.yaml`.
- Diagnostics redact application tokens, client tokens, the native shared secret, and private webhook identifiers/URLs.
- The application token is never included in the config-entry unique ID.
- Current Monita servers return application identity with the token field removed.
- Use HTTPS when the Monita server is reached over an untrusted network.
- Disable TLS verification only when you intentionally trust the target server/network.
- Inbound messages never execute Home Assistant actions on their own.
- Native webhook requests require the exact shared Bearer secret and only fire Home Assistant events.
- The one-time Monita pairing code is never persisted by Home Assistant.

## Compatibility

For server-centric connections, Push Message uses Monita's Gotify-compatible message endpoint with the client token and the selected Channel ID:

```text
POST /message
X-Gotify-Key: <client-token>

{
  "appid": <selected-channel-id>,
  "message": "..."
}
```

Image notifications additionally use Monita's staged attachment endpoint:

```text
POST /application/current/attachment
X-Gotify-Key: <application-token>
Content-Type: multipart/form-data
```

The returned staged attachment ID is supplied to `POST /message` as `attachmentIds`. The integration does not invent public media URLs or manually build `gotify-mu::display.images` / `client::notification.bigImageUrl`; Monita owns that canonical contract.

Monita-specific capabilities are additive. Text-only outbound operation remains compatible with Gotify-style servers that do not expose the MU identity or staged attachment endpoints.

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

Monita for Home Assistant 1.0 is the stable integration baseline for Monita 1.0. The native pairing contract is versioned and validated together with the server release, while the existing application-token notification and optional client-token inbound-message paths remain supported.

## License

MIT

## Branding

**Monita for Home Assistant** is the active product identity. The supplied Monita brand sheet, logo treatment, app icon treatment, typography, and palette are the approved visual baseline for the rebrand.

Brand palette:

- Primary — `#2563EB`
- Blue — `#3B82F6`
- Cyan — `#06B6D4`
- Slate — `#0F172A`
- Gray — `#9CA3B8`

The active repository branding is Monita-only. The approved Monita artwork must not be regenerated, recolored, redrawn, or silently replaced during normal feature work. Branding changes require an explicit branding update and corresponding CI lock update.
