# FireServiceRota / BrandweerRooster Extended for Home Assistant

This repository is a fork of the original [`cyberjunky/home-assistant-fireservicerota`](https://github.com/cyberjunky/home-assistant-fireservicerota) integration by Ron Klinkien / Cyberjunky and contributors.

The original integration and its core design remain credited to Ron Klinkien / Cyberjunky. This fork does **not** claim maintainership of the original project. The `extended` branch is an independent extension built on top of that work.

The practical reason for creating the Extended version is multi-station use. The fork author is an active member of two fire stations and found that the original integration did not expose enough information to distinguish station-specific memberships, alert groups/tasks and incident responses. That became the starting point for the Extended branch.

The goal of **Extended** is to keep the existing FireServiceRota / BrandweerRooster Home Assistant functionality compatible, while exposing more of the BrandweerRooster API in a generic way for users who belong to one or more stations.

> **Status:** active development. The `extended` branch contains experimental functionality and may change while the new data model and services are being completed and tested.

## Safety notice

Do not rely on Home Assistant or this integration as your only emergency alerting method. Official pager, app, P2000 and/or other approved alerting channels remain leading.

## Main goals of the Extended version

The Extended version is designed around API discovery rather than hardcoded station IDs, task IDs or user IDs. It should therefore work for different FireServiceRota / BrandweerRooster users and organizations.

Planned and/or currently being implemented functionality includes:

- Real-time incident reception through the existing WebSocket connection.
- Preserve the existing `sensor.incidents`, duty sensor and incident response switch where possible for backwards compatibility.
- Distinguish BrandweerRooster incident `trigger` values such as `new` and `update`.
- Retrieve full incident data from the REST API after a WebSocket incident is received.
- Discover the authenticated user automatically.
- Discover stations/groups from `/groups` automatically.
- Discover the authenticated user's membership per station.
- Support users who belong to multiple stations.
- Resolve incident `task_ids` to readable task / alert-group names.
- Resolve tasks to the correct station/group.
- Expose the user's own incident response per station/membership.
- Show whether the user acknowledged (`acknowledged`) or rejected (`rejected`) an incident per station when the API provides this information.
- Expose additional response metadata such as response time, channel, reported status and arrival-at-station information.
- Discover pagers linked to the authenticated account.
- Expose pager status, battery, last-seen time, firmware and radio/mobile signal information.
- Add support for sending pager messages through the BrandweerRooster pager API.
- Keep optional/detail information mainly as attributes instead of creating a large number of Home Assistant entities.

## Architecture

The integration uses the existing `pyfireservicerota` library for authentication, availability, incidents and pager API access.

The Extended branch currently targets:

```text
pyfireservicerota 0.0.49
```

At startup the integration builds an internal, user-specific data model:

```text
Authenticated user
    |
    +-- stations/groups
    |     +-- memberships for this user
    |     +-- tasks / alert groups
    |
    +-- pagers
    |
    +-- incidents
          +-- task_ids -> readable tasks / stations
          +-- incident_responses -> own response per membership/station
```

No specific station, user, membership or task IDs should be hardcoded in the integration.

## Installation

During development, install the integration from the `extended` branch manually.

1. Copy `custom_components/fireservicerota` to:

   ```text
   <Home Assistant config>/custom_components/fireservicerota
   ```

2. Restart Home Assistant.
3. Go to **Settings -> Devices & services -> Add integration**.
4. Search for **FireServiceRota**.
5. Select BrandweerRooster or FireServiceRota and enter your account details.

If the official/core FireServiceRota integration is already configured, use caution when replacing it with this custom version and keep a backup of your Home Assistant configuration.

## Entities

The exact entity set may still change during development. The design principle is to keep the number of entities small and expose related detail as attributes.

### `sensor.incidents`

The main incident sensor keeps the incident message as its state.

Existing attributes are retained where available, including:

- `id`
- `trigger`
- `created_at`
- `message_to_speech_url`
- `prio`
- `type`
- `responder_mode`
- `can_respond_until`
- incident address/location information

Extended attributes include or are being added for:

- `task_ids`
- `resolved_tasks`
- `resolved_stations`
- `responses_by_station`

Example shape:

```yaml
state: "P 1 Brand woning ..."
attributes:
  id: 1234567
  trigger: update
  prio: prio1
  task_ids:
    - 4270
    - 4272
  resolved_tasks:
    - id: 4270
      name: TS
      station_id: 3853
      station_name: Example Station
      alertable: true
    - id: 4272
      name: POST
      station_id: 3853
      station_name: Example Station
      alertable: true
  resolved_stations:
    - id: 3853
      name: Example Station
  responses_by_station:
    - station_id: 3853
      station_name: Example Station
      membership_id: 12345
      status: acknowledged
      response: opkomen
      responded_at: "2026-09-09T12:15:06+02:00"
      channel: pager
      arrived_at_station: false
```

The API's original response status is kept alongside a friendlier response value where possible.

Typical status mapping:

```text
acknowledged -> opkomen
rejected     -> afwijzen
no response  -> geen reactie
```

## Stations, memberships and alert groups

The Extended version reads `/groups` and automatically finds station groups where the authenticated user has an active membership.

This is important for users who are members of more than one fire station. The same BrandweerRooster `user_id` can have a different `membership_id` for every station. Incident responses are therefore matched primarily through `membership_id` instead of relying only on `user_id`.

Tasks / alert groups are also read from the group data. This allows an incident's `task_ids` to be resolved into readable names without hardcoding local task IDs.

This data is intended to be available for Home Assistant templates and automations even when the user does not actively use it.

## Pager sensor

The Extended branch adds a pager sensor for pagers linked to the authenticated BrandweerRooster account.

For a single pager the sensor can expose attributes such as:

- pager ID
- pager type
- serial number
- firmware version
- battery level
- pager state
- last seen
- mobile signal strength
- mobile signal status
- paging/P2000 signal strength
- paging/P2000 signal status
- mobile operator

If an account has multiple pagers, the intention is to keep them grouped under one sensor instead of automatically creating a large number of entities.

## Pager messages

`pyfireservicerota` 0.0.49 supports the BrandweerRooster pager API, including:

- listing pagers
- sending a message to a pager
- retrieving pager-message acknowledgment status

The Extended integration adds a Home Assistant service so messages can be sent without defining a separate `rest_command`.

Example:

```yaml
action: fireservicerota.send_pager_message
data:
  message: "Test message from Home Assistant"
  confirmation: true
```

For accounts with multiple pagers a `pager_id` can be supplied explicitly.

> Pager-message service syntax may still change until this functionality has completed testing.

## Incident responses

The original integration exposes one generic incident response switch. The Extended version keeps backwards compatibility where practical, while also making the user's per-station response visible in `sensor.incidents`.

Relevant API response data can include:

- `membership_id`
- `group_id`
- `status`
- `responded_at`
- `channel`
- `reported_status`
- `estimated_time_of_arrival`
- `arrived_at_station`
- `available_at_incident_creation`
- `alerted_at`

This makes it possible to see which station the user responded for and whether the user chose to turn out or reject the call.

## Example automations

### React only to a new incident

A changing text-to-speech URL should not be used as the only indication of a new incident. BrandweerRooster supplies a `trigger` attribute that can be `new` or `update`.

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

### Check whether a task / alert group was included

```yaml
condition:
  - condition: template
    value_template: >
      {{ 4270 in (state_attr('sensor.incidents', 'task_ids') or []) }}
```

Using the resolved task attributes is preferable when building reusable dashboards; numeric IDs are organization-specific.

## Development principles

The Extended branch follows these principles:

1. **Universal discovery** - no hardcoded user, station, membership or task IDs.
2. **Backwards compatibility** - existing FireServiceRota entities should keep working where practical.
3. **Small entity footprint** - related detail belongs in attributes unless a separate entity adds clear Home Assistant value.
4. **Preserve raw API values** - translated/friendly values should complement rather than replace API data.
5. **Multi-station support** - membership identity is taken into account when resolving responses.
6. **Optional functionality** - users do not have to use pager, task or response extensions simply because the data is available.
7. **Safety first** - Home Assistant remains an additional automation/information layer, not the primary emergency alerting path.

## Debugging

Enable debug logging with:

```yaml
logger:
  default: info
  logs:
    custom_components.fireservicerota: debug
    pyfireservicerota: debug
```

Useful debug information includes WebSocket incidents, discovered stations/memberships/tasks, pager API information, availability and incident response data.

## Upstream and credits

The original FireServiceRota Home Assistant integration and `pyfireservicerota` were created and maintained upstream by Ron Klinkien / Cyberjunky and contributors. All original-project credit remains with them.

This repository is a fork. The fork owner is responsible only for the Extended changes in this repository/branch and is **not** presented as maintainer of the original project.

Original repositories:

- https://github.com/cyberjunky/home-assistant-fireservicerota
- https://github.com/cyberjunky/python-fireservicerota

The Extended branch explores broader BrandweerRooster API support, especially multi-station memberships, task/alert-group resolution, pager information and richer incident responses, while retaining the useful real-time incident and availability foundation of the original integration.
