# FireServiceRota Extended 1.2.0-beta.10

Beta.10 makes "own stations/groups" fully dynamic from the authenticated FireServiceRota / BrandweerRooster account. No local station names, membership IDs or group IDs are hard-coded.

## Dynamic own affiliations

At discovery time Extended now records every active membership of the authenticated user, regardless of group type.

Incident and overview attributes expose:

```yaml
own_stations:
  - id: 123
    name: Example Station
    short_code: EX

own_affiliations:
  - group_id: 123
    name: Example Station
    type: station
    membership_ids: [456]
    station_ids: [123]
    station_names: [Example Station]
    is_station: true
  - group_id: 789
    name: Regional Specialist Team
    type: team
    membership_ids: [999]
    station_ids: []
    station_names: []
    is_station: false
```

This supports users who belong to one station, several stations, regional specialist groups or a combination of those.

The integration keeps the existing station-specific membership index for duty/availability compatibility. The new affiliation model is additive and does not change existing duty entities.

## Incident involvement

`own_incident_affiliations` contains the user's active affiliations that are relevant to a specific incident. Relevance is derived from incident task IDs and the authenticated user's incident responses, including parent/ancestor group relationships where the API exposes them.

The active-incidents and incident-history sensors also expose the current `own_stations` and `own_affiliations` at sensor level. Dashboards can therefore classify historic P2000 units against the user's current BrandweerRooster memberships without local station-name mappings.

## Manual close reopen cleanup

Reopening a locally closed incident now clears the stale `manual_closed` and `manual_closed_at` state. This keeps subsequent dashboard state consistent with the operational status.

## Scope

No station, specialist group, user, membership, task or vehicle ID is hard-coded. P2000 remains supplemental; BrandweerRooster / FireServiceRota membership and station data is authoritative for the user's own affiliations.
