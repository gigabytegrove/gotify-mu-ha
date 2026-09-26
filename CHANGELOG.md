# Changelog

## 0.3.0 - 2026-09-26

### Added

- Native Gotify MU ↔ Home Assistant pairing using one-time Gotify MU pairing codes.
- Random private Home Assistant webhook registration for Gotify MU → Home Assistant events.
- Bearer-secret validation for native inbound events.
- Home Assistant event forwarding to the paired Gotify MU native event endpoint.
- Native pairing management in the integration options, including clear Paired / Not paired state, repair, and removal without deleting the normal Gotify MU integration.
- Automatic Home Assistant webhook URL discovery with a manual reachable-URL fallback only when Home Assistant cannot determine one.
- Native pairing and bridge coverage for successful pairing, invalid/expired/failed codes, invalid Bearer credentials, outbound event posting, and inbound event receipt.

### Changed

- Gotify MU options are split into notification/inbound-message settings and native Home Assistant pairing management.
- The webhook component is now an integration dependency.
- Integration version is now 0.3.0.

### Security

- Native shared secrets and private webhook identifiers/URLs are redacted from diagnostics.
- One-time pairing codes are never persisted.
- Native Gotify MU payloads can fire Home Assistant events only; they are never interpreted as service calls.
- Native webhook Bearer credentials are compared using constant-time secret comparison.

## 0.2.0 - 2026-09-26

### Added

- Dedicated Gotify MU HA integration logo and transparent Home Assistant connector icon based on the Gotify MU mascot.
- Exact application-token validation and Channel identity using the Gotify MU application identity endpoint when available.
- Safe legacy token-validation fallback that does not create a notification.
- Stable Channel-ID-based config-entry identity when supported by the server.
- Config-entry `runtime_data` architecture.
- Reauthentication flow for revoked or replaced credentials.
- Reconfiguration flow for server URL, Channel display name, TLS validation, and optional client-token replacement/removal.
- Optional realtime inbound Gotify MU messages over the client-token WebSocket stream.
- Home Assistant Event entity for inbound Channel messages.
- Inbound WebSocket connection-status binary sensor.
- Automatic stream reconnect with bounded exponential backoff.
- Loop prevention for messages sent by the same Home Assistant config entry.
- Explicit handling for authentication failures, rate limiting, server failures, connection errors, and request timeouts.
- Redacted config-entry diagnostics.
- Migration path from v0.1 config entries.
- Hassfest, Ruff, JSON, Python compile, and pytest validation workflow.

### Changed

- `gotify_mu.send` is registered at integration setup rather than per config entry.
- Notification entities advertise title support using Home Assistant's current `NotifyEntity` API.
- IoT classification is `local_push` for the direct self-hosted connection model.
- Optional client token is used only for Channel discovery/inbound subscription; application tokens remain the outbound publishing credential.

### Security

- Application/client tokens are redacted from diagnostics.
- Raw application tokens are never used as config-entry unique IDs.
- Inbound message text is exposed as event data only and is never executed automatically.

## 0.1.0 - 2026-09-26

- Initial Home Assistant custom integration.
- UI config flow.
- Gotify MU notification entity.
- `gotify_mu.send` action.
- Multiple config entries.
- HACS-compatible structure.
