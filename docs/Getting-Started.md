# Getting started

## Install the integration

For the current release candidate **1.2.0-rc.1**, install the contents of:

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
sensor.pager
sensor.mobiele_apparaten
```

Depending on your account, additional entities can include:

```text
binary_sensor.dienst_example_station
switch.incidentreactie_example_station
```

The exact names can differ by Home Assistant language and entity-registry history.

### Duty / availability

Station-specific duty entities are read-only in 1.2.0-rc.1. Extended reads the current combined schedule for each active station membership, but does not create paraat/niet-paraat planning exceptions.

### Incident response switches

Per-membership incident-response switches support acknowledged/rejected responses. These are real BrandweerRooster/FireServiceRota writes.

For safety, newly created response-switch entity-registry entries are disabled by default. Existing Home Assistant registry choices are not forcibly changed. Enable a response switch only when you intentionally want Home Assistant to be able to send a response, and avoid placing unprotected response buttons on shared dashboards.

### Pager and mobile communication diagnostics

`sensor.pager` exposes selected pager status fields such as battery level and last-seen time when the API supplies them.

For BrandweerRooster Netherlands, `sensor.mobiele_apparaten` exposes privacy-filtered device diagnostics such as platform/model, app version, network type, latest heartbeat and `alert_notifications_enabled`.

Mobile push tokens, UUIDs, IMEI, serial identifiers and live-update tokens are deliberately not exposed.

The legacy user-level `do_not_disturb` entity can still exist for compatibility when the API supplies that field. Do not treat it as the same thing as mobile-device alert notification settings.

## What the three incident sensors are for

### `sensor.incidents`

The latest incident/update. This is the fastest and simplest trigger source for automations.

Useful attributes include:

```text
id
trigger
created_at
start_time
end_time
prio
type
task_ids
new_task_ids
resolved_tasks
resolved_stations
responses_by_station
own_stations
own_affiliations
own_incident_affiliations
incident_active
incident_ended_at
duration_seconds
p2000_enrichment
```

### `sensor.actieve_incidenten`

State = number of active incidents.

The `incidents` attribute contains all active incident snapshots. This is the preferred source for dashboards, concurrent incidents, staffing, assignment information and practical-incident P2000 enrichment.

The sensor also exposes the authenticated user's current `own_stations` and `own_affiliations`.

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

## Multi-station and specialist affiliations

Extended discovers active memberships dynamically. `own_stations` contains station memberships, while `own_affiliations` can also contain team/specialist groups linked to the authenticated account.

Use the station-specific duty entities for station availability. Use incident snapshot attributes such as `own_incident_affiliations` when a dashboard or automation needs to show which of the user's affiliations are relevant to a specific incident.

## Complete package example

For a single, privacy-safe Home Assistant package containing live-incident handling, deduplication, queued TTS, own-response observation and finalized staffing notifications, see:

[`examples/Complete-Automation-Package.yaml`](examples/Complete-Automation-Package.yaml)

The response example observes response data already present on the incident. It does not call the response switches.

It uses placeholder entities only. Replace them with your own entity IDs before use.

## Updating

An optional Git-based updater for Home Assistant OS / Supervised installations is documented in [Updating from Git](Updating.md). The documented script supports selecting a branch such as `1.2.0-rc` while testing a release candidate.

## Next steps

- Use [Incident automations](Incident-Automations.md) for smaller notification/TTS building blocks.
- Use [Complete automation package](examples/Complete-Automation-Package.yaml) for one combined package.
- Use [iPhone critical alerts](iPhone-Critical-Alerts.md) for iOS critical notifications.
- Use [Crew staffing and assignments](Crew-Staffing.md) for current staffing semantics.
- Use [Dashboard examples](Dashboard-Examples.md) for privacy-neutral incident, communication and P2000 examples.
- Read the [1.2.0-rc.1 release notes](Release-Notes-1.2.0-rc.1.md) for the consolidated 1.2.0 changes.
