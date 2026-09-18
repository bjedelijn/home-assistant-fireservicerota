# Crew staffing and assignments

FireServiceRota Extended `1.1.0-rc.2` includes dynamic staffing data derived from API incident structures such as `incident_responses`, `incident_skill_assignments` and `warning_statuses`.

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

## Own response and assignment

An incident snapshot can contain:

```text
own_responses
own_response
own_responding
own_assignment
```

`own_response` prefers a responding own response when one exists. `own_responding` indicates whether any own response currently counts as responding.

Typical `own_assignment` fields include:

```text
assigned
skill_codes
task_names
assignments
```

Important: `own_assignment.assigned == false` is not enough to conclude that a user is reserve. Check `crew_summary.individual_assignments_available` first.

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
individual_assignments_available
```

In RC2:

- `required_positions` = `None`
- `filled_positions` = `None`

They remain in the schema only for compatibility and must not be used to calculate personnel counts.

Each skill entry can contain:

```text
short_code
required
assigned
filled
sufficient
coverage_source
api_assigned_count
available_count
```

RC2 treats skill requirements as **overlapping qualification requirements**, not as separate seats. For example, a requirement can need six members with a general crew skill while one of those six also covers commander and another covers driver. Therefore skill requirements such as 6 + 1 + 1 must not be summed into eight personnel positions.

The API `warning_statuses` coverage is used for sufficient/insufficient status when available. `incident_skill_assignments` remains useful for individual person-to-function details, but some organizations/incidents return no individual assignments.

Example summary:

```jinja
{% set incidents = state_attr('sensor.actieve_incidenten', 'incidents') or [] %}
{% for i in incidents %}
  Incident {{ i.id }}
  {% for r in i.crew_requirements or [] %}
    {% set tasks = (r.tasks or []) | map(attribute='name') | select | list %}
    - {{ tasks | join(', ') if tasks else (r.short_code or r.name or 'Requirement') }}:
      sufficient={{ r.sufficient }}
      responding={{ r.responding_count }}
      {% for skill in r.skills or [] %}
      {{ skill.short_code }} {{ skill.assigned }}/{{ skill.required }}
      {% endfor %}
  {% endfor %}
{% endfor %}
```

When individual assignments are unavailable, `assigned_member_count` and `reserve_responding_count` are left unknown instead of incorrectly treating every responding member as reserve.

## `crew_summary`

A compact incident-wide summary can contain:

```text
sufficient
responding_count
assigned_member_count
reserve_responding_count
individual_assignments_available
staffing_source
```

Interpretation:

- `responding_count` can still be known without individual assignments.
- `individual_assignments_available == false` means exact person-to-function assignment data is not available.
- `assigned_member_count` and `reserve_responding_count` are then `None`.
- `staffing_source` indicates whether coverage primarily came from `warning_statuses` or individual assignments.

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

See [iPhone critical alerts](iPhone-Critical-Alerts.md) or the [complete automation package](examples/Complete-Automation-Package.yaml) for complete generic notification examples.

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
