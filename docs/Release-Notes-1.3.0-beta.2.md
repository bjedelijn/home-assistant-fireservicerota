# FireServiceRota Extended 1.3.0-beta.2

## Changes

- Fixed the RTL-SDR unit-candidate regular expression. Six-digit callsigns in the P2000 message body, for example `026832`, are now passed into the existing shared vehicle-confirmation pipeline.
- Fixed the RTL capcode split expression.
- Added `providers.rtl.provider_debug.last_event` to the P2000 status diagnostics.
- Added `recent_events` to `sensor.p2000_status`. It contains the newest 20 events from the shared 60-minute P2000 buffer and includes both `online` and `rtl` source events.
- This makes it possible to verify whether the same practical P2000 alert was received through RTL-SDR and the online provider even when no BrandweerRooster incident has matched yet.

## Notes

- `units` inside an individual raw P2000 event still represents six-digit candidates at provider level. Confirmed vehicles are determined later by the shared enrichment pipeline and exposed as confirmed `units`, with `unit_candidates_raw` and `unresolved_unit_candidates` retained for diagnostics.
- RTL-SDR MQTT reception is immediate, while insertion into the shared correlation buffer still occurs on the normal manager cycle (default 30 seconds).
- Stable `extended` remains `1.2.0`.
