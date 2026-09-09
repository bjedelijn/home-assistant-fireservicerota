# FireServiceRota / BrandweerRooster Extended for Home Assistant

This repository is a fork of the original [`cyberjunky/home-assistant-fireservicerota`](https://github.com/cyberjunky/home-assistant-fireservicerota) integration by Ron Klinkien / Cyberjunky and contributors.

The original integration and its core design remain credited to Ron Klinkien / Cyberjunky. This fork does **not** claim maintainership of the original project. The `extended` branch is an independent extension built on top of that work.

The practical reason for creating the Extended version is multi-station use. The fork author is an active member of two fire stations and found that the original integration did not expose enough information to distinguish station-specific memberships, alert groups/tasks and incident responses. That became the starting point for the Extended branch.

The goal of **Extended** is to keep the existing FireServiceRota / BrandweerRooster Home Assistant functionality compatible, while exposing more of the BrandweerRooster API in a generic way for users who belong to one or more stations.

> **Status:** public test release. The `extended` branch is ready for Home Assistant testing, but should still be considered pre-release software until it has been validated with real incidents, pager data and multi-station responses.

## Safety notice

Do not rely on Home Assistant or this integration as your only emergency alerting method. Official pager, app, P2000 and/or other approved alerting channels remain leading.

## Extended functionality

The Extended version is designed around API discovery rather than hardcoded station IDs, task IDs or user IDs. It should therefore work for different FireServiceRota / BrandweerRooster users and organizations.

Extended adds or expands:

- Real-time incidents through the existing WebSocket connection.
- REST enrichment of received incidents.
- `trigger` handling for `new` and `update` incidents.
- Automatic discovery of the authenticated user.
- Automatic station/group discovery through `/groups`.
- Active membership discovery per station.
- Multi-station account support.
- Dynamic task / alert-group resolution from `task_ids`.
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
    |     +-- tasks / alert groups
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

### Task / alert-group resolution

`task_ids` remain the raw API identifiers. Their labels are **not translated or hardcoded** by Extended. They are resolved dynamically from `/groups` and exposed in `resolved_tasks`.

This means local labels such as `TS`, `POST`, `PROEF`, or organization-specific names remain exactly as configured in BrandweerRooster.

Task-change metadata works per incident:

```text
new incident      -> previous_task_ids = []
                     new_task_ids = all current task IDs

incident update   -> previous_task_ids = previous set
                     new_task_ids = only newly added task IDs
```

This is useful for automations that must react only when a new alert group is added to an existing incident.

## Multi-station memberships and incident responses

The same BrandweerRooster `user_id` can have a separate `membership_id` for every station. Extended therefore resolves responses by membership instead of only by user ID.

For a multi-station account:

- the original generic Incident Response switch remains for backwards compatibility;
- the generic switch is not writable when more than one active station membership exists;
- one additional response switch is created per active membership;
- each membership switch has a stable unique ID based on `membership_id`;
- the visible station name is discovered dynamically from `/groups`.

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

Fixed Home Assistant UI labels such as Duty, Incidents, Pager and Incident Response use Home Assistant translation keys. English and Dutch are maintained in the Extended branch. Existing translations from the original project remain credited to their original contributors; missing new Extended strings in other languages may fall back to English until contributed by a speaker of that language.

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

### React only to newly added tasks

```yaml
condition:
  - condition: template
    value_template: >
      {{ (state_attr('sensor.incidents', 'new_task_ids') or []) | count > 0 }}
```

## Development principles

1. **Universal discovery** - no hardcoded user, station, membership or task IDs.
2. **Backwards compatibility** - existing FireServiceRota entities should keep working where practical.
3. **Small entity footprint** - related detail belongs in attributes unless a separate entity adds clear Home Assistant value.
4. **Preserve raw API values** - translations belong in the presentation layer, not in API data.
5. **Multi-station support** - membership identity is used to resolve and submit responses.
6. **Optional functionality** - users can ignore pager/task/response extensions they do not need.
7. **Safety first** - Home Assistant is an additional information/automation layer, not the primary emergency alerting path.

## Debugging

Enable debug logging with:

```yaml
logger:
  default: info
  logs:
    custom_components.fireservicerota: debug
    pyfireservicerota: debug
```

Useful debug information includes WebSocket incidents, discovered stations/memberships/tasks, pager information, availability and incident response data.

## Upstream and credits

The original FireServiceRota Home Assistant integration and `pyfireservicerota` were created and maintained upstream by Ron Klinkien / Cyberjunky and contributors. All original-project credit remains with them.

This repository is a fork. The fork owner maintains only the Extended changes in this repository/branch and is **not** presented as maintainer of the original project.

Original repositories:

- https://github.com/cyberjunky/home-assistant-fireservicerota
- https://github.com/cyberjunky/python-fireservicerota

Extended builds on that foundation with broader BrandweerRooster API support, particularly multi-station memberships, task/alert-group resolution, pager integration and richer incident responses.
