# FireServiceRota Extended 1.2.0-rc.5

rc.5 is a diagnostic release candidate following the rc.4 grouped-subitem filter regression.

## Why rc.5

rc.4 assumed every AlarmeringDroid main item and subitem exposed a per-record `dienst` field. Live testing showed valid nationwide Brandweer messages were then filtered to zero events, which means that assumption was not valid for the actual provider payload.

## Changes

- The API request remains restricted to `diensten=["2"]` (Brandweer).
- The rc.4 mandatory per-record `dienst == 2` check is removed so nationwide Brandweer events are received again.
- Grouped `subitems` are temporarily expanded as before while the real provider schema is inspected.
- `sensor.p2000_status` -> `providers.online.provider_debug` exposes compact schema diagnostics:
  - main-item count;
  - grouped subitem count;
  - sorted main/subitem key names;
  - only service/discipline-related scalar fields;
  - first capcode-object key names.
- Message text, full capcodes and full raw provider payloads are not copied into the diagnostic structure.
- The rc.3 confirmed/unresolved vehicle resolver remains unchanged as the safety layer for six-digit false positives.

## Next validation

Use live nationwide Brandweer traffic to verify events return, then inspect `provider_debug` to identify the actual discipline/service representation for grouped subitems. A later release candidate can then implement the definitive Brandweer-only subitem filter without guessing field names.

RTL-SDR, dashboards and local automations remain outside the integration.
