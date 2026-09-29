# Monita for Home Assistant — Complete Feature & Usage Guide

This is the canonical user-facing guide for every supported Monita for Home Assistant feature. Monita for Home Assistant was formerly Gotify-MU for Home Assistant.

The integration is designed around three separate paths:

1. **Server-centric outbound notifications** — Home Assistant connects to one Monita server with a client token, discovers accessible Channels, and publishes to the selected Channel using Monita's `appid` routing.
2. **Realtime inbound Channel messages** — the same server connection listens to Monita and filters messages to the Channels selected in Home Assistant.
3. **Native Home Assistant bridge** — an optional paired, authenticated event bridge between Home Assistant and Monita.

Legacy per-Channel application-token entries remain supported for upgrade compatibility.

## Product-name transition

Monita for Home Assistant is the successor name for **Gotify-MU for Home Assistant**. The rebrand does not rename Home Assistant's technical integration domain in this release.

For compatibility, existing YAML and stored objects continue to use:

- `gotify_mu` as the Home Assistant integration domain
- `gotify_mu.send` as the Push Message action ID
- `custom_components/gotify_mu` as the custom component directory
- `homeassistant::gotify_mu` as the existing origin-extra namespace used for loop prevention

These identifiers are compatibility contracts, not the active product name.

---

## 1. Connection and credential model

### New server-centric setup

A new Home Assistant config entry represents **one Monita server**, not one Channel.

Required:

- Monita server URL
- Monita client token
- TLS verification preference

During setup, Home Assistant:

1. verifies the server is reachable;
2. validates the client token against the current-user endpoint;
3. queries `GET /application` for the Channels the account can access;
4. displays those Channels in a multi-select list;
5. stores only the Channel IDs you choose to expose.

The same client token is then used for Channel discovery, inbound WebSocket messages, and normal Push Message publishing.

To create the token in Monita, open **Clients → Create Client**, give it a recognizable name such as **Home Assistant**, choose the desired inactivity expiration, create it, and copy the token Monita displays.

### Channel permissions

Monita returns the current account's effective role for each Channel. Home Assistant uses that metadata to determine whether the Channel is push-capable.

Roles that can publish are:

- owner
- manager
- publisher
- member when that Channel allows member posting

A read-only Channel can still be selected so inbound messages from it reach Home Assistant, but it does not receive a push-capable notification entity.

### Legacy per-Channel entries

Entries created before the server-centric model may still contain an application token and a single Channel ID.

Those entries continue to work. Migration to config-entry version 3 preserves the old unique ID and entity identity while adding the selected-Channel option internally.

This avoids breaking existing dashboards and automations.

---

## 2. Multiple Channels and Manage Channels

You no longer add the integration once per Channel.

Example: one Monita server may expose:

- Security
- Home
- Greenhouse
- Server Alerts
- Doorbells
- Infrastructure

During initial setup, choose any combination of those Channels.

Later, open:

**Settings → Devices & services → Monita → Configure → Manage Channels**

Every time that screen opens, Home Assistant queries Monita again. Newly created Channels appear automatically, deleted Channels disappear, and role changes are reflected in the labels.

Saving the selection reloads the integration.

For each selected push-capable Channel, Home Assistant creates a separate notify entity. All selected Channels share the same server connection, WebSocket, credentials, diagnostics, and native bridge.

---

## 3. Standard Home Assistant notify entities

Each selected Channel that the configured Monita account can post to becomes a standard Home Assistant notify entity.

Example:

```yaml
action:
  - action: notify.send_message
    target:
      entity_id: notify.security
    data:
      title: "Security"
      message: "Front door opened."
```

The exact entity ID is assigned by Home Assistant. Use the entity picker rather than assuming the example ID.

The notify entity exposes non-secret Channel metadata including:

- Channel ID
- Channel name
- current Channel role
- Channel type

### Default priority

The notify entities use the integration's configured **Default priority**.

Configure it from:

**Settings → Devices & services → Monita → Configure → Notifications and inbound messages**

Priority range: 0 through 10. The default is 5.

---

## 4. Push Message action (`gotify_mu.send`)

The Home Assistant action picker presents this as **Push Message**.

The technical action ID remains `gotify_mu.send` so existing automations continue working.

Supported fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `message` | Yes | Notification/message body |
| `channel` | Recommended | Monita notify entity representing the destination Channel |
| `title` | No | Notification title |
| `priority` | No | Per-message Monita priority from 0–10 |
| `markdown` | No | Enables Gotify-compatible Markdown display extras |
| `entry_id` | No | Legacy/advanced server-entry targeting |
| `image_entity` | No | Captures a current `camera.*` or `image.*` image |
| `image_url` | No | Downloads an HTTP/HTTPS image inside Home Assistant |
| `extras` | No | Advanced caller-supplied extras |

