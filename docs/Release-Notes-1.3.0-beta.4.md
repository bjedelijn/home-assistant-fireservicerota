# FireServiceRota Extended 1.3.0-beta.4

## Changes

- Groups identical P2000 observations from the online provider and local ether receiver into one practical alert for dashboard use.
- Adds `last_practical_event` and `recent_practical_events` to `sensor.p2000_status`.
- Keeps raw provider observations available separately in `recent_events`.
- Preserves per-source timestamps and ids under `source_events`.
- Adds matched BrandweerRooster first-seen timing where a practical alert correlates with a BWR incident.
- Adds dashboard-friendly arrival differences in seconds:
  - `ether_to_online`
  - `ether_to_bwr`
  - `online_to_bwr`

## Matching and timing notes

- Online and ether records are grouped only when the normalized P2000 message text is identical and their event times are within 90 seconds.
- This grouping is presentation/diagnostic logic; raw source events are not deleted or merged in the internal ring buffer.
- BrandweerRooster timing is included only when the practical alert matches an incident using the existing correlation logic.
- All arrival differences use local Home Assistant observation timestamps, not provider publication timestamps.
