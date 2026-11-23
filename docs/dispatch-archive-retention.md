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

## Historical BWR import (initial safe phase)

The opt-in action below traverses a maximum of 25 BWR listing pages per call,
25 incidents per page, and stops at the first empty page. The previously
verified history covered 392 incident-list records through 2019, but actual
API coverage and year completeness still cannot be guaranteed. The persisted
page checkpoint and archive records are stored together so a Home Assistant
restart can resume the next page without recounting. Calling the action again
after a successful complete run is a no-op.

```yaml
action: fireservicerota.import_dispatch_history
data:
  station_id: YOUR_AUTHORIZED_STATION_ID
  max_pages: 25
```

The importer **currently saves only validated incident IDs and timestamps**,
because those are the only fields confirmed from the list response. It does
not infer post membership, incident titles, priority, vehicle specialism,
individual responders, actual turnout or fairness. This is a first-stage
archive index, **not the complete named incident-detail import**. No yearly
statistics are calculated from these records, and no historical year can yet
be marked complete. Extra details require verified source mapping and separate
privacy safeguards. The retention/options UI applies to metadata records
when such detail ingestion is later implemented.

`fireservicerota.get_dispatch_archive_status` reports the stored count,
checkpoint and import state without disclosing incidents or member identities.

**Safety:** Read-only remote BWR API, private HA storage, no upload to GitHub.
This action should not be used to infer real turnout or personal fairness
from listing records. Audit extraction and role-level fairness aggregation
remain a separate bounded design task.

## Status action

```yaml
action: fireservicerota.get_dispatch_archive_status
data: {}
```

This status response contains no incident ID, title or personal detail.
