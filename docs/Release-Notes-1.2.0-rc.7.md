# FireServiceRota Extended 1.2.0-rc.7

rc.7 follows the successful rc.6 startup fix and addresses the two remaining lifecycle/storage warnings observed in live Home Assistant logs.

## Shutdown lifecycle

Live rc.6 testing confirmed startup dropped from about 358 seconds to about 58 seconds and the bootstrap timeout disappeared. One warning remained during shutdown because the P2000 background loop was still alive at the final-writes stage.

rc.7 now:
- listens once for Home Assistant's stop event;
- calls `P2000EnrichmentManager.async_stop()` before final-writes shutdown;
- retains the config-entry background-task lifecycle from rc.6;
- keeps explicit unload cleanup idempotent.

## Persistent P2000 match storage

The full `sensor.p2000_matches` attributes exceeded Home Assistant's 16 KiB recorder attribute limit.

rc.7 moves the full bounded persistent-match payload to Home Assistant storage:
- storage key is unique per config entry;
- at most 25 practical-incident match groups are retained;
- matches are restored before the P2000 polling loop starts;
- changes are coalesced to storage and the latest state is explicitly saved on stop.

The sensor remains available but now exposes only compact diagnostics:
- current match count as native state;
- match limit;
- up to 10 lightweight latest-group summaries;
- storage backend marker.

The full P2000 enrichment continues to be applied to incidents/history; it is simply no longer duplicated into large entity state attributes.

## Unchanged

- rc.5 provider-schema diagnostics remain available in `sensor.p2000_status`.
- Nationwide online query remains restricted to `diensten=["2"]`.
- rc.3 confirmed/unresolved vehicle filtering remains active.
- RTL-SDR, dashboards and local automations remain outside the integration.
