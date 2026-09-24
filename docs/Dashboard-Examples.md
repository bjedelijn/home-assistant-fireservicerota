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


## Communication status

For BrandweerRooster Netherlands, `sensor.mobiele_apparaten` contains privacy-filtered mobile-device diagnostics. `sensor.pager` contains selected pager status.

This read-only example keeps the compact dashboard useful without exposing device credentials:

```yaml
- type: markdown
  title: Communication
  content: |-
    {% set pager_battery = state_attr('sensor.pager', 'battery_level') %}
    {% set pager_seen = state_attr('sensor.pager', 'last_seen_at') %}
    {% set devices = state_attr('sensor.mobiele_apparaten', 'mobile_devices') or [] %}

    **Pager**
    {% if pager_battery is not none %}Battery: {{ pager_battery }}%{% endif %}
    {% if pager_seen %} · Last seen: {{ as_datetime(pager_seen).strftime('%H:%M') }}{% endif %}

    {% for d in devices %}
    **{{ d.brand | default(d.platform | default('Mobile device')) }}**
    Alerts: {{ 'on' if d.alert_notifications_enabled == true else 'off' }}
    {% if d.last_heartbeat_at %} · Last seen: {{ as_datetime(d.last_heartbeat_at).strftime('%H:%M') }}{% endif %}
    {% endfor %}
```

The integration deliberately does not expose mobile push tokens, UUIDs, IMEI, serial identifiers or live-update tokens.

## P2000 incident scale

When optional Netherlands P2000 enrichment is enabled, incident snapshots can contain independent scale axes:

```text
highest_fire_scale
highest_hv_scale
highest_ibgs_scale
highest_grip
escalation_timeline
```

Do not merge these into one generic scale. For example, `medium_hv` is a hulpverlening scale and must not be shown as `medium_fire`. GRIP is independent and can coexist with any incident discipline.

Example:

```yaml
- type: markdown
  title: P2000 scale
  content: |-
    {% set incidents = state_attr('sensor.actieve_incidenten', 'incidents') or [] %}
    {% for i in incidents %}
      {% set p = i.p2000_enrichment or {} %}
      **Incident {{ i.id }}**
      Fire: {{ p.highest_fire_scale | default('none') }}
      · HV: {{ p.highest_hv_scale | default('none') }}
      · IBGS: {{ p.highest_ibgs_scale | default('none') }}
      · GRIP: {{ p.highest_grip | default('none') }}
    {% endfor %}
```

## Response-control safety

Incident snapshots can show the authenticated user's response status. The standard dashboard examples intentionally do **not** include buttons that call incident-response switches.

Those switches perform real acknowledged/rejected writes and are disabled by default for newly created entity-registry entries. If an installation intentionally enables them, add explicit confirmation and access controls appropriate for that dashboard.

## Concurrent incidents

For dashboards, do not assume the latest incident is the only active incident. Use the list from:

```jinja
state_attr('sensor.actieve_incidenten', 'incidents') or []
```

This is also why the popup above separates the latest incident card from the active-incidents overview.
