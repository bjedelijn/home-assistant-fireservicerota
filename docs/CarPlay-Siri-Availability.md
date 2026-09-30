# CarPlay / Siri station availability

This page shows a safe pattern for changing station availability from an iPhone / CarPlay flow and only speaking success after Home Assistant has verified the refreshed BrandweerRooster state.

The integration itself does not provide a CarPlay application. Home Assistant handles the write and verification; Apple Shortcuts / Siri can then read the resulting confirmation text aloud.

## Recommended flow

```text
Siri / CarPlay command
        |
        v
Home Assistant script
        |
        v
fireservicerota.set_station_availability
        |
        v
BrandweerRooster schedule exception
        |
        v
membership duty refresh
        |
        v
confirmed / status_changed response
        |
        v
Home Assistant confirmation text
        |
        v
Siri speaks the result
```

This avoids announcing a requested state as successful before BrandweerRooster has been read back.

## Home Assistant package pattern

The example below uses one central script and an `input_text` helper. Public examples deliberately use placeholder station IDs.

```yaml
input_text:
  brandweer_paraat_laatste_resultaat:
    name: Brandweer paraat laatste resultaat
    max: 255

script:
  brandweer_paraat_wijzig:
    alias: Brandweer - Paraatstatus wijzigen en controleren
    mode: queued
    fields:
      station_id:
        required: true
      station_name:
        required: true
      available:
        required: true
      availability_mode:
        required: true
    sequence:
      - action: fireservicerota.set_station_availability
        data:
          station_id: "{{ station_id | int }}"
          available: "{{ available | bool }}"
          mode: "{{ availability_mode }}"
          comments: "Home Assistant · CarPlay/dashboard"
        response_variable: fsr_result

      - variables:
          bevestigd: "{{ fsr_result.confirmed | default(false) | bool }}"
          gewijzigd: "{{ fsr_result.status_changed | default(false) | bool }}"
          actueel: "{{ fsr_result.actual_available | default(none) }}"
          eind_raw: "{{ fsr_result.end_time | default('') }}"
          eind_tekst: >-
            {% if eind_raw %}
              {{ as_datetime(eind_raw).astimezone().strftime('%H:%M') }}
            {% else %}
              onbekende tijd
            {% endif %}
          gewenst_tekst: "{{ 'paraat' if (available | bool) else 'niet paraat' }}"

      - choose:
          - conditions:
              - condition: template
                value_template: "{{ bevestigd and gewijzigd }}"
            sequence:
              - action: input_text.set_value
                target:
                  entity_id: input_text.brandweer_paraat_laatste_resultaat
                data:
                  value: >-
                    {{ station_name }} is nu {{ gewenst_tekst }} tot {{ eind_tekst }}.

          - conditions:
              - condition: template
                value_template: "{{ bevestigd and not gewijzigd }}"
            sequence:
              - action: input_text.set_value
                target:
                  entity_id: input_text.brandweer_paraat_laatste_resultaat
                data:
                  value: >-
                    {{ station_name }} stond al {{ gewenst_tekst }}.
                    De periode is bevestigd tot {{ eind_tekst }}.

        default:
          - action: input_text.set_value
            target:
              entity_id: input_text.brandweer_paraat_laatste_resultaat
            data:
              value: >-
                Wijziging niet bevestigd. Controleer de actuele poststatus.
```

Create small wrapper scripts per post/action. Example:

```yaml
script:
  brandweer_post_a_paraat:
    alias: Brandweer Post A - Paraat
    sequence:
      - action: script.brandweer_paraat_wijzig
        data:
          station_id: 123
          station_name: Post A
          available: true
          availability_mode: next_schedule_change

  brandweer_post_a_niet_paraat_2u:
    alias: Brandweer Post A - Niet paraat 2 uur
    sequence:
      - action: script.brandweer_paraat_wijzig
        data:
          station_id: 123
          station_name: Post A
          available: false
          availability_mode: 2h
```

## Why distinguish "changed" and "already correct"?

A write can be useful even when the boolean status was already the requested state. For example, a user who is already paraat can apply a new temporary period. Therefore the spoken result should distinguish:

```text
Post A is now paraat until 17:00.
```

from:

```text
Post A was already paraat. The period is confirmed until 17:00.
```

If read-back does not match the requested state, use a failure message instead of a success announcement.

## Apple Shortcuts / Siri setup

On the iPhone:

1. Make sure the Home Assistant Companion app is installed, logged in and can reach the Home Assistant instance.
2. Open **Shortcuts** and create a new shortcut, for example **Brandweer Post A paraat**.
3. Add Home Assistant **Run Script** and select the corresponding wrapper script.
4. Add a short wait (about one second is normally enough because the Home Assistant script itself waits for the verified service response).
5. Add Home Assistant **Render template** with:
   `{{ states('input_text.brandweer_paraat_laatste_resultaat') }}`
   and use its output in the next step. Render template requires an administrator account in the Companion app.
6. Add Apple's **Speak Text** action and pass the rendered text to it.
7. Give the shortcut a short, unique Siri phrase.
8. Test the shortcut on the iPhone before using it through CarPlay.

The spoken text is generated by Home Assistant after BrandweerRooster read-back, so Siri only speaks the verified result.

Exact Shortcuts action names can vary between iOS / Home Assistant Companion versions. The functional sequence remains: **run HA script -> read helper state -> Speak Text**.

## Suggested commands

Keep spoken commands short and unambiguous, for example:

```text
Brandweer Post A paraat
Brandweer Post A niet paraat
Brandweer Post A paraat twee uur
Brandweer Post A niet paraat twee uur
```

For driving use, prefer a small set of common commands rather than exposing every possible action.

## Safety

Do not use Home Assistant / Siri / CarPlay as the only availability or emergency-alerting mechanism. Official BrandweerRooster and organization procedures remain leading.


## Home Assistant CarPlay Quick Access

The Home Assistant iOS app can also expose `script` entities directly in CarPlay Quick Access. This is useful for large touch targets such as:

```text
Post A paraat
Post A niet paraat
Post A paraat 1 uur
Post A niet paraat 1 uur
```

Configure this on the iPhone under **Companion App Settings -> CarPlay -> Quick Access**.

Direct script buttons are useful for touch control, while the Siri Shortcut flow above is preferred when spoken read-back is required.

On supported iOS versions, CarPlay can also expose Home Assistant Assist and predefined Assist prompts. When the selected Assist pipeline has TTS configured, the response can be played through the vehicle audio system.
