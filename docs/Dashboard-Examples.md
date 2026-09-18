# Dashboard examples

These examples deliberately do not show an incident address, coordinates, map route, local station number or local vehicle list.

The examples below use community cards. Install the required cards separately if they are not already available.

## Compact incident card

This example uses Mushroom and opens a Bubble Card popup.

```yaml
- type: custom:mushroom-template-card
  entity: sensor.incidents
  primary: >-
    {% set n = states('sensor.actieve_incidenten') | int(0) %}
    {% if n > 0 %}
      FireServiceRota · {{ n }} active
    {% else %}
      Latest FireServiceRota incident
    {% endif %}
  secondary: >-
    {% set text = states('sensor.incidents')
       | regex_replace('\\b[0-9]{6}\\b', '')
       | regex_replace('\\s+', ' ') | trim %}
    {% set active = state_attr('sensor.incidents', 'incident_active') %}
    {% if active == true %}
      {% set start = state_attr('sensor.incidents', 'start_time')
         or state_attr('sensor.incidents', 'created_at') %}
      {% if start %}
        {% set mins = [0, ((as_timestamp(now()) - as_timestamp(start)) / 60) | int] | max %}
        ACTIVE · {{ mins }} min · {{ text }}
      {% else %}
        ACTIVE · {{ text }}
      {% endif %}
    {% elif active == false %}
      {{ text }} · closed
    {% else %}
      {{ text }}
    {% endif %}
  icon: mdi:fire-truck
  icon_color: >-
    {% if states('sensor.actieve_incidenten') | int(0) > 0 %}red{% else %}grey{% endif %}
  multiline_secondary: true
  tap_action:
    action: navigate
    navigation_path: '#fireservicerota-incident'
```

## Privacy-neutral incident popup

This popup uses Bubble Card plus Mushroom cards. It shows the latest incident and a summary of active incidents without exposing the address/location.

```yaml
- type: custom:bubble-card
  card_type: pop-up
  hash: '#fireservicerota-incident'
  button_type: name
  name: FireServiceRota · Extended
  icon: mdi:fire-truck
  width_desktop: 900px
  cards:
    - type: custom:mushroom-template-card
      entity: sensor.incidents
      primary: >-
        {% if state_attr('sensor.incidents', 'incident_active') == true %}
          Active incident
        {% else %}
          Latest incident
        {% endif %}
      secondary: >-
        {% set text = states('sensor.incidents')
           | regex_replace('\\b[0-9]{6}\\b', '')
           | regex_replace('\\s+', ' ') | trim %}
        {% set start = state_attr('sensor.incidents', 'start_time')
           or state_attr('sensor.incidents', 'created_at') %}
        {% set ended = state_attr('sensor.incidents', 'incident_ended_at') %}
        {% set seconds = state_attr('sensor.incidents', 'duration_seconds') | int(0) %}
        {{ text }}

        {% if start %}Started: {{ as_datetime(start).strftime('%H:%M') }}{% endif %}
        {% if ended %} · Ended: {{ as_datetime(ended).strftime('%H:%M') }}{% endif %}
        {% if seconds > 0 %} · Duration: {{ (seconds / 60) | int }} min{% endif %}
      icon: mdi:fire-alert
      multiline_secondary: true

    - type: markdown
      title: Active incidents
      content: |-
        {% set incidents = state_attr('sensor.actieve_incidenten', 'incidents') or [] %}
        {% if incidents | count == 0 %}
        No active incidents.
        {% else %}
        {% for i in incidents %}
        **{{ i.prio | default('') }}** {{ (i.body | default('Incident'))
          | regex_replace('\\b[0-9]{6}\\b', '')
          | regex_replace('\\s+', ' ') | trim }}
        Duration: {{ ((i.duration_seconds | int(0)) / 60) | int }} min
        {% set tasks = (i.resolved_tasks or []) | map(attribute='name') | select | unique | list %}
        {% if tasks %}Tasks: {{ tasks | join(', ') }}{% endif %}

        {% endfor %}
        {% endif %}
```

## Staffing card

This example distinguishes "no individual assignment data" from "not assigned":

```yaml
- type: markdown
  title: My assignment
  content: |-
    {% set incidents = state_attr('sensor.actieve_incidenten', 'incidents') or [] %}
    {% if incidents | count == 0 %}
    No active incidents.
    {% else %}
      {% for i in incidents %}
        {% set summary = i.crew_summary or {} %}
        {% set individual = summary.individual_assignments_available | default(false) %}
        {% set a = i.own_assignment or {} %}

        **Incident {{ i.id }}**
        Responding: {{ i.own_responding | default(false) }}
        {% if individual == false %}
        Individual assignment: unavailable via API
        {% elif a.assigned == true %}
        Assigned: yes
        {% if a.skill_codes %}Skills: {{ a.skill_codes | join(', ') }}{% endif %}
        {% if a.task_names %}Tasks: {{ a.task_names | join(', ') }}{% endif %}
        {% else %}
        Assigned: no individual assignment found
        {% endif %}
        Responding total: {{ summary.responding_count | default('unknown') }}

      {% endfor %}
    {% endif %}
```

## Concurrent incidents

For dashboards, do not assume the latest incident is the only active incident. Use the list from:

```jinja
state_attr('sensor.actieve_incidenten', 'incidents') or []
```

This is also why the popup above separates the latest incident card from the active-incidents overview.
