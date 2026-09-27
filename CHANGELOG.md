# Changelog

## 1.2.0 - 2026-09-27

### Added

- Real image notifications for `gotify_mu.send` using `camera.*`, `image.*`, or advanced HTTP/HTTPS image sources.
- Secure in-Home-Assistant image retrieval followed by multipart staging through `POST /application/current/attachment` with the configured Gotify MU application token.
- Staged attachment IDs on the normal `POST /message` payload while preserving priority, Markdown, caller extras, and the Home Assistant origin marker.
- Bounded image downloads, raster MIME/signature validation, and source-URL secret redaction behavior.
- Service UI selectors and doorbell/camera documentation for image notifications.
- Regression coverage for capture, download, staging, authentication, oversized/invalid content, failure-closed delivery, and recoverable staged orphans.

### Changed

- Standard Home Assistant `notify.send_message` remains the stable text/title path; image notifications use `gotify_mu.send`.
- Caller-supplied Gotify extras are merged with the integration origin marker instead of being replaced.

### Documentation

- Added a canonical complete feature and usage guide covering every user-facing integration capability, credential role, option, entity, health signal, repair path, security behavior, and compatibility requirement.
- Expanded image-notification documentation with practical doorbell/camera guidance, source selection, supported formats, the 10 MiB limit, remote/mobile behavior, and failure semantics.
- Added a README documentation map so every feature is directly discoverable.


## 1.1.0 - 2026-09-26

### Added

- Native Home Assistant Repairs issue when Gotify MU rejects the stored native bridge credential.
- Automatic repair-issue cleanup after successful bridge recovery, successful re-pairing, pairing removal, or integration removal.
- Regression coverage for the notify entity, `gotify_mu.send`, inbound WebSocket channel/self-loop filtering, inbound event entity payloads, and both connection binary sensors.
- Repairs regression coverage proving rejected native credentials create an actionable Home Assistant issue and successful recovery clears it.

### Changed

- Native bridge instances are now tied to their Home Assistant config-entry ID so repair issues remain unique across multiple Gotify MU entries.


## 1.0.3 - 2026-09-26

### Hardened

- Locked all six approved Gotify-MU for Home Assistant branding assets to their exact Git blob hashes and dimensions.
- Added CI validation that fails if any canonical branding asset changes unexpectedly.
- Added CI validation that requires `banner.png`, `logo.png`, and `icon.png` to remain byte-for-byte aliases of the approved canonical artwork.
- Added regression coverage confirming the options flow remains based on Home Assistant's `OptionsFlowWithReload`, so changes such as enabling or disabling inbound messages reload the integration and take effect.


## 1.0.2 - 2026-09-26

### Fixed

- Replaced the incorrect/stale Home Assistant branding aliases with the exact user-supplied canonical Gotify-MU for Home Assistant logo and icon.
- Added the canonical Gotify-MU for Home Assistant banner and updated the GitHub README to use it.
- Preserved all six supplied branding files in the repository and documented them as immutable project branding.
- Updated Home Assistant compatibility aliases (`logo.png`, `icon.png`, and `banner.png`) to the canonical non-`-q` artwork.


## 1.0.1 - 2026-09-26

### Fixed

- Restored the valid Gotify MU + Home Assistant logo and icon assets after the 1.0.0 branding PNGs were found to be truncated/corrupt.
- Updated README image references to use the raw repository assets directly so GitHub renders the complete branding reliably.


## 1.0.0 - 2026-09-26

Stable tandem release for Gotify MU 1.0. This promotes the validated native bridge baseline with application-token notifications, optional client-token inbound messages, native no-LLT pairing, authenticated bidirectional events, non-destructive repair, authenticated remote revoke, bridge health visibility, bounded delivery retry, reauthentication/reconfiguration, diagnostics redaction, and full Home Assistant validation coverage.


## 1.0.0-rc1 - 2026-09-26

Release candidate for the tandem Gotify MU 1.0 launch. Functionally identical to the validated 0.4.0 pre-1.0 hardening baseline, with versioning promoted for final cross-project compatibility validation against Gotify MU `release/v1.0.0-rc1`.

## 0.4.0 - 2026-09-26

Pre-1.0 native bridge hardening release.

### Added

- Native bridge connectivity binary sensor with Paired, Connected, Degraded, and Repair required health.
- Last sent/received timestamps, queue depth, retry count, dropped-event count, and last native delivery error.
- Bounded exponential retry for transient Home Assistant → Gotify MU event delivery failures.
- Authenticated remote native bridge revoke during unpair.
- Force-local-remove recovery path when remote revocation cannot be completed.
- Manual Home Assistant callback URL override even when Home Assistant auto-detects a URL.

### Fixed

- Treats Gotify MU HTTP 401/403/404 pairing responses as invalid pairing codes instead of generic pairing failures.
- Native repair replaces only the native bridge credentials and leaves application-token notifications and optional client-token inbound messages intact.
- Invalid inbound Bearer probes do not falsely mark a healthy bridge as repair-required.
- Diagnostics include non-secret native health information while continuing to redact the shared secret and private webhook details.

### Testing

- Adds real Home Assistant event-bus → Gotify MU delivery coverage.
- Adds pairing 401 coverage, manual callback override coverage, repair coverage, remote revoke/removal coverage, repair-required health coverage, and diagnostics redaction coverage.

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
