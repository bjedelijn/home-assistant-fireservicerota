# Crew staffing and assignments

FireServiceRota Extended `1.1.0-rc.1` includes dynamic staffing data derived from API incident structures such as `incident_responses`, `incident_skill_assignments` and `warning_statuses`.

The integration does not require local vehicle numbers, fixed station IDs or hardcoded function names.

## Where to find staffing data

The richest staffing information is stored in incident snapshots under:

```jinja
state_attr('sensor.actieve_incidenten', 'incidents')
```

and, for closed incidents:

```jinja
state_attr('sensor.incidenthistorie', 'incidents')
```

## `own_assignment`

Where available, the authenticated user's incident snapshot can contain:

```text
own_responses
own_response
own_responding
own_assignment
```

Typical `own_assignment` fields include:

```text
assigned
skill_codes
task_names
assignments
```

Example template:

```jinja
{% set incidents = state_attr('sensor.actieve_incidenten', 'incidents') or [] %}
{% for i in incidents %}
  {% if i.own_assignment is defined %}
    Assigned: {{ i.own_assignment.assigned | default(false) }}
    Skills: {{ (i.own_assignment.skill_codes or []) | join(', ') }}
    Tasks: {{ (i.own_assignment.task_names or []) | join(', ') }}
  {% endif %}
{% endfor %}
```

## `crew_requirements`

Each requirement can contain:

```text
availability_requirement_id
name
short_code
task_ids
tasks
station_ids
skills
required_positions
filled_positions
sufficient
responding_count
assigned_member_count
reserve_responding_count
```

Example summary:

```jinja
{% set incidents = state_attr('sensor.actieve_incidenten', 'incidents') or [] %}
{% for i in incidents %}
  Incident {{ i.id }}
  {% for r in i.crew_requirements or [] %}
    {% set tasks = (r.tasks or []) | map(attribute='name') | select | list %}
    - {{ tasks | join(', ') if tasks else (r.short_code or r.name or 'Requirement') }}:
      {{ r.filled_positions | int(0) }}/{{ r.required_positions | int(0) }}
      sufficient={{ r.sufficient }}
      reserve={{ r.reserve_responding_count | int(0) }}
  {% endfor %}
{% endfor %}
```

## `crew_summary`

A compact incident-wide summary can contain:

```text
sufficient
responding_count
assigned_member_count
reserve_responding_count
```

## Assignment revision fields

Staffing changes can update:

```text
assignment_revision
assignment_last_changed_at
assignment_final
assignment_finalized_at
```

`assignment_final` means the short staffing observation window has completed for the current revision. A later live WebSocket update can start another observation window and create a newer revision.

## `fireservicerota_assignment_finalized`

After the fast observation window Extended fires:

```text
fireservicerota_assignment_finalized
```

with the incident ID in the event data. This event is intended for automations that need a more settled staffing snapshot than the first few seconds after dispatch.

Example trigger:

```yaml
triggers:
  - trigger: event
    event_type: fireservicerota_assignment_finalized

actions:
  - variables:
      incident_id: "{{ trigger.event.data.incident_id | string }}"
```

See [iPhone critical alerts](iPhone-Critical-Alerts.md) for a complete generic notification example.

## Refresh behavior

For an active new/update incident Extended performs approximately:

```text
10-second REST refreshes for about 100 seconds
```

After that, active incident REST refreshes are throttled to approximately:

```text
120 seconds
```

The fast window is intended to capture later responses and assignments shortly after dispatch.
