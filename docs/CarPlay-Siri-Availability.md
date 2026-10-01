# CarPlay / Siri station availability and incident information

This page shows a reusable pattern for controlling station availability from Home Assistant Assist / CarPlay and for requesting short spoken incident information.

The integration itself does not provide a CarPlay application. Home Assistant Companion handles CarPlay Quick Access and Assist. FireServiceRota Extended supplies the verified availability write/read-back data plus active/history incident attributes.

## Recommended architecture

Use one central Home Assistant layer and let every frontend call the same logic:

```text
CarPlay Assist prompt / Home Assistant Assist / Siri Shortcut / dashboard
        |
        v
Home Assistant central script / conversation automation
        |
        +--> fireservicerota.set_station_availability
        |         |
        |         v
        |    BrandweerRooster write + membership-duty read-back
        |
        +--> sensor.actieve_incidenten / sensor.incidenthistorie
        |
        v
one short result text
        |
        +--> CarPlay TTS
        +--> Assist response
        +--> Siri Shortcut
        +--> dashboard helper
```

This keeps the wording and verification behavior identical across touch and voice control.

## Prefer CarPlay Assist prompts for spoken feedback

On supported Home Assistant Companion / iOS versions, CarPlay Quick Access can expose predefined **Assist prompts**. When the selected Assist pipeline has TTS configured, the conversation response can be played through the vehicle audio system.

A useful dedicated CarPlay tab can contain prompts such as:

| CarPlay title | Assist prompt |
| --- | --- |
| Post A paraat | `Brandweer Post A paraat` |
| Post A niet paraat | `Brandweer Post A niet paraat` |
| Active incident | `Brandweer actieve melding` |
| Last incident | `Brandweer laatste melding` |

Configure these in the Home Assistant Companion app under **CarPlay -> Quick Access**. Choose the Assist pipeline that is configured for the desired language and TTS voice.

Direct `script` entities are still useful for simple touch control, but an Assist prompt is preferable when a spoken response is wanted.

## Verified station availability

The central availability script should call `fireservicerota.set_station_availability` with a response variable and only report success after the integration has refreshed the affected membership duty.

Relevant action response fields include:

- `previous_available`
- `actual_available`
- `confirmed`
- `status_changed`
- `start_time`
- `end_time`

A write can be useful even when the boolean state was already correct because the requested temporary period may have changed. Spoken output should therefore distinguish:

```text
Post A is now not available until 10:45.
```

from:

```text
Post A was already not available. The period is confirmed until 10:45.
```

If `confirmed` is false, report the refreshed state instead of announcing success.

## Conversation-trigger example

Home Assistant conversation triggers can turn fixed Assist prompts into deterministic actions:

```yaml
automation:
  - id: fireservicerota_assist_post_a_not_available
    alias: FireServiceRota - Assist Post A not available
    triggers:
      - trigger: conversation
        command:
          - "brandweer post a niet paraat"
    actions:
      - action: script.brandweer_paraat_wijzig
        data:
          station_id: 123
          station_name: Post A
          available: false
          availability_mode: next_schedule_change

      - set_conversation_response: >-
          {{ states('input_text.brandweer_laatste_resultaat') }}
```

The package example linked below shows a reusable version with several periods.

## Active incident prompt

The active-incident example uses `sensor.actieve_incidenten`. A short spoken response can include:

- priority and incident text;
- resolved turnout/tasks when available;
- `crew_summary.responding_count`;
- whether the authenticated user is responding;
- individual assignment when the API exposes it.

Example response:

```text
Prio 1. Building fire Main Street.
Turnout: Tanker.
7 people have indicated they are responding.
You have indicated that you are responding.
You are assigned for firefighter.
```

`crew_summary.responding_count` is the normalized count supplied by the integration. During an active incident it can still change while responders update their status.

Do not present unavailable individual assignment data as "not assigned". Check `crew_summary.individual_assignments_available` first.

## Last historical incident prompt

For testing CarPlay / Assist without waiting for a live incident, use `sensor.incidenthistorie`. Its `incidents` attribute contains retained closed snapshots.

A prompt such as:

```text
Brandweer laatste melding
```

can return a compact response with date/time, priority, body, turnout/tasks, historical `crew_summary.responding_count`, own response and own assignment when retained in the snapshot.

Example:

```text
The last incident was 30-09 at 21:14.
Prio 1. Building fire Main Street.
Turnout: Tanker.
7 people responded.
You indicated that you were responding.
You were assigned for firefighter.
```

This is a convenient end-to-end test of:

```text
CarPlay Quick Access -> Assist prompt -> Home Assistant conversation automation
-> FireServiceRota incident data -> conversation response -> TTS
```

without changing anything in BrandweerRooster.

## Apple Shortcuts / Siri

Apple Shortcuts remains useful when the user wants Siri to start the same flow outside the Home Assistant CarPlay Quick Access UI.

Prefer routing Siri into the same Home Assistant Assist prompt / central script instead of maintaining separate availability logic in Shortcuts. This keeps CarPlay, Siri and dashboard behavior consistent.

A direct Shortcuts pattern using **Perform action -> Render template -> Speak Text** also remains possible for installations that do not use Assist prompts.

## Package example

See:

- [Station availability / CarPlay package](examples/Station-Availability-CarPlay-Package.yaml)

The example deliberately uses placeholder station IDs and generic station names.

## Safety

Do not use Home Assistant, Siri or CarPlay as the only availability, dispatch or emergency-alerting mechanism. Official BrandweerRooster and organization procedures remain leading.