`image_entity` and `image_url` are mutually exclusive.

When a server exposes more than one Channel, choose **Channel** in the action editor. The picker shows Home Assistant notify entities, so users do not need to know numeric Monita Channel IDs.

### Basic Push Message

```yaml
action:
  - action: gotify_mu.send
    data:
      channel: notify.security
      title: "Security"
      message: "Front door opened."
```

### Priority and Markdown

```yaml
action:
  - action: gotify_mu.send
    data:
      channel: notify.greenhouse
      title: "Greenhouse"
      message: "**Temperature is above 100°F.**"
      priority: 8
      markdown: true
```

### Compatibility behavior

Older automations that specify `entry_id` remain supported. If the resolved entry exposes exactly one Channel, the Channel can still be inferred.

If an entry exposes multiple Channels and no Channel target is supplied, the action fails with a clear request to choose a Channel rather than guessing where to send the message.

### Advanced extras

Caller-supplied extras are preserved.

The integration adds its origin marker:

```json
{
  "homeassistant::gotify_mu": {
    "entry_id": "...",
    "channel_id": 7,
    "source": "monita-ha"
  }
}
```

That marker supports loop prevention while preserving the caller's existing extras.

---

## 5. Image notifications

Image notifications are designed for cameras, doorbells, snapshots, dashboards, and other security/home-automation events where the image must still work when the phone is away from the Home Assistant LAN.

The integration does **not** simply pass a Home Assistant camera URL to the phone.

Instead:

```text
Home Assistant captures/downloads image
        ↓
Home Assistant validates image bytes
        ↓
Home Assistant uploads image to Monita
        ↓
Monita stages/hosts the attachment
        ↓
Message is created with attachmentIds
        ↓
Web / Android / Channel history use the Monita-hosted image
```

This means the phone does not need direct access to:

- Home Assistant
- the camera
- a private camera URL
- the original image source URL

### Camera usability

For a live camera frame, use `image_entity` with a `camera.*` entity.

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Front Door"
      message: "Someone is at the door."
      priority: 8
      image_entity: camera.front_door
```

When the automation runs, Home Assistant requests a fresh camera image at that moment.

Use this for:

- doorbell person detection
- driveway motion
- package detection
- gate cameras
- garage cameras
- security alerts

### Doorbell example

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Doorbell"
      message: "Person detected."
      priority: 9
      image_entity: camera.front_door
```

Expected behavior with a compatible Monita server/client stack:

1. Home Assistant retrieves the current camera frame.
2. Home Assistant uploads the actual image bytes to Monita.
3. Monita creates the message with the staged attachment.
4. Monita Web shows the image with the message.
5. Monita for Android history shows the same image.
6. Android can use the first image as the notification's Big Image.
7. The image remains reachable while the phone is on cellular.
8. Protected Channel notification-redaction rules remain a client/server concern and are not bypassed by Home Assistant.

### Home Assistant `image.*` entities

The same field supports current Home Assistant image entities.

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Latest Snapshot"
      message: "A new snapshot is available."
      image_entity: image.latest_snapshot
```

Home Assistant retrieves the image through its supported image entity API.

The integration does not read arbitrary filesystem paths supplied by the service caller.

### Advanced `image_url`

Use `image_url` when the source is an HTTP or HTTPS image.

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Driveway"
      message: "Motion detected."
      priority: 7
      image_url: "https://camera.example.com/current.jpg"
```

Home Assistant downloads the image first and then uploads the bytes to Monita.

The original URL is not used as the phone-facing attachment.

This is useful for:

- authenticated image-producing services reachable by Home Assistant
- local HTTP snapshot endpoints
- temporary signed image URLs
- external image generators

### Image safety and validation

For `image_url`, the integration:

- permits HTTP and HTTPS only
- uses Home Assistant's shared aiohttp session
- honors the entry's TLS verification setting
- follows HTTP redirects
- rejects redirects to unsupported URL schemes
- limits the image to 10 MiB
- validates the response MIME type
- validates the actual image byte signature
- rejects HTML or login/error pages pretending to be images
- does not place the source URL in Gotify extras
- avoids exposing secret query-string values in integration error messages

Supported image types:

- JPEG
- PNG
- GIF
- WebP

### Server-centric image compatibility

Text and Markdown Push Message publishing is fully server-centric and uses one client token plus the selected Channel ID.

