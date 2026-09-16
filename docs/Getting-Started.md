# Getting started

## Install the integration

For the current release candidate, install the contents of:

```text
custom_components/fireservicerota
```

into:

```text
<Home Assistant config>/custom_components/fireservicerota
```

Restart Home Assistant and add **FireServiceRota Extended / FireServiceRota** from **Settings -> Devices & services**.

## Verify the main entities

After setup, check the entity registry. Typical Dutch entity IDs are:

```text
sensor.incidents
sensor.actieve_incidenten
sensor.incidenthistorie
```

Depending on your account, additional entities can include:

```text
binary_sensor.dienst_example_station
binary_sensor.niet_storen
switch.incidentreactie_example_station
sensor.pager
```

The exact names can differ by Home Assistant language and entity-registry history.

## What the three incident sensors are for

### `sensor.incidents`

The latest incident/update. This is the fastest and simplest trigger source for automations.

Useful attributes include:

```text
id
trigger
created_at
prio
type
task_ids
new_task_ids
resolved_tasks
resolved_stations
responses_by_station
incident_active
incident_ended_at
duration_seconds
```

### `sensor.actieve_incidenten`

State = number of active incidents.

The `incidents` attribute contains all active incident snapshots. This is the preferred source for dashboards, concurrent incidents, staffing and assignment information.

### `sensor.incidenthistorie`

Contains unique closed incident snapshots. Repeated updates for one incident do not create a new history row for every update.

## Automation safety

A state trigger on `sensor.incidents` can also run during reload/restart related state restoration. Extended removes the historic raw trigger during restore, so automations should still explicitly require a live trigger:

```jinja
{{ state_attr('sensor.incidents', 'trigger') in ['new', 'update'] }}
```

A more defensive automation can use the trigger state directly:

```yaml
condition:
  - condition: template
    value_template: >-
      {{ trigger.to_state is not none
         and trigger.to_state.attributes.get('trigger') in ['new', 'update'] }}
```

## Multi-station installations

Use the station-specific duty and response entities where practical. The legacy generic Duty/Incident Response entities are kept for compatibility, but station-specific membership entities provide the clearest behavior on accounts connected to multiple stations.

## Updating

An optional Git-based updater for Home Assistant OS / Supervised installations is documented in [Updating from Git](Updating.md). It updates the local clone but restarts Home Assistant only when the actual integration directory changed.

## Next steps

- Use [Incident automations](Incident-Automations.md) for notification/TTS examples.
- Use [iPhone critical alerts](iPhone-Critical-Alerts.md) for iOS critical notifications.
- Use [Crew staffing and assignments](Crew-Staffing.md) for `own_assignment` and `crew_requirements`.
- Use [Dashboard examples](Dashboard-Examples.md) for a privacy-neutral incident card and popup.
