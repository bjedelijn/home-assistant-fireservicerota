# FireServiceRota Extended 1.3.0-rc.2

Release candidate **1.3.0-rc.2** adds per-station BrandweerRooster availability writes on top of the 1.3.0-rc.1 P2000 online/ether release-candidate line.

## Added

- New Home Assistant action: `fireservicerota.set_station_availability`.
- Paraat / niet-paraat writes use the authenticated user's dynamically discovered **station membership**.
- No station, group or membership IDs are hard-coded.
- Fixed quick periods: **1 hour, 2 hours, 4 hours and 8 hours**.
- `next_schedule_change` mode reads the membership `combined_schedule` and automatically determines when the effective roster can take over again.
- Optional custom start/end period.
- BrandweerRooster 15-minute block normalization.
- Membership/station validation prevents writes to unrelated or non-station memberships.
- Default `ignore_schedule_warnings: true` for predictable quick-action behavior.
- Availability is refreshed immediately after a successful write.
- Service response includes the resolved membership, station, requested state and effective start/end time.

## API behavior validated before implementation

The write path is:

```text
POST /memberships/{id}/schedule_exceptions
```

A successful BrandweerRooster test returned HTTP **201 Created** without `availability_code_id`. RC.2 therefore does not send a fabricated availability-code ID.

The payload uses:

```json
{
  "start_time": "...",
  "end_time": "...",
  "available": true,
  "comments": "Home Assistant",
  "ignore_schedule_warnings": true,
  "channel": "desktop"
}
```

## Home Assistant / CarPlay

The integration provides the API and scheduling logic. CarPlay/dashboard presentation remains a Home Assistant configuration choice, so users can build controls appropriate to their own stations without integration-level hard-coding.

See [Station availability / paraat](Station-Availability.md).

## Existing 1.3.0 RC functionality

All 1.3.0-rc.1 functionality remains, including P2000 online + P2000 via ether, practical-event grouping, source-arrival timing diagnostics and the stricter location-aware incident matcher introduced in beta.5.