With **Monita 1.1.7 or newer**, Monita for Home Assistant 1.5.0 can send a captured/downloaded image directly into a selected **Chat Channel** when the server advertises the `chatImages` capability. The image is uploaded as an authenticated Chat attachment and stored with the Chat message.

Legacy per-Channel application-token entries continue to use the staged attachment workflow. For server-centric entries, image delivery to unsupported servers or to Notification Channels without a supported image route fails clearly instead of silently sending a text-only message.

The integration always checks the server capability and selected Channel type before choosing the direct Chat-image path.

### Failure behavior

Image requests fail closed.

If the user asks for an image and any of these fail:

- camera capture
- image entity retrieval
- URL download
- image validation
- staged upload

then the Home Assistant action fails.

The integration does **not** silently turn:

```text
Front Door + requested image
```

into:

```text
Front Door without image
```

This is intentional because silent image loss can make security-camera automations misleading.

### Image upload contracts

For legacy per-Channel application-token entries, images are uploaded with the configured application token to:

```text
POST /application/current/attachment
X-Gotify-Key: <application-token>
Content-Type: multipart/form-data
```

The returned staged ID is sent through the normal message API:

```json
{
  "attachmentIds": [123]
}
```

Home Assistant does not manually create:

- `gotify-mu::display.images`
- `client::notification.bigImageUrl`
- public Monita media URLs

Monita owns those canonical fields.

For server-centric Chat Channels on Monita 1.1.7+, the integration instead uses Monita's authenticated Chat-image multipart route with the client token and selected Channel ID. That route stores the image directly on the Chat message and preserves the caller's title/message, priority, Markdown metadata, extras, and Home Assistant origin marker.

### Multiple-image readiness

The API client already accepts a list of staged attachment IDs.

The current Home Assistant service UI exposes one primary image source, but the client contract is ready for future multi-image support without redesigning the message API.

---

## 6. Realtime inbound Channel messages

Realtime inbound messages use the same Monita client token as the server-centric connection.

Enable or disable inbound streaming from:

**Settings → Devices & services → Monita → Configure → Notifications and inbound messages**

When enabled, the integration maintains **one WebSocket connection per Monita server** and accepts messages only from the Channels currently selected in **Manage Channels**.

### Messages event entity

The integration creates one Home Assistant event entity named **Messages** for the server connection.

Each incoming message from a selected Monita Channel exposes:

- `message_id`
- `channel_id`
- `channel_name`
- `title`
- `message`
- `priority`
- `date`
- `sender_user_id`
- `sender_name`
- `extras`

Use the Channel ID/name in Home Assistant automation conditions when different selected Channels should trigger different behavior.

Inbound message text is never automatically interpreted as a Home Assistant command.

### Loop prevention

Messages pushed by the same Home Assistant config entry contain the integration origin marker, including the destination Channel ID.

The same server entry ignores those loopback messages on its inbound stream.

### Inbound connection sensor

When inbound messages are enabled, the integration creates an **Inbound connection** connectivity binary sensor for the Monita server.

It exposes:

- connected/disconnected state
- reconnect count
- most recent stream error

The WebSocket automatically reconnects using bounded backoff after ordinary connection failures. Client-token authentication failures trigger Home Assistant reauthentication rather than endlessly reconnecting.

---

## 7. Native Home Assistant pairing

Native pairing is an optional feature separate from normal notification publishing and client-token inbound messages.

It creates an authenticated bidirectional event bridge:

```text
Monita events → Home Assistant event bus
Home Assistant event bus → Monita
```

It does not require a Home Assistant Long-Lived Access Token.

### Pairing

In Monita:

1. Create or open a Home Assistant native connection.
2. Generate a one-time pairing code.

The pairing code has the form:

```text
12.<random-secret>
```

Then in Home Assistant:

**Settings → Devices & services → Monita → Configure → Native Home Assistant pairing**

Enter the pairing code.

Pairing codes:

- are one-time use
- expire after 15 minutes
- are never persisted by Home Assistant

### Home Assistant callback URL

Home Assistant attempts to determine a reachable webhook URL automatically.

The pairing screen shows the detected URL.

You can override it when:

- Home Assistant selected an internal URL that Monita cannot reach
- a reverse proxy URL must be used
- routing requires a different reachable hostname

If Home Assistant cannot determine a usable URL, an override is required.

### Monita → Home Assistant

Monita posts authenticated event payloads to a private Home Assistant webhook.

The integration:

- requires the exact Bearer secret
- validates the event payload
- fires the supplied event type on the Home Assistant event bus
- never converts incoming data directly into arbitrary Home Assistant service calls

### Home Assistant → Monita

