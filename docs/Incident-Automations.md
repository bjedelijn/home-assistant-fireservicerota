# Incident automations

These examples intentionally contain no local station IDs, vehicle lists, addresses or personal device names.

> For one combined, privacy-safe package with live incident handling, deduplication, queued TTS, own-response handling and finalized staffing notifications, use [Complete-Automation-Package.yaml](examples/Complete-Automation-Package.yaml).

## Basic live incident notification

This example reacts only to a live `new` or `update` payload and therefore ignores restored historic state.

```yaml
alias: FireServiceRota - live incident notification
mode: queued
max: 10

triggers:
  - trigger: state
    entity_id: sensor.incidents

actions:
  - variables:
      incident_id: >-
        {{ trigger.to_state.attributes.get('id', '') | string | trim }}
      incident_trigger: >-
        {{ trigger.to_state.attributes.get('trigger', '') | string | trim }}
      incident_text: >-
        {{ trigger.to_state.state | string }}

  - condition: template
    value_template: >-
      {{ incident_trigger in ['new', 'update'] }}

  - condition: template
    value_template: >-
      {{ incident_id not in ['', 'None', 'unknown', 'unavailable'] }}

  - action: notify.mobile_app_your_phone
    data:
      title: "FireServiceRota incident"
      message: >-
        {{ incident_text
           | regex_replace('\\b[0-9]{6}\\b', '')
           | regex_replace('\\s+', ' ')
           | trim }}
      data:
        tag: "fireservicerota-{{ incident_id }}"
```

The notification tag keeps updates for the same incident grouped on supported mobile devices.

## React only when new task IDs are added

Extended stores task changes per incident. This is useful when an incident receives a later alarm group/task update.

```yaml
condition:
  - condition: template
    value_template: >-
      {{ (trigger.to_state.attributes.get('new_task_ids', []) or []) | count > 0 }}
```

Readable task information is available in `resolved_tasks`.

## Use confirmed P2000 units and normalized vehicle types

When Netherlands P2000 enrichment is enabled, automation logic should prefer the
confirmed enrichment fields instead of treating every six-digit token in the
incident text as a vehicle number.

- `p2000_enrichment.units` contains confirmed units only.
- `p2000_enrichment.unit_details` contains per-unit details such as callsign,
  station, `vehicle_type` and normalized `vehicle_type_code`.
- `p2000_enrichment.unit_candidates_raw` and
  `p2000_enrichment.unresolved_unit_candidates` are diagnostic fields and
  should not normally drive actions.

Example:

```yaml
- variables:
    p2000: >-
      {{ trigger.to_state.attributes.get('p2000_enrichment', {}) or {} }}
    confirmed_units: >-
      {{ p2000.get('units', []) or [] }}
    unit_details: >-
      {{ p2000.get('unit_details', []) or [] }}
    vehicle_type_codes: >-
      {% set ns = namespace(types=[]) %}
      {% for d in unit_details %}
        {% set code = d.get('vehicle_type_code') %}
        {% if code and code not in ns.types %}
          {% set ns.types = ns.types + [code] %}
        {% endif %}
      {% endfor %}
      {{ ns.types }}

- condition: template
  value_template: >-
    {{ 'TS' in vehicle_type_codes }}
```

Use `vehicle_type_code` for generic automation logic. Use the more descriptive
`vehicle_type` when you want to show the Brandbase description to a user. A
specific vehicle description can therefore be more detailed than its normalized
automation category. Installations may still keep explicit local overrides for
known specialist appliances, but those overrides belong in the local Home
Assistant configuration rather than in the integration.

## Prevent duplicate custom actions

If your own automation must perform an action only once per incident or update, keep a small list of processed keys in an `input_text` helper.

```yaml
input_text:
  fireservicerota_processed_incidents:
    name: FireServiceRota processed incidents
    max: 255
```

Condition:

```yaml
- condition: template
  value_template: >-
    {% set sent = states('input_text.fireservicerota_processed_incidents')
       .split(',') | map('trim') | reject('equalto', '') | list %}
    {{ incident_id not in sent }}
```

Store the ID after the action:

```yaml
- action: input_text.set_value
  target:
    entity_id: input_text.fireservicerota_processed_incidents
  data:
    value: >-
      {% set current = states('input_text.fireservicerota_processed_incidents')
         .split(',') | map('trim') | reject('equalto', '')
         | reject('equalto', incident_id) | list %}
      {{ (current + [incident_id])[-10:] | join(',') }}
```

## Generic TTS example

```yaml
- action: media_player.volume_set
  target:
    entity_id: media_player.example_speaker
  data:
    volume_level: 0.7

- action: tts.google_translate_say
  data:
    entity_id: media_player.example_speaker
    message: >-
      {{ trigger.to_state.state
         | regex_replace('\\b[0-9]{6}\\b', '')
         | regex_replace('\\s+', ' ')
         | trim }}
    cache: false
```

Replace the TTS action with the TTS integration used by your Home Assistant installation.

For Google Cast / Nest targets it can be useful to explicitly close the Cast session after speech has finished, otherwise indicator LEDs can remain active even though audio playback has stopped:

```yaml
- wait_template: "{{ not is_state('media_player.example_speaker', 'playing') }}"
  timeout: "00:02:00"
  continue_on_timeout: true

- delay:
    seconds: 1

- action: media_player.media_stop
  target:
    entity_id: media_player.example_speaker
  continue_on_error: true
```

Apply this only to targets for which stopping the Cast session is desired; a wall/tablet media player may need different handling.

For multiple incident/reaction speech paths, a queued script is recommended so one message does not interrupt another. A daytime/nighttime split can also use separate volumes and an optional on-duty guard before nighttime speech. The complete package includes these patterns. BrandweerRooster mobile alert-notification settings are intentionally not used as a Home Assistant TTS guard.

## Pause media without turning devices on

Only pause media players that already report an active/on-like state:

```yaml
- variables:
    incident_media_players:
      - media_player.example_tv
      - media_player.example_streamer

- repeat:
    for_each: "{{ incident_media_players }}"
    sequence:
      - if:
          - condition: template
            value_template: >-
              {{ states(repeat.item) in ['playing', 'paused', 'idle', 'on', 'buffering'] }}
        then:
          - action: media_player.media_pause
            target:
              entity_id: "{{ repeat.item }}"
            continue_on_error: true
```

This avoids calling `media_pause` on devices that are off/unavailable.

## More advanced examples

- [Complete automation package](examples/Complete-Automation-Package.yaml)
- [iPhone critical alerts](iPhone-Critical-Alerts.md)
- [Crew staffing and assignments](Crew-Staffing.md)
- [Incident lifecycle and history](Incident-Lifecycle-and-History.md)
