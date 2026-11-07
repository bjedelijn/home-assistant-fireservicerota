# FireServiceRota Extended 1.3.4-beta.2

**Beta prerelease for controlled Home Assistant testing. Stable v1.3.3 remains unchanged.**

## Changes since beta.1

- Multiple independent replacement vehicle assignments for every linked station.
- Each assignment requires the actual **original vehicle** and the **replacement vehicle** (for example `04-2350` to `04-1050`).
- Home Assistant `fireservicerota.set_replacement_vehicle`: `station_id`, `original_vehicle_number`, `vehicle_number`.
- Home Assistant `fireservicerota.clear_replacement_vehicle`: `station_id`, `original_vehicle_number` (only this original vehicle is cleared).
- Home Assistant `fireservicerota.get_replacement_vehicles` lists every active assignment.
- P2000 original dispatch units remain unchanged. Enrichment includes `original_vehicle_number`, `operational_station_name` and time-scoped local assignment metadata.
- Regression coverage added for simultaneous assignments, targeted clearing, replacement, conflicts and migration.
- All beta.1 roster look-ahead and CarPlay sample improvements remain included.

## Upgrade notes

Beta.1 saved replacement vehicles without their original numbers. These cannot be safely guessed; active legacy assignments are closed on first load, while their past time windows remain available. Configure replacements again with both numbers. If you were on stable v1.3.3 this migration is irrelevant.

## Testing

Live P2000 event formatting and Home Assistant automations are not yet field-tested. The separate user YAML packages and dashboard are **not included in this integration release** and will be updated after beta.2 validation. Do not depend on a beta as the sole emergency alerting mechanism. Back up Home Assistant before installing. Prereleases must be explicitly selected in HACS where supported.