The bridge listens to Home Assistant events and forwards them to the paired Monita event endpoint.

Monita applies the configured routing/filtering rules on its side.

The bridge suppresses immediate loopback of events that originated through its own inbound webhook.

### Delivery reliability

Transient Home Assistant → Monita event-delivery failures use bounded retries with backoff.

The bridge tracks:

- queued events
- retry count
- dropped events
- last successful send
- last successful receive
- last error

A bounded queue protects Home Assistant from unbounded memory growth during extended failures.

---

## 8. Native bridge health sensor

When native pairing is configured, the integration creates a **Native bridge** connectivity binary sensor.

Its attributes include:

- `status`
- `repair_required`
- `queued_events`
- `retry_count`
- `dropped_events`
- `last_sent_at`
- `last_received_at`
- `last_error`

Possible operational states include:

- paired
- connected
- degraded
- repair required

Use this sensor to monitor native integration health in dashboards or automations.

---

## 9. Repairing native pairing

If Monita rejects the stored native bridge credential, the integration marks the bridge as requiring repair.

Home Assistant also creates a Repairs issue.

To repair:

**Settings → Devices & services → Repairs**

or:

**Settings → Devices & services → Monita → Configure → Native Home Assistant pairing → Repair pairing**

Generate a new one-time pairing code in Monita and pair again.

Repairing native pairing does not delete or replace:

- the Monita server/client credential
- selected Channels
- Channel notify entities
- the **Push Message** action (`gotify_mu.send`)
- legacy application-token credentials on upgraded per-Channel entries
- the normal Monita config entry

The Repairs issue clears automatically after successful recovery.

---

## 10. Removing native pairing

Native pairing can be removed independently from the normal Monita integration.

Normal removal:

1. Home Assistant authenticates to Monita with the stored bridge secret.
2. Monita revokes the native connection.
3. Home Assistant removes the local native bridge credentials.
4. The normal notification integration remains configured.

### Force local removal

A recovery-only **Force local removal** option is available when:

- the remote connection was already deleted
- the bridge credential was replaced
- Monita is unreachable
- remote revoke cannot succeed

Use this only when the Monita side will be cleaned up separately.

---

## 11. Reauthentication

For a new server-centric entry, reauthentication replaces the Monita **client token** and re-queries the server for accessible Channels.

Home Assistant preserves selected Channel IDs that are still accessible. If none of the previous selections remain accessible, the integration falls back to the Channels returned by the newly authenticated account so the entry is not left unusable.

Legacy per-Channel entries retain their application-token reauthentication path.

---

## 12. Reconfiguration

Use **Reconfigure** to change connection settings without deleting the integration.

For server-centric entries, supported changes are:

- Monita server URL
- TLS certificate verification
- replacement client token

Channel selection is managed separately through **Configure → Manage Channels** so changing Channels does not require touching credentials.

Legacy per-Channel entries retain their earlier application-token/client-token reconfiguration behavior.

---

## 13. Integration options

Open:

**Settings → Devices & services → Monita → Configure**

The options menu exposes:

### Manage Channels

Queries Monita live and displays every Channel the configured account can currently access.

Use this whenever:

- a new Channel was added to Monita;
- a Channel was deleted;
- a user's Channel role changed;
- you want Home Assistant to stop exposing a Channel;
- you want to add another Channel without creating another integration entry.

Saving the list reloads the integration. Push-capable selected Channels get notification entities; selected read-only Channels remain available for inbound messages.

### Notifications and inbound messages

**Default priority** controls the priority used by Channel notification entities. Range: 0–10; default: 5.

**Enable inbound messages** controls the single server WebSocket used to expose messages from the selected Channels.

### Native Home Assistant pairing

Manages the optional paired event bridge independently from normal Channel publishing and inbound messages.

---

## 14. TLS verification

TLS certificate verification is enabled by default.

Keep it enabled whenever possible.

Disable it only for a trusted private deployment using a certificate Home Assistant cannot validate, such as a deliberate self-signed environment.

The setting applies to the integration's Monita HTTPS traffic and to `image_url` download behavior where applicable.

---

## 15. Diagnostics

Home Assistant config-entry diagnostics include useful non-secret operational information such as:

- selected Channel IDs
- selected Channel names
- effective Channel roles
- whether each selected Channel is push-capable
- inbound enabled state
- stream connection status
- reconnect count
- most recent stream error
- native pairing state
- native bridge status
- queue depth
- retry count
- dropped-event count
- last sent/received timestamps
- last native bridge error

Diagnostics redact:

- client token
- legacy application token
- native shared secret
- private native webhook ID
- private native webhook URL

