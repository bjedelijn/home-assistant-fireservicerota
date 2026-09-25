# FireServiceRota Extended 1.2.0-rc.2

This release candidate keeps the 1.2.0 scope focused on the existing Netherlands-only P2000 enrichment and adds an optional local vehicle-identity cache.

## Vehicle registry cache

- No Brandbase vehicle dataset is bundled or redistributed in this repository.
- When online P2000 enrichment is enabled, Extended reads the public Brandbase current-vehicle region index and caches normalized vehicle metadata only in Home Assistant storage.
- The cache refresh interval is seven days. A stale or unavailable source never clears a previously valid local cache.
- Region discovery is dynamic from the Brandbase current region index, so the implementation is not tied to one station or one safety region.
- Exact numeric callsigns such as `04-2330` are normalized to the six-digit P2000 unit form `042330`.
- Unique matches can provide callsign, region, station, vehicle type and a conservative normalized type code.
- Multiple conflicting matches stay ambiguous; Extended does not guess.
- Existing capcode-derived `station_hints` remain available and are preserved as diagnostic evidence when an exact registry match supplies the canonical station.
- Registry status is exposed under `sensor.p2000_status` -> `vehicle_registry`.

## Scope

Dashboards, local automations, Telegram rendering and blueprints are not moved into the integration by this change. RTL-SDR also remains outside 1.2.0 until the receiver path has been validated with real hardware.
