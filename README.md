# FireServiceRota / BrandweerRooster Extended for Home Assistant

**Current release candidate: `1.1.0-rc.1`**

This repository is a fork of the original [`cyberjunky/home-assistant-fireservicerota`](https://github.com/cyberjunky/home-assistant-fireservicerota) integration by Ron Klinkien / Cyberjunky and contributors.

The original integration and its core design remain credited to Ron Klinkien / Cyberjunky. This fork does **not** claim maintainership of the original project. The `extended` branch is an independent extension built on top of that work.

The goal of **Extended** is to keep the existing FireServiceRota / BrandweerRooster Home Assistant functionality compatible, while exposing more of the BrandweerRooster API in a generic way for users who belong to one or more stations.

> **Status:** release candidate. The main Extended feature set is implemented and the focus for RC1 is real-world validation and bug fixing. Dynamic crew staffing / assignments should still be treated as test functionality until more real incidents and acknowledge/reject cases have been validated.

## Safety notice

Do not rely on Home Assistant or this integration as your only emergency alerting method. Official pager, app, P2000 and/or other approved alerting channels remain leading.

## Documentation / Wiki

Practical examples and privacy-safe configuration guides are available here:

- [GitHub Wiki](https://github.com/bjedelijn/home-assistant-fireservicerota/wiki)
- [Documentation index](docs/README.md)
- [Getting started](docs/Getting-Started.md)
- [Incident automations](docs/Incident-Automations.md)
- [iPhone critical alerts](docs/iPhone-Critical-Alerts.md)
- [Incident lifecycle and history](docs/Incident-Lifecycle-and-History.md)
- [Crew staffing and assignments](docs/Crew-Staffing.md)
- [Dashboard examples](docs/Dashboard-Examples.md)
- [Updating from Git](docs/Updating.md)
- [Privacy and safety](docs/Privacy-and-Safety.md)

The public examples intentionally avoid private addresses, personal device names, local vehicle mappings and other installation-specific data.

## Extended functionality

Extended adds or expands:

- Real-time incidents through the existing WebSocket connection.
- REST enrichment of received incidents.
- `trigger` handling for `new` and `update` incidents.
- Restart/reload protection so restored historic state is not replayed as a fresh incident.
- Multi-incident tracking.
- Unique incident history keyed by incident ID.
- Live duration and closed-incident duration.
- API lifecycle/end-time handling with a detected fallback only for observed live active-to-finished transitions.
- Automatic authenticated-user, station/group and membership discovery.
- Multi-station duty / availability support.
- Global user-level Do Not Disturb state.
- Dynamic task / alert-group resolution.
- Per-membership incident response data and response switches.
- Dynamic incident crew assignments.
- Dynamic crew requirements, filled/required positions and sufficiency.
- Own response / own assignment information where available.
- Short high-frequency REST refresh after a live incident/update for late staffing changes.
- Pager discovery, pager status and pager-message support.
- Task-change tracking through `previous_task_ids` and `new_task_ids`.
- Home Assistant translations for fixed UI labels while preserving raw API values.

No specific station, user, membership, task, vehicle or local priority mapping is hardcoded in the integration.

## Architecture

The integration currently targets:

```text
pyfireservicerota 0.0.49
```

At startup it builds a user-specific model:

```text
Authenticated user
    |
    +-- stations/groups
    |     +-- active memberships
    |     +-- per-membership combined schedules
    |     +-- tasks / alert groups / teams
    |
    +-- global user preferences
    |     +-- do_not_disturb
    |
    +-- pagers
    |
    +-- incidents
          +-- task_ids -> readable tasks / stations
          +-- incident_responses -> response information
          +-- incident_skill_assignments -> live crew assignments
          +-- warning_statuses -> requirements / skills / sufficiency
          +-- lifecycle -> active / finished / duration
```

## Installation

For the current release candidate, install from the `extended` branch manually.

1. Copy `custom_components/fireservicerota` to:

   ```text
   <Home Assistant config>/custom_components/fireservicerota
   ```

2. Restart Home Assistant.
3. Go to **Settings -> Devices & services -> Add integration**.
4. Search for **FireServiceRota Extended** / **FireServiceRota**.
5. Select BrandweerRooster or FireServiceRota and enter your account details.

If the official/core FireServiceRota integration is already configured, keep a backup before replacing it with this custom integration.

An optional Git-based updater for Home Assistant OS / Supervised installations is documented in [Updating from Git](docs/Updating.md).

## Main incident entities

Typical Dutch entity IDs are:

```text
sensor.incidents
sensor.actieve_incidenten
sensor.incidenthistorie
```

The exact entity ID can depend on Home Assistant entity naming and language settings.

### Latest incident sensor

`sensor.incidents` remains the central latest-incident entity. Its state is the latest incident body/message.

Common attributes include:

```text
id
trigger
created_at
prio
type
responder_mode
can_respond_until
task_ids
previous_task_ids
new_task_ids
resolved_tasks
resolved_stations
responses_by_station
incident_active
incident_status
incident_ended_at
duration_seconds
```

For automations, explicitly check for a live trigger:

```jinja
{{ state_attr('sensor.incidents', 'trigger') in ['new', 'update'] }}
```

### Active incidents sensor

`sensor.actieve_incidenten` contains all incidents currently considered active by Extended. Its state is the number of active incidents and its `incidents` attribute contains the active snapshots, newest first.

This is the preferred source for dashboards, concurrent incidents and dynamic crew/staffing information.

### Incident history sensor

`sensor.incidenthistorie` contains unique closed incidents. Repeated updates for the same incident ID do not create duplicate history rows. Extended currently retains up to 25 closed snapshots in restored/in-memory history.

## Incident lifecycle

Extended keeps incident state in a shared store keyed by incident ID.

Lifecycle handling follows these rules:

1. Explicit API end timestamps or explicit finished/closed state take precedence.
2. A normal WebSocket `new` / `update` does not override an explicit closed state.
3. If Home Assistant observes a live active-to-finished transition and the API supplies no end time, the detected time can be used as an estimated fallback.
4. An incident already finished at Home Assistant startup is not given an invented end time.
5. A real API end timestamp remains preferred over a detected estimate.

See [Incident lifecycle and history](docs/Incident-Lifecycle-and-History.md) for details.

## Dynamic crew staffing and assignments

RC1 exposes dynamic staffing information by joining API incident structures such as:

```text
incident_responses
incident_skill_assignments
warning_statuses
```

The richest information is available in active/history incident snapshots through fields such as:

```text
crew_assignments
crew_requirements
crew_summary
own_responses
own_response
own_responding
own_assignment
assignment_revision
assignment_last_changed_at
assignment_final
assignment_finalized_at
```

After the short fast-refresh observation window, Extended fires:

```text
fireservicerota_assignment_finalized
```

with the incident ID in the event data. This can be used for a more settled assignment notification. A privacy-safe iPhone critical-alert example is included in [iPhone critical alerts](docs/iPhone-Critical-Alerts.md).

## Refresh strategy

For a new or updated active incident, Extended performs approximately:

```text
10-second REST refreshes for about 100 seconds
```

After that, active incidents continue to be REST-refreshed with a throttle of approximately:

```text
120 seconds
```

A later live WebSocket update can start a new short observation window.

## Multi-station duty and incident response

BrandweerRooster users can have a separate active `membership_id` for every station. Extended therefore retrieves current availability and incident response state per membership rather than assuming one station represents the entire user.

Typical station-specific Dutch entity names can look like:

```text
binary_sensor.dienst_example_station
switch.incidentreactie_example_station
```

Exact entity IDs depend on the station names returned by the API and Home Assistant's entity registry.

The original generic Duty / Incident Response entities remain for backwards compatibility, but station-specific entities are preferred for multi-station automations.

## Do Not Disturb

Extended exposes one user-level Do Not Disturb binary sensor. A typical Dutch entity name is:

```text
binary_sensor.niet_storen
```

Current API observations indicate that Do Not Disturb belongs to the authenticated user rather than an individual station membership.

## Pager

Extended can expose pager state and can send pager messages through:

```text
fireservicerota.send_pager_message
```

Example:

```yaml
action: fireservicerota.send_pager_message
data:
  message: "Test message from Home Assistant"
  confirmation: true
```

If exactly one pager is linked it can be selected automatically. With multiple pagers, specify `pager_id`.

## Development principles

1. **Universal discovery** - no hardcoded user, station, membership, task or vehicle IDs.
2. **Unlimited membership count by design** - behavior is based on discovered memberships.
3. **Backwards compatibility** - existing entities should keep working where practical.
4. **Multi-incident lifecycle** - updates are merged by incident ID.
5. **Small entity footprint** - related detail belongs in attributes where practical.
6. **Preserve raw API values** - translations stay in the presentation layer.
7. **Multi-station support** - membership identity is used for duty and response handling.
8. **Dynamic staffing** - requirements, skills and assignments are derived from API data.
9. **Optional functionality** - users can ignore extensions they do not need.
10. **Safety first** - Home Assistant is an additional information/automation layer.

## RC1 validation focus

Before promoting RC1 to `1.1.0`, further real-world validation is recommended for:

- acknowledged and rejected incident responses per membership;
- late task/unit updates after the initial incident;
- `incident_skill_assignments` and `warning_statuses` across more real incidents;
- required/filled functions and crew sufficiency against the BrandweerRooster UI;
- responding / assigned / reserve counts;
- the fast assignment refresh window;
- closure/end-time/duration behavior across more incidents;
- two or more simultaneous real incidents end-to-end;
- accounts with more than two active station memberships where available.

## Debugging

Enable debug logging with:

```yaml
logger:
  default: info
  logs:
    custom_components.fireservicerota: debug
    pyfireservicerota: debug
```

Before posting logs or screenshots publicly, review [Privacy and safety](docs/Privacy-and-Safety.md).

## Issues

Bug reports and feedback can be submitted through:

https://github.com/bjedelijn/home-assistant-fireservicerota/issues

Please remove private incident, location and household information before posting.

## Upstream and credits

The original FireServiceRota Home Assistant integration and `pyfireservicerota` were created and maintained upstream by Ron Klinkien / Cyberjunky and contributors. All original-project credit remains with them.

This repository is a fork. The fork owner maintains only the Extended changes in this repository/branch and is **not** presented as maintainer of the original project.

Original repositories:

- https://github.com/cyberjunky/home-assistant-fireservicerota
- https://github.com/cyberjunky/python-fireservicerota

Extended builds on that foundation with broader BrandweerRooster API support, particularly multi-station memberships, per-station duty state, global Do Not Disturb, task/alert-group resolution, pager integration, richer incident responses, multi-incident lifecycle/history and dynamic crew staffing.
