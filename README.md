# FireServiceRota / BrandweerRooster Extended for Home Assistant

**Current beta: `1.2.0-beta.8`**

**Extended maintainer:** Bernd Edelijn

This repository is a fork of the original [`cyberjunky/home-assistant-fireservicerota`](https://github.com/cyberjunky/home-assistant-fireservicerota) integration by Ron Klinkien / Cyberjunky and contributors.

The original integration and its core design remain credited to Ron Klinkien / Cyberjunky. This fork does **not** claim maintainership of the original project. The `extended` branch is an independent extension built on top of that work and maintained by Bernd Edelijn.

The goal of **Extended** is to keep the existing FireServiceRota / BrandweerRooster Home Assistant functionality compatible, while exposing more of the BrandweerRooster API in a generic way for users who belong to one or more stations.

> **Status:** beta. `1.2.0-beta.8` is based on `1.1.0-rc.4` and develops the opt-in Netherlands-only P2000 enrichment path. Online buffering, location normalization and logical grouping of related BrandweerRooster incident ids are available; RTL-SDR support is intentionally reserved for a later beta so it can be validated against real hardware.

## Safety notice

Do not rely on Home Assistant or this integration as your only emergency alerting method. Official pager, app, P2000 and/or other approved alerting channels remain leading.

## Documentation / Wiki

Practical examples and privacy-safe configuration guides are available here:

- [GitHub Wiki](https://github.com/bjedelijn/home-assistant-fireservicerota/wiki)
- [Documentation index](docs/README.md)
- [Getting started](docs/Getting-Started.md)
- [Incident automations](docs/Incident-Automations.md)
- [Complete automation package](docs/examples/Complete-Automation-Package.yaml)
- [iPhone critical alerts](docs/iPhone-Critical-Alerts.md)
- [Incident lifecycle and history](docs/Incident-Lifecycle-and-History.md)
- [Crew staffing and assignments](docs/Crew-Staffing.md)
- [Dashboard examples](docs/Dashboard-Examples.md)
- [Updating from Git](docs/Updating.md)
- [Privacy and safety](docs/Privacy-and-Safety.md)

The public examples intentionally avoid private addresses, personal device names, local vehicle mappings, station IDs and other installation-specific data.

## Extended functionality

Extended adds or expands:

- Real-time incidents through the existing WebSocket connection.
- REST enrichment of received incidents.
- `trigger` handling for `new` and `update` incidents.
- Restart/reload protection so restored historic state is not replayed as a fresh incident.
- Multi-incident tracking.
- Unique incident history keyed by incident ID.
- Live duration and closed-incident duration.
- Operational end-time handling based on actual API end timestamps.
- Automatic authenticated-user, station/group and membership discovery.
- Multi-station duty / availability support.
- Global user-level Do Not Disturb state.
- Dynamic task / alert-group resolution.
- Per-membership incident response data and response switches.
- Dynamic incident crew assignments where the API exposes them.
- Dynamic crew requirements and skill coverage.
- Own response / own assignment information where available.
- Short high-frequency REST refresh after a live incident/update for late staffing changes.
- One final REST staffing capture after an incident receives a real operational end time.
- Normalized staffing/response history survives Home Assistant restart/RestoreEntity reconstruction.
- Manual, opt-in staffing backfill for retained closed history that genuinely lacks staffing data.
- Pager discovery, pager status and pager-message support.
- Task-change tracking through `previous_task_ids` and `new_task_ids`.
- Home Assistant translations for fixed UI labels while preserving raw API values.

No specific station, user, membership, task, vehicle or local priority mapping is hardcoded in the integration.

## P2000 enrichment (Netherlands, beta)

For BrandweerRooster Netherlands, Extended can optionally enrich active incidents with P2000 data. This feature is disabled by default and has no effect on FireServiceRota UK entries.

In `1.2.0-beta.9`:

- the online P2000 provider talks directly to the AlarmeringDroid feed;
- no separate HA P2000 integration is required for online mode;
- when P2000 enrichment is enabled, the online provider polls continuously rather than waiting for an active BrandweerRooster incident;
- recent unique P2000 messages are retained in an in-memory 60-minute rolling buffer;
- confirmed matches are also retained in RestoreEntity-backed `sensor.p2000_matches`, so the ring buffer is the discovery window rather than the lifetime of a match;
- when a BrandweerRooster incident appears, Extended can therefore match P2000 messages that arrived before BrandweerRooster as well as later escalation messages;
- correlation uses incident time plus coordinates when available, with text/location fallback;
- Dutch postcodes are normalized separately from provider-specific location references such as motorway/hectometer references;
- six-digit appliance/unit numbers are normalized from P2000 text;
- multiple BrandweerRooster API incident ids can be linked into one logical `incident_group` when time and location strongly indicate one practical incident; original API incident ids and lifecycle remain separate;
- BrandweerRooster `radio_channels` and provider talkgroup hints, when available, are treated as supporting correlation evidence rather than being confused with BrandweerRooster station/alert groups;
- matched P2000 messages, units, talkgroup hints and capcodes are stored in `p2000_enrichment`;
- explicit P2000 escalation milestones are normalized into `escalation_timeline`, `highest_fire_scale` and `highest_grip`, without inventing missing lower stages or duplicate same-level events;
- `source_timing` compares the local Home Assistant first-observed time for BrandweerRooster and each matched P2000 provider; provider/source timestamps are retained separately so polling delay is not confused with original message time;
- conservative Netherlands-only `station_hints` and `unit_details` can use capcode descriptions as a fallback for otherwise unknown stations/units; BrandweerRooster-resolved station data remains leading and ambiguous P2000 evidence is never guessed;
- P2000 enrichment survives incident closure/history storage and can be reused when practical groups are rebuilt after restart;
- stale technical BrandweerRooster ids can become `group_closed_pending_api` from conservative group-level closure evidence while raw BWR lifecycle fields stay unchanged;
- pending API closures are rechecked every 30 minutes and automatically become normal API closures when BWR later supplies `end_time`;
- `fireservicerota.mark_incident_closed` and `fireservicerota.reopen_incident` provide explicit local-only operational overrides without writing to BrandweerRooster;
- polling is configurable from 30 to 3600 seconds;
- a P2000 status sensor exposes polling health, ring-buffer size and the latest buffered message for testing;
- RTL-SDR is not enabled yet and will be added after hardware validation.

Configure this under **Settings -> Devices & services -> FireServiceRota Extended -> Configure**.

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
          +-- incident_skill_assignments -> individual assignments when available
          +-- warning_statuses -> requirements / skills / coverage
          +-- lifecycle -> active / end_time / duration
```