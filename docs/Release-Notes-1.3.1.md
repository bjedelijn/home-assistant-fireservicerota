# FireServiceRota Extended 1.3.1

FireServiceRota Extended 1.3.1 is a focused patch release on top of 1.3.0.

## Fixed

### Prevent repeated incident notifications during REST staffing refreshes

Live BrandweerRooster WebSocket payloads can contain transient event metadata such as:

- `trigger: new`
- `trigger: update`
- `new_task_ids`

These fields describe a specific live event and should not remain attached to later REST enrichment cycles.

Previously, the integration preserved that metadata while refreshing staffing, response and lifecycle data. A Home Assistant automation that triggered on `sensor.incidents` and checked `trigger in ['new', 'update']` could therefore run again when the same incident was refreshed.

1.3.1 changes this behavior:

- `trigger` is exposed only for the actual live WebSocket event.
- `new_task_ids` is also treated as transient live-event metadata.
- Follow-up REST staffing and lifecycle refreshes clear those transient fields.
- `previous_task_ids` remains available as incident context.
- Staffing refreshes, response handling, incident grouping and lifecycle tracking remain unchanged.

This keeps genuine new/update events usable for automations while preventing normal background enrichment from looking like another live incident.

## Validation

The release is checked through the repository's normal validation layers:

- CI and Home Assistant import smoke test
- Security checks
- CodeQL
- HACS validation
- Home Assistant Hassfest

## Compatibility and safety

- Requires `pyfireservicerota>=0.0.49`.
- No migration is required from 1.3.0.
- Existing config entries, entities, station availability controls and services remain compatible.
- Home Assistant remains an additional information/automation layer and must not be used as the only emergency alerting mechanism.

## Upgrade

Install **1.3.1** through HACS and restart Home Assistant when prompted.
