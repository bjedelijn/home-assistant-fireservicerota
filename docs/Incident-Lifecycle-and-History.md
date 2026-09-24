# Incident lifecycle and history

Extended stores incidents by BrandweerRooster/FireServiceRota incident ID. This prevents repeated updates from becoming separate incidents and allows more than one incident to be active simultaneously.

## Active incidents

`sensor.actieve_incidenten` has:

- state = number of active incidents;
- `latest_incident_id`;
- `incidents` = active incident snapshots;
- `refresh_seconds` = normal active REST refresh interval.

Example template:

```jinja
{% set active = state_attr('sensor.actieve_incidenten', 'incidents') or [] %}
Active incidents: {{ active | count }}
{% for i in active %}
- {{ i.id }} | {{ i.prio }} | {{ i.duration_seconds | int(0) }} seconds
{% endfor %}
```

## History

`sensor.incidenthistorie` contains unique closed snapshots. Extended currently retains up to 25 closed incidents in restored/in-memory history.

Useful lifecycle fields include:

```text
incident_active
incident_status
incident_ended_at
duration_seconds
lifecycle_known
lifecycle_fields
ended_at_source
ended_at_estimated
```

Not every field is present on every API payload.

Closed snapshots can also retain staffing fields such as `crew_summary`, `crew_requirements`, `crew_assignments` and own response/assignment data when the API exposes them.

## End-time rules

Extended prefers the operational timestamps from the BrandweerRooster incident payload:

1. An explicit API `end_time` (or another explicit end timestamp) closes the operational incident.
2. BrandweerRooster can expose `state: finished` while the incident is still operationally active. Extended therefore does **not** use `finished` by itself as an incident end.
3. Extended does not invent an estimated end time when `state` changes to `finished`.
4. When `end_time` becomes available, it is stored as the incident end time and the duration is calculated from `start_time` (falling back to `created_at`).
5. On the active -> closed transition, Extended performs one final REST read to capture the latest available staffing/response data into history. This is a single closure check, not a continuing history refresh.

## Duration

For active incidents:

```text
start_time (or created_at) -> current time
```

For closed incidents:

```text
start_time (or created_at) -> incident_ended_at / API end_time
```

The result is exposed as `duration_seconds`.

## Restart behavior

Incident state is restored after a Home Assistant restart. Historic restored state should remain useful for dashboards without looking like a new live incident to automations. Normalized staffing and own-response fields that were already stored in a compact incident snapshot are preserved during this restore instead of being discarded.

For that reason, incident automations should explicitly check:

```jinja
{{ state_attr('sensor.incidents', 'trigger') in ['new', 'update'] }}
```

## Historical staffing backfill

History that already contains normalized staffing data is restored locally and does not need a backfill after restart. Older history from versions that did not yet store staffing fields is not automatically re-fetched on every Home Assistant restart. This avoids unnecessary API traffic.

A retained closed incident can be checked manually:

```yaml
action: fireservicerota.backfill_history_staffing
data:
  incident_id: "1234567"
response_variable: backfill_result
```

To check recent retained history for missing staffing fields, omit `incident_id` and optionally set `limit` from 1 to 25:

```yaml
action: fireservicerota.backfill_history_staffing
data:
  limit: 25
response_variable: backfill_result
```

The service only requests closed records that are missing normalized staffing data. It returns summary counts including `matched`, `checked`, `updated`, `unavailable`, `failed` and `skipped`.

Backfill is best-effort: if BrandweerRooster no longer exposes the underlying historic responses, warning statuses or assignments, Extended leaves that snapshot unchanged rather than manufacturing empty staffing data.

## Concurrent incidents

Do not assume `sensor.incidents` represents the only active incident. It is the latest incident sensor. For a complete active overview use:

```jinja
{{ state_attr('sensor.actieve_incidenten', 'incidents') or [] }}
```

Dashboard examples are available in [Dashboard examples](Dashboard-Examples.md).
