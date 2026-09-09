# FireServiceRota / BrandweerRooster Extended for Home Assistant

This repository is a fork of the original [`cyberjunky/home-assistant-fireservicerota`](https://github.com/cyberjunky/home-assistant-fireservicerota) integration by Ron Klinkien / Cyberjunky and contributors.

The original integration and its core design remain credited to Ron Klinkien / Cyberjunky. This fork does **not** claim maintainership of the original project. The `extended` branch is an independent extension built on top of that work.

The practical reason for creating the Extended version is multi-station use. The fork author is an active member of two fire stations and found that the original integration did not expose enough information to distinguish station-specific memberships, alert groups/tasks, duty state and incident responses. That became the starting point for the Extended branch.

The goal of **Extended** is to keep the existing FireServiceRota / BrandweerRooster Home Assistant functionality compatible, while exposing more of the BrandweerRooster API in a generic way for users who belong to one or more stations.

> **Status:** public test release. Multi-station discovery, per-station duty state, global Do Not Disturb, task/station resolution, pager data and restart-safe incident restore behavior have been validated in Home Assistant. Incident responses per membership are implemented and should still be considered test functionality until more real-world acknowledge/reject cases have been validated.

## Safety notice

Do not rely on Home Assistant or this integration as your only emergency alerting method. Official pager, app, P2000 and/or other approved alerting channels remain leading.

## Extended functionality

The Extended version is designed around API discovery rather than hardcoded station IDs, task IDs or user IDs. It should therefore work for different FireServiceRota / BrandweerRooster users and organizations, including accounts with one, two or more active station memberships.

Extended adds or expands:

- Real-time incidents through the existing WebSocket connection.
- REST enrichment of received incidents.
- `trigger` handling for `new` and `update` incidents.
- Restart/reload protection so a restored historic incident is not replayed as a fresh `new` incident.
- Automatic discovery of the authenticated user.
- Automatic station/group discovery through `/groups`.
- Active membership discovery per station.
- Multi-station account support without assuming a fixed number of stations.
- Dynamic task / alert-group resolution from `task_ids`.
- Task resolution across station, team and related groups using API relationships such as `station_ids`, `parent_group_id` and `ancestor_ids`.
- Per-membership duty / availability sensors using each membership's `combined_schedule`.
- One global user-level Do Not Disturb sensor.
- Per-station incident response information using `membership_id`.
- Per-membership response switches for multi-station accounts.
- Pager discovery and pager-status attributes.
- Pager-message sending through a Home Assistant action/service.
- Pager-message acknowledgment-status polling.
- Task-change tracking through `previous_task_ids` and `new_task_ids`.
- A small entity footprint: detail is kept in attributes where practical.
- Home Assistant entity translations for fixed UI labels while API values remain unchanged.

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
          +-- incident_responses -> own response per membership/station
```

No specific station, user, membership or task IDs are hardcoded in the integration.

## Installation

For the current test release, install from the `extended` branch manually.

1. Copy `custom_components/fireservicerota` to:

   ```text
   <Home Assistant config>/custom_components/fireservicerota
   ```

2. Restart Home Assistant.
3. Go to **Settings -> Devices & services -> Add integration**.
4. Search for **FireServiceRota Extended** / **FireServiceRota**.
5. Select BrandweerRooster or FireServiceRota and enter your account details.

If the official/core FireServiceRota integration is already configured, keep a backup before replacing it with this custom integration.

## Main entities

### Incident sensor

The existing incidents sensor remains the central incident entity. Its state is the incident body/message.

Common attributes include:

- `id`
- `trigger`
- `created_at`
- `message_to_speech_url`
- `prio`
- `type`
- `responder_mode`
- `can_respond_until`
- address/location information
- `task_ids`
- `previous_task_ids`
- `new_task_ids`
- `resolved_tasks`
- `resolved_stations`
- `responses_by_station`

Example:

```yaml
state: "P 1 Brand woning ..."
attributes:
  id: 1234567
  trigger: update
  task_ids:
    - 4270
    - 4272
    - 4401
  previous_task_ids:
    - 4270
    - 4272
  new_task_ids:
    - 4401
  resolved_tasks:
    - id: 4270
      name: TS
      alertable: true
      station_id: 3853
      station_name: Example Station
  resolved_stations:
    - id: 3853
      name: Example Station
  responses_by_station:
    - station_id: 3853
      station_name: Example Station
      membership_id: 12345
      status: acknowledged
      responded_at: "2026-09-09T12:15:06+02:00"
      channel: pager
```

### Restart and reload safety

The incident sensor restores its previous state after Home Assistant restarts so the last incident remains visible. Extended deliberately removes the restored raw `trigger` attribute during restore.

This means a historic incident can remain visible in dashboards without being presented to automations as a new live WebSocket incident.

For automations, prefer explicitly checking:

```jinja
{{ state_attr('sensor.incidents', 'trigger') in ['new', 'update'] }}
```

instead of reacting to every generic state change.

### Task / alert-group resolution

`task_ids` remain the raw API identifiers. Their labels are **not translated or hardcoded** by Extended. They are resolved dynamically from `/groups` and exposed in `resolved_tasks`.

Tasks are not assumed to exist directly on station groups. Extended indexes tasks from all returned groups and resolves their active station relationship using API metadata where available:

- task `station_ids`
- station group identity
- group `parent_group_id`
- group `ancestor_ids`

Only dynamically discovered active stations for the authenticated user are used in the final station mapping.

This means local labels such as `TS`, `POST`, `PROEF`, or organization-specific names remain exactly as configured in BrandweerRooster.

Task-change metadata works per incident:

```text
new incident      -> previous_task_ids = []
                     new_task_ids = all current task IDs

incident update   -> previous_task_ids = previous set
                     new_task_ids = only newly added task IDs
```

This is useful for automations that must react only when a new alert group is added to an existing incident.

## Multi-station duty / availability

BrandweerRooster users can have a separate active `membership_id` for every station. Extended therefore retrieves current availability per membership instead of assuming the first membership represents the whole user.

For every active membership, Extended reads:

```text
memberships/{membership_id}/combined_schedule
```

and creates a station-specific duty binary sensor when the account has multiple active memberships.

Typical Dutch entity names are for example:

```text
binary_sensor.dienst_hardenberg
binary_sensor.dienst_gramsbergen
```

The exact entity ID depends on Home Assistant's generated entity naming and the station name returned by the API.

Each station-specific duty sensor exposes attributes such as:

- `membership_id`
- `station_id`
- `station_name`
- `station_short_code`
- current availability data from the membership schedule

These sensors are independent. One station can therefore be `on` while another station is `off`.

### Legacy Duty sensor

The original generic Duty entity remains available for backwards compatibility.

On multi-station accounts, this legacy entity still follows the original wrapper behavior and should **not** be interpreted as "available at any station". New automations should use the station-specific duty entities instead.

## Do Not Disturb

Extended exposes one user-level Do Not Disturb binary sensor.

Typical Dutch entity name:

```text
binary_sensor.niet_storen
```

Current API observations show `do_not_disturb` on the authenticated user object rather than on a station membership. Extended therefore treats Do Not Disturb as a **global user setting**, not as a per-station setting.

The sensor is currently read-only. Write support should only be added once the BrandweerRooster update endpoint for this preference has been confirmed.

## Multi-station memberships and incident responses

The same BrandweerRooster `user_id` can have a separate `membership_id` for every station. Extended therefore resolves responses by membership instead of only by user ID.

Duty state and incident response are intentionally treated as separate concepts. A user can, for example, be off duty for a station and still explicitly choose to acknowledge/respond to a specific incident.

For a multi-station account:

- the original generic Incident Response switch remains for backwards compatibility;
- the generic switch is not writable when more than one active station membership exists;
- one additional response switch is created per active membership;
- each membership switch has a stable unique ID based on `membership_id`;
- the visible station name is discovered dynamically from `/groups`;
- a membership response switch uses that membership's own duty state for availability checks.

When a station-specific switch is used, Extended sends the BrandweerRooster response with the selected membership:

```json
{
  "status": "acknowledged",
  "membership_id": 12345
}
```

or:

```json
{
  "status": "rejected",
  "membership_id": 12345
}
```

Only API-confirmed fields are sent. Other optional response fields are left to BrandweerRooster unless explicitly implemented later.

`responses_by_station` on the incident sensor can be used in dashboards and automations to distinguish, per station, whether the authenticated user acknowledged, rejected or has no response object for that incident.

## Pager sensor

Extended adds a pager sensor for pagers linked to the authenticated account.

For a single pager it can expose attributes such as:

- pager ID
- user ID
- serial number
- firmware version
- pager type
- battery level
- state
- last seen
- signal strength
- signal-strength status
- paging signal strength
- paging signal-strength status
- mobile operator

If an account has multiple pagers, they remain grouped under one sensor instead of automatically creating many entities.

## Pager messages

Extended adds:

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

If exactly one pager is linked, it is selected automatically. With multiple pagers, specify `pager_id`.

Optional API fields supported by the action include:

- `address`
- `addresses`
- `confirmation`
- `webhook_url`

`address` and `addresses` cannot be used at the same time.

The latest locally sent pager message and its acknowledgment status are exposed on the pager sensor where available.

## API values and translations

Backend/API values are preserved exactly as returned by BrandweerRooster. For example:

```text
acknowledged
rejected
dispatched
powered_on
```

Extended does **not** replace these values with Dutch or other translated data values.

Fixed Home Assistant UI labels such as Duty, Do Not Disturb, Incidents, Pager and Incident Response use Home Assistant translation keys. English and Dutch are maintained in the Extended branch. Existing translations from the original project remain credited to their original contributors; missing new Extended strings in other languages may fall back to English until contributed by a speaker of that language.

Dynamic station names, task names and other organization-configured labels always come directly from the API and are not part of the translation files.

## Example automations

### React only to a new incident

```yaml
automation:
  - alias: FireServiceRota - new incident
    triggers:
      - trigger: state
        entity_id: sensor.incidents
    conditions:
      - condition: template
        value_template: >
          {{ state_attr('sensor.incidents', 'trigger') == 'new' }}
    actions:
      - action: light.turn_on
        target:
          entity_id: light.example
```

### React to live new or updated incidents, but not restored state

```yaml
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.incidents', 'trigger') in ['new', 'update'] }}
```

### React only to newly added tasks

```yaml
condition:
  - condition: template
    value_template: >
      {{ (state_attr('sensor.incidents', 'new_task_ids') or []) | count > 0 }}
```

### Check one station's duty state

```yaml
condition:
  - condition: state
    entity_id: binary_sensor.dienst_example_station
    state: "on"
```

Use the actual entity ID created by Home Assistant for your station.

## Development principles

1. **Universal discovery** - no hardcoded user, station, membership or task IDs.
2. **Unlimited membership count by design** - behavior is based on discovered active memberships, not an assumed maximum of two stations.
3. **Backwards compatibility** - existing FireServiceRota entities should keep working where practical.
4. **Small entity footprint** - related detail belongs in attributes unless a separate entity adds clear Home Assistant value.
5. **Preserve raw API values** - translations belong in the presentation layer, not in API data.
6. **Multi-station support** - membership identity is used for duty, response resolution and response submission.
7. **Optional functionality** - users can ignore pager/task/response extensions they do not need.
8. **Safety first** - Home Assistant is an additional information/automation layer, not the primary emergency alerting path.

## Current validation status

The Extended branch has been validated in a live Home Assistant installation for:

- discovery of multiple active station memberships;
- independent duty state per station;
- live changes to one station's duty state without changing another station;
- global Do Not Disturb readout;
- pager power, battery, signal and last-seen data;
- task resolution where incident tasks originate from non-station/team groups;
- mapping resolved tasks back to the correct active station;
- preserving the last incident across restart without replaying it as a fresh `new` incident.

Still recommended before a stable release:

- validate more real `acknowledged` incident responses per membership;
- validate more real `rejected` incident responses per membership;
- validate incident updates where tasks/units are added later;
- validate edge cases with more than two active station memberships if test accounts are available.

## Debugging

Enable debug logging with:

```yaml
logger:
  default: info
  logs:
    custom_components.fireservicerota: debug
    pyfireservicerota: debug
```

Useful debug information includes WebSocket incidents, discovered stations/memberships/tasks, pager information, per-membership availability and incident response data.

## Upstream and credits

The original FireServiceRota Home Assistant integration and `pyfireservicerota` were created and maintained upstream by Ron Klinkien / Cyberjunky and contributors. All original-project credit remains with them.

This repository is a fork. The fork owner maintains only the Extended changes in this repository/branch and is **not** presented as maintainer of the original project.

Original repositories:

- https://github.com/cyberjunky/home-assistant-fireservicerota
- https://github.com/cyberjunky/python-fireservicerota

Extended builds on that foundation with broader BrandweerRooster API support, particularly multi-station memberships, per-station duty state, global Do Not Disturb, task/alert-group resolution, pager integration and richer incident responses.
