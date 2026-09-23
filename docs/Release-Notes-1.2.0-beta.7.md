# FireServiceRota Extended 1.2.0-beta.7

Beta.7 separates raw BrandweerRooster technical lifecycle from Home Assistant operational lifecycle and makes confirmed P2000 correlation persistent.

## P2000 persistence

- The 60-minute P2000 ring buffer remains the discovery window.
- Confirmed practical-incident matches are retained in `sensor.p2000_matches` and restored after restart.
- Existing per-incident `p2000_enrichment` is reused when groups are rebuilt, so matched messages are not lost when the ring buffer expires.
- Persistent matches remain bounded to 25 practical incident groups.

## Operational lifecycle

- Raw BWR status and `end_time` remain untouched.
- A stale technical id can become `group_closed_pending_api` only after conservative authoritative group closure evidence and a 10-minute grace period.
- Closure evidence is accepted when the earliest group member has a real API end time, or at least two group members have clustered real API end times.
- Pending ids no longer count as operationally active, but are rechecked against BWR every 30 minutes.
- A later real BWR `end_time` promotes the record to normal `closed` / `ended_at_source: api`.

## Manual local control

- `fireservicerota.mark_incident_closed` closes one retained technical id or its practical group locally only.
- `fireservicerota.reopen_incident` undoes a local pending close; genuine API closures are never reopened.
- Manual/group closure remains auditable through `operational_status`, `operational_ended_at_source`, `api_closed` and related fields.

Dashboard controls are intentionally added after backend validation.
