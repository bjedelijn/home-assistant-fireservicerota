# FireServiceRota Extended 1.3.4-beta.1

**Pre-release for controlled Home Assistant testing. Not a stable release.**

## Changes

- Optional `next_scheduled_available_at` in the verified availability response after changing a station to not available. Unlike the temporary exception's `end_time`, this looks for the next actual available interval in the membership's combined schedule.
- Updated Dutch CarPlay/Assist example announces today's/tomorrow's next available time or weekday/date. Missing or incomplete schedule data is announced as unknown, never guessed.
- Local per-station replacement-vehicle assignment via `fireservicerota.set_replacement_vehicle`, `clear_replacement_vehicle`, `get_replacement_vehicles`. Accepts Dutch six-digit callsigns like `04-1034` or `04-1037`, with assignment history stored in Home Assistant.
- P2000 keeps original unit number and canonical vehicle/station evidence. Supplemental `operational_station_name` and `replacement_vehicle` metadata identify the temporarily served station.
- `sensor.p2000_status` shows currently configured `replacement_vehicles`.
- Regression tests for availability lookup and time-scoped unit mappings.

## Testing & limitations

- GitHub automated CI, HACS/Hassfest, CodeQL and security workflows passed for the development branch.
- Requires live validation of BrandweerRooster combined_schedule, CarPlay speech, and actual P2000 enrichment/operational station mapping.
- Replacement mapping annotates incidents already correlated by P2000; it does not itself trigger a new correlation.
- Do not rely on this beta for primary incident alerting or emergency operations.

## Installation and return to stable

This is a **GitHub prerelease**. Home Assistant users must explicitly choose to install prereleases in HACS where supported. Make a Home Assistant backup first. The existing stable release is **v1.3.3** and can be reinstalled if needed.

Do not merge this branch into `extended` before field validation.
