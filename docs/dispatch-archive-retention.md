# Dispatch archive retention (development branch)

The local **dispatch archive** is separate from the operational 25-incident
cache, from the bounded historical fairness store and from HA Recorder.

## Options

Home Assistant → Settings → Devices & Services → FireServiceRota → Configure:

- **Dispatch archive retention**: `all` (default), `2`, `5` or `10` calendar years.
- **Store incident details**: enabled by default. If disabled, keep only incident
  ID and timestamp in the incident archive; names, station, vehicle, priority and
  speciality metadata are removed from that archive.
- **Store long-term yearly statistics**: enabled by default. Yearly data uses
  a logically separate collection, unaffected by incident-detail retention.
  **Disabling it deletes the archive's persisted yearly collection** when
  options reload; it does not modify HA Recorder.

The retention cutoff is checked on integration load and each future archive
upsert. The values live in Home Assistant's private `.storage`, per config
entry, never in GitHub. Raw BWR responses and crew/personnel entries are never
accepted as archived records. The store only saves a strict metadata allowlist.
Historical incident titles may contain sensitive free text: protect HA backups
and limit access to history dashboards. Treat incident titles as untrusted
display text.

## Current status and remaining work

`fireservicerota.get_dispatch_archive_status` returns the archive record
count, date boundaries and active settings. On a newly updated installation
`stored_incidents: 0` is expected: **historical BWR ingestion is not connected
yet**. The existing `probe_historical_incident_list` is read-only and does
not write any incident archive records.

Next development tasks: build a resilient backfill with pagination checkpoint,
source field mapping, verifiable deduplication, and separated alerted versus
reported versus verified turnout evidence. Do not label a year complete just
because pagination reaches an empty page. Do not publish an annual turnout
count until corresponding evidence and data coverage have been validated.

## Status action

```yaml
action: fireservicerota.get_dispatch_archive_status
data: {}
```

This status response contains no incident ID, title or personal detail.
