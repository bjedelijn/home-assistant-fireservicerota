# Release notes - 1.2.0-beta.11

## Communication diagnostics and safer response controls

1.2.0-beta.11 keeps station availability read-only and adds privacy-safe
communication diagnostics for BrandweerRooster Netherlands.

### Mobile devices

- Adds a read-only **Mobile devices** sensor for BrandweerRooster NL.
- Reads the authenticated user's registered mobile devices from the API.
- Exposes only dashboard-safe fields such as device id, platform/model, OS/app
  version, device enabled state, `alert_notifications_enabled`, network type,
  latest heartbeat and battery level when the API supplies it.
- The integration does **not** expose mobile push tokens, UUIDs, IMEI, serial
  identifiers or live-update tokens.
- The mobile-device request deliberately bypasses the upstream
  `pyfireservicerota._request` debug-response logging path so raw device
  credentials are not written to Home Assistant debug logs.

### Pager data

The existing Pager sensor remains the authoritative read-only pager source and
already exposes `battery_level` and `last_seen_at` when BrandweerRooster
provides them. This is intended to be combined with the Mobile devices sensor
in a dashboard communication popup.

### Incident response safety

- Per-membership **acknowledged / rejected** (opkomen / afwijzen) support remains
  implemented.
- Incident-response switch entities are now disabled by default in the Home
  Assistant entity registry for newly created entities.
- Existing entity-registry enable/disable choices are not forcibly changed.
- No dashboard action is added by this release.

### Availability / duty

- Per-station duty remains read-only.
- This release deliberately does not add a paraat / niet-paraat write action,
  because BrandweerRooster availability can be time-bound and should not be
  modeled as a simple boolean without validating the planning/exception API.

### Legacy do_not_disturb

The optional user-level `do_not_disturb` field remains supported for backward
compatibility when the API actually supplies it. It is **not** treated as the
same thing as the mobile-device `alert_notifications_enabled` setting.
