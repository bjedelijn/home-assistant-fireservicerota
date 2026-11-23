# Opt-in historical turnout recheck (Home Assistant)

The `fireservicerota.refresh_turnout_audit_history` action is available to
authenticated BrandweerRooster integration entries and rechecks already cached
incident evidence for the station to which the authenticated account belongs.

Example HA automation; replace `YOUR_AUTHORIZED_STATION_ID` locally with your
authorized station ID. **Do not commit actual station IDs or real audit output.**

```yaml
alias: FireServiceRota - bounded historical turnout review
triggers:
  - trigger: time
    at: "03:10:00"
actions:
  - action: fireservicerota.refresh_turnout_audit_history
    data:
      station_id: YOUR_AUTHORIZED_STATION_ID
mode: single
```

This is **opt-in**, never automatically created by the integration.
It makes at most **two** incident audit checks per invocation, from existing
local historical fairness cache only. Eligible records between 1 and 14 days
are due at most daily; those between 15 and 45 days are due at most weekly.
A two-record cap **does not guarantee every incident is refreshed daily**
when more than two are due. The action reports anonymous totals and saves
only small timestamp/count summaries to private HA storage. It never sends
updates to BrandweerRooster and does not establish physical vehicle turnout.

Historical cache discovery/import of newly closed incidents, guaranteed
coverage for all incidents, and 90-day retention/automatic pruning
are **not yet implemented**. The current cache has a separate 100-record
bound and may contain older records. Do not assume the schedule alone meets
a time-based retention policy. Investigate the current provider audit API
availability and privacy/storage implications before enabling broad ingestion.

For a single on-demand audit use `fireservicerota.inspect_turnout_audit`.
