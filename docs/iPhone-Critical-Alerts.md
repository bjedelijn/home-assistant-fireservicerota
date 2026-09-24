# iPhone critical alerts

Home Assistant Companion for iOS supports critical notifications. These can bypass normal notification volume/focus behavior depending on the iPhone configuration and Home Assistant Companion permissions.

> Test critical notifications carefully. Do not use Home Assistant as the only emergency alerting method.

## Simple critical incident notification

```yaml
alias: FireServiceRota - iPhone critical incident
mode: queued
max: 10

triggers:
  - trigger: state
    entity_id: sensor.incidents

conditions:
  - condition: template
    value_template: >-
      {{ trigger.to_state is not none
         and trigger.to_state.attributes.get('trigger') in ['new', 'update'] }}

actions:
  - variables:
      incident_id: >-
        {{ trigger.to_state.attributes.get('id', '') | string | trim }}
      message_clean: >-
        {{ trigger.to_state.state
           | regex_replace('\\b[0-9]{6}\\b', '')
           | regex_replace('\\s+', ' ')
           | trim }}

  - action: notify.mobile_app_your_iphone
    data:
      title: "FireServiceRota"
      message: "{{ message_clean }}"
      data:
        tag: "fireservicerota-{{ incident_id }}"
        push:
          sound:
            name: default
            critical: 1
            volume: 1.0
          interruption-level: critical
```

Replace `notify.mobile_app_your_iphone` with your own Home Assistant mobile-app notifier.

## Critical assignment notification after the fast staffing refresh

Extended fires:

```text
fireservicerota_assignment_finalized
```

after the short high-frequency staffing observation window for an incident. The event can occur again after a later live update, so a notification automation should deduplicate incident IDs.

The complete privacy-safe implementation is available in [Complete-Automation-Package.yaml](examples/Complete-Automation-Package.yaml).

### Assignment semantics in 1.2.0-rc.1

Do not interpret `own_assignment.assigned == false` by itself as "reserve".

First inspect:

```jinja
{% set summary = incident.crew_summary or {} %}
{{ summary.individual_assignments_available | default(false) }}
```

Use these meanings:

- `individual_assignments_available == false`: the API did not provide individual person-to-function assignments. The user's exact assignment is unknown.
- `individual_assignments_available == true` and `own_assignment.assigned == true`: the authenticated user is present in the individual assignment data.
- `individual_assignments_available == true` and `own_assignment.assigned == false`: the authenticated user is not present in the individual assignment data.

A safe assignment message template is:

```jinja
{% set summary = incident.crew_summary or {} %}
{% set individual = summary.individual_assignments_available | default(false) %}
{% set a = incident.own_assignment or {} %}

{% if individual == false %}
  You confirmed responding. Individual assignment is not available via the API.
{% elif a.assigned == true %}
  {% set skills = (a.skill_codes or []) | join(', ') %}
  {% set tasks = (a.task_names or []) | join(', ') %}
  {% set detail = [skills, tasks] | reject('equalto', '') | join(' - ') %}
  Assigned{{ ': ' ~ detail if detail else '' }}.
{% else %}
  You confirmed responding, but are not present in the individual assignment.
{% endif %}
```

### Staffing summary in 1.2.0-rc.1

Do not use `required_positions` / `filled_positions` to calculate total staffing. 1.2.0-rc.1 deliberately keeps those compatibility fields unknown because skill requirements can overlap.

Instead, show `responding_count` plus per-skill coverage:

```jinja
{% for r in incident.crew_requirements or [] %}
  {% set tasks = (r.tasks or []) | map(attribute='name') | select | list %}
  {% set label = tasks | join(', ') if tasks else (r.short_code or r.name or 'Requirement') %}
  {{ label }} - responding {{ r.responding_count }}
  {% for skill in r.skills or [] %}
    · {{ skill.short_code or skill.skill_id }} {{ skill.assigned }}/{{ skill.required }}
  {% endfor %}
{% endfor %}
```

This remains meaningful when individual assignments are unavailable because coverage can come from `warning_statuses`.

## Full example

For deduplication, critical push configuration, finalized staffing checks and privacy-safe incident text, use:

[`examples/Complete-Automation-Package.yaml`](examples/Complete-Automation-Package.yaml)
