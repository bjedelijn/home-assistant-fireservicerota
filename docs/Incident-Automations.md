# Incident automations

These examples intentionally contain no local station IDs, vehicle lists, addresses or personal device names.

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

## Prevent duplicate custom actions

If your own automation must perform an action only once per incident, keep a small list of processed incident IDs in an `input_text` helper.

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

- [iPhone critical alerts](iPhone-Critical-Alerts.md)
- [Crew staffing and assignments](Crew-Staffing.md)
- [Incident lifecycle and history](Incident-Lifecycle-and-History.md)
