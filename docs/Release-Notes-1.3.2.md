# FireServiceRota Extended 1.3.2

FireServiceRota Extended 1.3.2 is a focused lifecycle/restore bug-fix release on top of 1.3.1.

## Fixed

### Prevent stale historic incidents from reappearing as active after reload

A persisted incident could remain in Home Assistant's restored active state when BrandweerRooster had never supplied a reliable operational `end_time`. Some older API records can continue to expose a response-phase state such as `alerting` long after the practical incident has ended.

Previously, the integration trusted persisted active state during RestoreEntity reconstruction. After a Home Assistant or integration reload, the follow-up REST enrichment could therefore keep a very old incident active even though no new live WebSocket event had been received.

1.3.2 changes this behavior:

- Explicit API lifecycle evidence still wins.
- A recent unverified active snapshot may survive a short reload, preserving normal active incidents.
- An old unverified restored snapshot is archived locally instead of being reactivated.
- No artificial incident end timestamp is invented for such a stale record.
- Genuine live WebSocket `new` / `update` events continue to activate incidents normally.
- Regression tests cover old unverified, recent unverified, explicit-open and explicit-ended restore scenarios.

The stale-active guard currently treats an unverified persisted active snapshot older than 24 hours as stale. Explicit open lifecycle state remains authoritative even when the incident is older.

## Validation

The release is checked through the repository's normal validation layers:

- Python / JSON / YAML validation
- Home Assistant import smoke test
- Regression tests
- Security checks
- CodeQL
- HACS validation
- Home Assistant Hassfest

## Compatibility and safety

- Requires `pyfireservicerota>=0.0.49`.
- No migration is required from 1.3.1.
- Existing config entries, entities, station availability controls and services remain compatible.
- Home Assistant remains an additional information/automation layer and must not be used as the only emergency alerting mechanism.

## Upgrade

Install **1.3.2** through HACS and restart Home Assistant when prompted.
