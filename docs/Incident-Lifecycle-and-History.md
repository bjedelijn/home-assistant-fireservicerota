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

Extended prefers lifecycle information from the API:

1. An explicit API end time or explicit finished/closed state wins over a normal WebSocket `update` trigger.
2. If Home Assistant observes a live active -> finished transition and the API does not provide an end time, the detection time can be used as an estimated fallback.
3. Extended does not invent a detected end time for an incident that was already finished when Home Assistant starts.
4. If a real API end time later becomes available, it is preferred over an estimate.

## Duration

For active incidents:

```text
created_at -> current time
```

For closed incidents:

```text
created_at -> incident_ended_at
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
