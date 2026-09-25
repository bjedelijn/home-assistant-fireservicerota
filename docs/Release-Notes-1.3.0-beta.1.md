# FireServiceRota Extended 1.3.0-beta.1

This first 1.3.0 beta adds a local P2000 RTL-SDR input alongside the existing
online AlarmeringDroid provider.

## RTL-SDR / MQTT provider

- Adds a new normalized P2000 provider with source `rtl`.
- Subscribes directly to the MQTT attributes topic published by the Cyberjunky
  P2000 RTL-SDR add-on; it does not depend on Home Assistant state changes of
  `sensor.p2000_brandweer`.
- Default topic:
  `homeassistant/sensor/p2000_rtlsdr/2005/attributes`.
- The MQTT attributes topic is configurable for installations using another
  sensor id or MQTT base topic.
- FLEX UTC timestamps from the add-on's `raw message` are converted to
  timezone-aware ISO timestamps.
- Home Assistant receipt time is recorded independently in `received_at`.
- Brandweer discipline, priority, capcodes, city/address metadata and raw
  six-digit unit candidates are normalized into the existing `P2000Event`
  model.

## Source selection

The P2000 option now supports:

- `online` - existing AlarmeringDroid provider only.
- `rtl` - local RTL-SDR MQTT provider only.
- `both` - online and RTL-SDR together.

All enabled providers feed the same 60-minute P2000 ring buffer and existing
correlation pipeline. Confirmed incident matches continue to use the existing
persistent match storage.

When both sources match the same practical incident, `p2000_enrichment.sources`
can contain both `online` and `rtl`, while `source_timing.sources` exposes
them separately as `p2000_online` and `p2000_rtl`.

## Diagnostics

`sensor.p2000_status` exposes RTL provider diagnostics including the MQTT topic,
subscription state, pending queue size, number of MQTT messages received and the
last local message time.

## Beta limitation

The MQTT callback timestamps a local alert immediately, but beta.1 drains the
provider queue into the shared ring buffer on the normal P2000 manager cycle.
With the default configuration, incident enrichment may therefore update up to
about 30 seconds after the RTL-SDR MQTT publication. The original local
`received_at` timestamp is retained for source-timing comparisons.

## Compatibility

- Stable `extended` remains 1.2.0.
- Development branch: `1.3.0-beta`.
- Integration version: `1.3.0-beta.1`.
- `pyfireservicerota==0.0.49` remains unchanged.
- The RTL-SDR source requires a working Home Assistant MQTT integration and a
  compatible P2000 RTL-SDR add-on publishing the configured attributes topic.
