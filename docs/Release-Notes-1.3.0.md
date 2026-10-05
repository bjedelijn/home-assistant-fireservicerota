# FireServiceRota Extended 1.3.0

FireServiceRota Extended 1.3.0 promotes the field-tested 1.3.0 beta / release-candidate line to stable.

This release builds on 1.2.0 with station availability control, richer multi-membership incident context, optional local P2000 via ether support, practical-event timing diagnostics, and reusable Home Assistant Assist / CarPlay examples.

## Highlights

### Station availability / paraat

- Adds `fireservicerota.set_station_availability`.
- Availability is written per dynamically discovered station membership.
- Supports:
  - `next_schedule_change`
  - `1h`
  - `2h`
  - `4h`
  - `8h`
  - custom periods
- `next_schedule_change` ends at the end of the current effective roster interval for that membership.
- The integration performs a real membership-duty read-back after a successful write.
- Action responses include:
  - `previous_available`
  - `actual_available`
  - `confirmed`
  - `status_changed`
  - `start_time`
  - `end_time`
- This makes dashboard, Assist, Siri and CarPlay feedback depend on refreshed BrandweerRooster state rather than only on the POST result.

### Multi-station / membership model

- Keeps station and group discovery generic; no user, station, membership or task IDs are hard-coded.
- Exposes `own_stations`, `own_affiliations` and incident-specific affiliations.
- Keeps per-membership duty and incident-response handling separate for multi-station users.
- Per-membership response switches can write acknowledged/rejected responses and remain disabled by default when newly created.

### Staffing and incident context

- Keeps normalized crew requirements, individual assignments and own-response data available for active and retained incidents.
- `crew_summary.responding_count` can be used for compact spoken/dashboard summaries.
- Individual assignment handling continues to distinguish “assignment data unavailable” from “not assigned”.
- Active and historical incident snapshots remain restart-safe.

### P2000 enrichment

- Keeps the online Netherlands P2000 provider from 1.2.0.
- Adds optional local **P2000 via ether (RTL-SDR/MQTT)** support in the 1.3.0 line.
- Online and ether observations can be grouped into one practical event while preserving per-source evidence.
- `sensor.p2000_status` exposes practical-event and source-arrival diagnostics.
- Adds arrival deltas between ether, online and BrandweerRooster observations when available.
- Tightens correlation when provider coordinates are missing:
  exact unit/callsign, postcode, city, street and location-reference evidence take precedence over generic incident wording.
- Previously attached P2000 messages can be revalidated so stale false-positive enrichment is cleaned up.

### Home Assistant Assist / CarPlay

- Adds documentation for a central verified availability flow shared by dashboard, Assist, Siri and CarPlay.
- Adds reusable CarPlay Quick Access **Assist prompt** examples.
- Adds spoken active-incident and last-historical-incident examples using integration-provided attributes.
- The examples can include priority, incident text, turnout/tasks, `crew_summary.responding_count`, own response and own assignment when available.
- These examples are configuration examples; they are not required for the integration itself.

## Compatibility and safety

- Targets `pyfireservicerota==0.0.49`.
- Existing 1.2.0 functionality remains the compatibility baseline.
- No specific station, user, membership, task, vehicle or local priority mapping is hard-coded.
- Home Assistant remains an additional information/automation layer and must not be used as the only emergency alerting mechanism.

## Upgrade

Users on the `extended` branch can update normally after the stable branch is advanced to this release.

After updating, restart Home Assistant so the integration manifest and entity/service definitions are reloaded.