Image bytes are not included in diagnostics.

---

## 16. Security model

The integration is intentionally conservative.

- Application/client tokens live in Home Assistant config-entry storage rather than `configuration.yaml`.
- Raw application tokens are not used as config-entry unique IDs.
- One-time native pairing codes are not persisted.
- Native shared secrets are redacted from diagnostics.
- Inbound Monita messages are events only.
- Native webhook payloads can fire Home Assistant events but cannot directly execute arbitrary services.
- Native webhook authentication uses the exact Bearer secret.
- Image notifications upload image bytes rather than leaking Home Assistant authentication or private camera URLs to clients.
- Home Assistant tokens are never inserted into Gotify extras for image delivery.
- Large images are not embedded as base64 in Gotify message JSON.
- Image data is not stored in message text or extras by this integration.

---

## 17. Compatibility

### Server-centric text and Markdown publishing

New installations publish through Monita's Gotify-compatible message endpoint using the server client token and the destination Channel ID:

```text
POST /message
X-Gotify-Key: <client-token>
```

Example payload:

```json
{
  "appid": 8,
  "message": "Greenhouse temperature is high.",
  "priority": 8
}
```

Monita applies the authenticated account's Channel role before accepting the message. Home Assistant exposes push-capable notification entities only for Channels the account can post to.

### Legacy application-token publishing

Existing per-Channel entries continue to use the older application-token route without requiring users to rebuild their integrations or automations.

This is also the current path used by staged image uploads.

### Gotify compatibility

The underlying message endpoint and headers remain Gotify-compatible where possible. Monita-specific multi-user Channel roles, selected-Channel management, and native bridge capabilities are additive.

### Image notifications

The current staged attachment contract is application-token scoped:

```text
POST /application/current/attachment
```

Legacy application-token Channel entries retain their staged-image delivery through `POST /application/current/attachment`. On **Monita 1.1.7+**, server-centric client-token entries can send captured images directly to selected **Chat Channels** through the authenticated Chat-image endpoint. The integration checks the server's `chatImages` capability and the destination Channel type before using that path. A server-centric image request targeting a Notification Channel, or a server that does not advertise Chat-image support, fails explicitly rather than silently dropping the image.

### Native bridge

Native pairing and bidirectional event forwarding are Monita-specific features and require compatible server support.

---

## 18. Common workflows

### Simple Channel notify entity

```yaml
action:
  - action: notify.send_message
    target:
      entity_id: notify.security
    data:
      title: "Security"
      message: "Front door opened."
```

### Push Message to a selected Channel

```yaml
action:
  - action: gotify_mu.send
    data:
      channel: notify.server_alerts
      title: "Server Alert"
      message: "Storage array is degraded."
      priority: 10
```

### Markdown Push Message

```yaml
action:
  - action: gotify_mu.send
    data:
      channel: notify.greenhouse
      title: "Daily Status"
      message: |
        **Temperature:** 87°F
        **Humidity:** 62%
      markdown: true
```

### Manage Channels after Monita grows

Open:

**Settings → Devices & services → Monita → Configure → Manage Channels**

The list is refreshed from the server each time. Select the new Channel and save; there is no need to add another Monita integration entry.

### Doorbell snapshot on a legacy image-capable entry

Until the server-centric staged-upload contract is available, existing application-token Channel entries continue to support:

```yaml
action:
  - action: gotify_mu.send
    data:
      title: "Front Door"
      message: "Person detected."
      priority: 9
      image_entity: camera.front_door
```

---

## 19. Feature availability summary

| Feature | New server connection | Legacy per-Channel entry | Native pairing |
| --- | :---: | :---: | :---: |
| Discover accessible Channels | Yes | If client token present | No |
| Select/manage multiple Channels | Yes | Yes after v3 migration when client token is present | No |
| Notify entity per push-capable Channel | Yes | Yes | No |
| **Push Message** text/Markdown | Yes | Yes | No |
| Priority/Markdown/extras | Yes | Yes | No |
| Camera/image notifications | Yes for Chat Channels on Monita 1.1.7+ | Yes | No |
| Realtime inbound selected Channels | Yes | With client token | No |
| Messages event entity | Yes | With client token | No |
| Inbound connection sensor | Yes | With client token | No |
| Native Monita → HA events | Independent | Independent | Required |
| Native HA → Monita events | Independent | Independent | Required |
| Native bridge health/Repairs | Independent | Independent | Required |

New installs use one client-token server connection for Channel discovery, publishing, inbound messages, and direct Chat-image delivery on Monita 1.1.7+. Legacy application-token entries remain supported for backward compatibility and staged-image delivery.
