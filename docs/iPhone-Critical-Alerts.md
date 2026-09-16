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

after the short high-frequency staffing observation window for an incident. This is a useful moment to notify the authenticated user about their own assignment and the current staffing state.

The event can occur again if a later live incident update starts another staffing observation window, so the example stores processed incident IDs.

```yaml
input_text:
  fireservicerota_assignment_notifications:
    name: FireServiceRota assignment notifications
    max: 255
```

```yaml
alias: FireServiceRota - critical assignment notification
mode: queued
max: 10

triggers:
  - trigger: event
    event_type: fireservicerota_assignment_finalized

conditions:
  - condition: template
    alias: User is responding and assignment snapshot is final
    value_template: >-
      {% set wanted = trigger.event.data.incident_id | string %}
      {% set ns = namespace(ok=false) %}
      {% for i in state_attr('sensor.actieve_incidenten', 'incidents') or [] %}
        {% if (i.id | string) == wanted
              and i.assignment_final == true
              and i.own_responding == true %}
          {% set ns.ok = true %}
        {% endif %}
      {% endfor %}
      {{ ns.ok }}

  - condition: template
    alias: No notification sent for this incident yet
    value_template: >-
      {% set wanted = trigger.event.data.incident_id | string %}
      {% set sent = states('input_text.fireservicerota_assignment_notifications')
         .split(',') | map('trim') | reject('equalto', '') | list %}
      {{ wanted not in sent }}

actions:
  - variables:
      incident_id: "{{ trigger.event.data.incident_id | string }}"

      assignment_text: >-
        {% set wanted = trigger.event.data.incident_id | string %}
        {% set ns = namespace(text='Assignment unknown') %}
        {% for i in state_attr('sensor.actieve_incidenten', 'incidents') or [] %}
          {% if (i.id | string) == wanted %}
            {% set a = i.own_assignment or {} %}
            {% if a.assigned == true %}
              {% set skills = (a.skill_codes or []) | join(', ') %}
              {% set tasks = (a.task_names or []) | join(', ') %}
              {% set detail = [skills, tasks] | reject('equalto', '') | join(' - ') %}
              {% set ns.text = 'Assigned' ~ ((': ' ~ detail) if detail else '') %}
            {% else %}
              {% set ns.text = 'Responding, but not assigned to a function yet' %}
            {% endif %}
          {% endif %}
        {% endfor %}
        {{ ns.text }}

      crew_text: >-
        {% set wanted = trigger.event.data.incident_id | string %}
        {% set ns = namespace(lines=[]) %}
        {% for i in state_attr('sensor.actieve_incidenten', 'incidents') or [] %}
          {% if (i.id | string) == wanted %}
            {% for r in i.crew_requirements or [] %}
              {% set tasks = (r.tasks or []) | map(attribute='name') | select | list %}
              {% set label = (tasks | join(', ')) if tasks else (r.short_code or r.name or 'Incident') %}
              {% if r.sufficient == true %}
                {% set status = 'sufficient' %}
              {% elif r.sufficient == false %}
                {% set status = 'insufficient' %}
              {% else %}
                {% set status = 'unknown' %}
              {% endif %}
              {% set positions = '' %}
              {% if (r.required_positions | int(0)) > 0 %}
                {% set positions = ' - ' ~ (r.filled_positions | int(0)) ~ '/' ~ (r.required_positions | int(0)) %}
              {% endif %}
              {% set ns.lines = ns.lines + [label ~ ': ' ~ status ~ positions] %}
            {% endfor %}
          {% endif %}
        {% endfor %}
        {{ ns.lines | join('\n') if ns.lines else 'Staffing state unavailable' }}

  - action: notify.mobile_app_your_iphone
    data:
      title: "FireServiceRota - assignment"
      message: |-
        {{ assignment_text }}

        {{ crew_text }}
      data:
        tag: "fireservicerota-assignment-{{ incident_id }}"
        push:
          sound:
            name: default
            critical: 1
            volume: 1.0
          interruption-level: critical
    continue_on_error: true

  - action: input_text.set_value
    target:
      entity_id: input_text.fireservicerota_assignment_notifications
    data:
      value: >-
        {% set current = states('input_text.fireservicerota_assignment_notifications')
           .split(',') | map('trim') | reject('equalto', '')
           | reject('equalto', incident_id) | list %}
        {{ (current + [incident_id])[-10:] | join(',') }}
```

This example deliberately does not filter on a local station ID. If a multi-station user wants station-specific behavior, filter dynamically using the station/task information returned in the incident snapshot rather than copying another installation's numeric IDs.
