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

## End-time rules

Extended prefers the operational timestamps from the BrandweerRooster incident payload:

1. An explicit API `end_time` (or another explicit end timestamp) closes the operational incident.
2. BrandweerRooster can expose `state: finished` while the incident is still operationally active. Extended therefore does **not** use `finished` by itself as an incident end.
3. RC2 no longer invents an estimated end time when `state` changes to `finished`.
4. When `end_time` becomes available, it is stored as the incident end time and the duration is calculated from `start_time` (falling back to `created_at`).

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

Incident state is restored after a Home Assistant restart. Historic restored state should remain useful for dashboards without looking like a new live incident to automations.

For that reason, incident automations should explicitly check:

```jinja
{{ state_attr('sensor.incidents', 'trigger') in ['new', 'update'] }}
```

## Concurrent incidents

Do not assume `sensor.incidents` represents the only active incident. It is the latest incident sensor. For a complete active overview use:

```jinja
{{ state_attr('sensor.actieve_incidenten', 'incidents') or [] }}
```

Dashboard examples are available in [Dashboard examples](Dashboard-Examples.md).
