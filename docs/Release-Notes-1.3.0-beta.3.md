# FireServiceRota Extended 1.3.0-beta.3

## Changes

- Renamed the user-facing local RTL-SDR source to **P2000 via ether**.
- Options now show:
  - **P2000 online**
  - **P2000 via ether (RTL-SDR, beta)**
  - **P2000 online + ether (beta)**
- Added `source_labels` to `sensor.p2000_status`.
- Added `source_label` to `last_event`, each provider diagnostic and every item in `recent_events`.
- Internal source ids stay unchanged as `online` and `rtl` for backwards compatibility and automation stability.

## Notes

This is a presentation/diagnostics beta on top of beta.2. RTL-SDR MQTT reception, unit candidate handling, the shared 60-minute buffer and online/RTL diagnostics remain unchanged.
