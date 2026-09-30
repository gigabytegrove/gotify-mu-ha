# Changelog

## 1.8.0 - 2026-09-30

### Canonical Monita identity
- Added the canonical Home Assistant integration domain `monita` under `custom_components/monita`.
- New installations use `monita` and the canonical `monita.send` action.
- Retained the historical integration domain only as an existing-install compatibility component so previously stored config entries, entity identities, credentials, and automations remain loadable.
- The canonical and compatibility components resolve Monita Channel targets across both domains, allowing mixed transition states without binding the action to whichever component loads first.
- Canonical source classes use Monita naming; Gotify terminology remains only where it describes the compatible wire protocol or the historical compatibility layer.

### Messaging
- Added `@username` mention support to the current Monita server/Web clients and Android conversation rendering.
- Home Assistant message-control metadata remains compatible with Monita 1.2.0.

## 1.7.0 - 2026-09-30

### Per-message controls

- Added a Message controls multi-select to `monita.send`.
- Home Assistant can enable Assign to Me, Resolve, and Attach independently for each message.
- Messages without selected controls remain normal notifications without workflow buttons.

### Image delivery

- Refreshes Monita server capabilities before falling back to text-only when an image is requested, so an upgraded Monita server can accept images without first reloading the Home Assistant integration.
- Camera/image entity delivery remains supported on Notification and Chat Channels.

## 1.6.0 - 2026-09-30

### Monita-native automation namespace

- Added `monita.send` as the canonical Home Assistant action for Monita automations.
- Kept the historical integration service namespace as a compatibility alias so existing automations do not break during the transition.
- New documentation and examples use Monita terminology and the `monita.send` action.

### Notification Channel images

- Added direct camera/image delivery to Monita Notification Channels when the server advertises `notificationImages` support (Monita 1.1.9+).
- Preserved direct Chat image delivery through the existing `chatImages` capability.
- Older Monita servers no longer cause the entire alert to fail when an image is requested for a Notification Channel; Home Assistant sends the text notification and logs that the image was omitted.
- Image sends now preserve an explicit notification title through the multipart Monita image route.

### Compatibility

- Existing config entries, selected Channels, notification entities, native pairing, and stored credentials remain in place.
- Existing automations using the historical service alias continue to work, while new automations should use `monita.send`.

## 1.5.1 - 2026-09-29

### Maintenance

- Prepared the integration metadata for the HACS-ready 1.5.1 release.
- Added repository validation for HACS default-repository requirements.
- Removed stale Home Assistant development branches after their work was incorporated into `main`.
- Synchronized the README and release documentation with the manifest version.

### Compatibility

- No user-facing configuration migration is required from 1.5.0.
- The compatibility-safe technical domain remains `gotify_mu`, and existing config entries, selected Channels, entities, automations, credentials, and the `gotify_mu.send` action remain valid.

## 1.5.0 - 2026-09-28

### Added

- Direct Home Assistant camera/image delivery into Monita Chat Channels on Monita 1.1.7+ using the server-centric client token.
- Capability discovery for Monita's `chatImages` feature.
- Multipart Chat-image publishing that preserves priority, Markdown display metadata, caller extras, and the Home Assistant origin marker.
- Regression coverage for capability discovery, direct Chat image publishing, supported Chat routing, and failure-closed behavior on non-Chat Channels.

### Compatibility

- Existing application-token staged-image workflows remain unchanged.
- Server-centric image requests use the direct Chat-image route only when the selected Channel is a Chat and the server advertises `chatImages: true`.
- Image requests to unsupported servers or Notification Channels fail clearly instead of silently sending text without the requested image.

## 1.4.0 - 2026-09-27

### Added

- Server-centric setup: add one Monita server with a client token, query its accessible Channels, and select multiple Channels in one integration entry.
- **Manage Channels** in the Home Assistant options UI. Reopening it queries Monita live so newly created or removed Channels can be reflected without adding another integration entry.
- One Home Assistant notification entity per selected Channel that the configured Monita account is allowed to post to.
- Selected read-only Channels remain eligible for inbound-message filtering without being exposed as push-capable notification entities.
- **Push Message** as the user-facing Home Assistant action name for the compatibility-safe `gotify_mu.send` service.
- Channel targeting in Push Message through a Monita notification-entity picker.
- Channel name in inbound Home Assistant message-event data and selected-Channel details in diagnostics.

### Changed

- New installs use a Monita client token as the server credential instead of requiring one application token per Channel.
- Text and Markdown publishing can use one client token plus Monita's `appid` routing to reach any selected Channel the account is permitted to post to.
- Realtime inbound streaming now filters one server WebSocket to the complete selected Channel set.
- Legacy per-Channel application-token entries remain supported and migrate to config-entry version 3 without changing their existing entity identity.

### Compatibility

- The technical Home Assistant domain remains `gotify_mu` and the existing `gotify_mu.send` action ID remains valid.
- Existing `entry_id` Push Message automations continue to work. New automations should use the Channel picker.
- Existing application-token image workflows remain supported. Server-credential per-Channel staged image upload requires corresponding Monita server support and fails clearly rather than silently dropping the requested image.


## 1.3.0 - 2026-09-27

### Rebranded

- Renamed the user-facing integration to **Monita for Home Assistant**, formerly Gotify-MU for Home Assistant.
- Updated the Home Assistant manifest, HACS display name, config flows, options, services UI, entities, diagnostics terminology, Repairs text, release workflow titles, and user-facing runtime messages to the Monita brand.
- Adopted the approved Monita palette: Primary `#2563EB`, Blue `#3B82F6`, Cyan `#06B6D4`, Slate `#0F172A`, and Gray `#9CA3B8`.
- Added explicit rebrand/upgrade documentation so existing users understand that the name change does not require reconfiguration.

### Compatibility

- Preserved the Home Assistant integration domain `gotify_mu`, component directory `custom_components/gotify_mu`, and action `gotify_mu.send` so existing installations and automations continue to work.
- Preserved existing config-entry versions, entity unique IDs, token storage, API routes, WebSocket behavior, origin extras, and pairing contracts.
- Internal Python class names that contain `GotifyMU` remain implementation details for this compatibility release and do not change the user-facing Monita identity.
- Gotify protocol terminology remains only where it describes API compatibility or an established wire-format field.

### Branding transition

- The supplied **Monita for Home Assistant** brand sheet is the authoritative design source for the new visual identity.
- Legacy Gotify-MU artwork remains transitional until the approved Monita icon/logo/banner files replace the active compatibility aliases and the branding lock is updated.
- The visual asset replacement is intentionally separated from textual/runtime rebranding so an incomplete or regenerated logo cannot silently become the canonical artwork.


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
