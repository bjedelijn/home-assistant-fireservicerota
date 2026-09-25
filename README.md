# FireServiceRota / BrandweerRooster Extended for Home Assistant

**Current stable release: `1.2.0`**

**Current development release on `1.3.0-beta`: `1.3.0-beta.1`**

**Extended maintainer:** Bernd Edelijn

This repository is a fork of the original [`cyberjunky/home-assistant-fireservicerota`](https://github.com/cyberjunky/home-assistant-fireservicerota) integration by Ron Klinkien / Cyberjunky and contributors.

The original integration and its core design remain credited to Ron Klinkien / Cyberjunky. This fork does **not** claim maintainership of the original project. The `extended` branch is an independent extension built on top of that work and maintained by Bernd Edelijn.

The goal of **Extended** is to keep the existing FireServiceRota / BrandweerRooster Home Assistant functionality compatible, while exposing more of the BrandweerRooster API in a generic way for users who belong to one or more stations.

> **Status:** stable release `1.2.0`. This release consolidates the field-tested 1.2.0 beta/RC line: optional Netherlands P2000 enrichment, Brandbase-backed vehicle resolution, strict Brandweer-only AlarmeringDroid filtering, persistent P2000 matches, multi-incident lifecycle handling, staffing/response enrichment and multi-station account discovery. RTL-SDR remains outside 1.2.0.

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
- [1.2.0 release notes](docs/Release-Notes-1.2.0.md)
- [1.2.0-rc.8 release notes](docs/Release-Notes-1.2.0-rc.8.md)
- [1.2.0-rc.7 release notes](docs/Release-Notes-1.2.0-rc.7.md)
- [1.2.0-rc.6 release notes](docs/Release-Notes-1.2.0-rc.6.md)
- [1.2.0-rc.5 release notes](docs/Release-Notes-1.2.0-rc.5.md)
- [1.2.0-rc.4 release notes](docs/Release-Notes-1.2.0-rc.4.md)
- [1.2.0-rc.3 release notes](docs/Release-Notes-1.2.0-rc.3.md)
- [1.2.0-rc.2 release notes](docs/Release-Notes-1.2.0-rc.2.md)
- [1.2.0-rc.1 release notes](docs/Release-Notes-1.2.0-rc.1.md)

The public examples intentionally avoid private addresses, personal device names, local vehicle mappings, station IDs and other installation-specific data.

Questions, bug reports and contributions can be handled through the GitHub repository and issue tracker; no personal contact details are published in this documentation.

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
- Generic `own_stations` and `own_affiliations` discovery from active memberships, including multi-station users and non-station/regional specialist groups.
- Incident-level `own_incident_affiliations` derived from task and response context without hard-coded station or group IDs.
- Multi-station duty / availability support. Duty/availability is read-only in 1.2.0; no paraat/niet-paraat planning write is implemented.
- Legacy user-level `do_not_disturb` state when that optional API field is supplied; mobile alert settings are modeled separately.
- Dynamic task / alert-group resolution.
- Per-membership incident response data and response switches. These controls can write acknowledged/rejected responses and are disabled by default for newly created entity-registry entries.
- Dynamic incident crew assignments where the API exposes them.
- Dynamic crew requirements and skill coverage.
- Own response / own assignment information where available.
- Short high-frequency REST refresh after a live incident/update for late staffing changes.
- One final REST staffing capture after an incident receives a real operational end time.
- Normalized staffing/response history survives Home Assistant restart/RestoreEntity reconstruction.
- Manual, opt-in staffing backfill for retained closed history that genuinely lacks staffing data.
- Pager discovery, pager status and pager-message support.
- Read-only, privacy-filtered BrandweerRooster mobile-device diagnostics including model/app version, network, last heartbeat and `alert_notifications_enabled`; device tokens, UUIDs, IMEI and serial identifiers are not exposed.
- Task-change tracking through `previous_task_ids` and `new_task_ids`.
- Home Assistant translations for fixed UI labels while preserving raw API values.

No specific station, user, membership, task, vehicle or local priority mapping is hardcoded in the integration.

## P2000 enrichment (Netherlands)

For BrandweerRooster Netherlands, Extended can optionally enrich active incidents with P2000 data. This feature is disabled by default and has no effect on FireServiceRota UK entries.

The 1.2.0 release includes:

- the online P2000 provider talks directly to the AlarmeringDroid feed;
- the provider request selects service `2` (Brandweer); live provider diagnostics confirmed both main items and grouped subitems expose `dienstid="2"` and `dienst="Brandweer"`, so rc.8 applies strict per-item Brandweer filtering on `dienstid` with a name fallback only when the numeric id is absent;
- no separate HA P2000 integration is required for online mode;
- when P2000 enrichment is enabled, the online provider polls continuously rather than waiting for an active BrandweerRooster incident;
- recent unique P2000 messages are retained in an in-memory 60-minute rolling buffer;
- confirmed matches are retained in Home Assistant storage, while `sensor.p2000_matches` exposes only a compact recorder-safe summary; the ring buffer is therefore the discovery window rather than the lifetime of a match;
- when a BrandweerRooster incident appears, Extended can therefore match P2000 messages that arrived before BrandweerRooster as well as later escalation messages;
- correlation uses incident time plus coordinates when available, with text/location fallback;
- Dutch postcodes are normalized separately from provider-specific location references such as motorway/hectometer references;
- six-digit appliance/unit numbers are normalized from P2000 text;
- multiple BrandweerRooster API incident ids can be linked into one logical `incident_group` when time and location strongly indicate one practical incident; original API incident ids and lifecycle remain separate;
- BrandweerRooster `radio_channels` and provider talkgroup hints, when available, are treated as supporting correlation evidence rather than being confused with BrandweerRooster station/alert groups;
- matched P2000 messages, units, talkgroup hints and capcodes are stored in `p2000_enrichment`;
- explicit Dutch P2000 incident scales are kept separate for fire (`highest_fire_scale`), rescue/hulpverlening (`highest_hv_scale`) and hazardous-material incidents (`highest_ibgs_scale`), while GRIP remains independent in `highest_grip`; `escalation_timeline` records only explicitly observed upward milestones per discipline and never derives a discipline from generic labels such as `Middel incident`;
- `source_timing` compares the local Home Assistant first-observed time for BrandweerRooster and each matched P2000 provider; provider/source timestamps are retained separately so polling delay is not confused with original message time;
- conservative Netherlands-only `station_hints` and `unit_details` can use capcode descriptions as a fallback for otherwise unknown stations/units; BrandweerRooster-resolved station data remains leading and ambiguous P2000 evidence is never guessed;
- exact six-digit appliance numbers can additionally be resolved against a locally cached Brandbase current-vehicle registry; the cache is built dynamically from the public Brandbase region index, stored only in Home Assistant storage, refreshed at most weekly, and never bundled as a Brandbase dataset in this repository;
- raw six-digit tokens are retained separately as `unit_candidates_raw`; only exact vehicle-registry matches or strong capcode/unit-suffix evidence are exposed as confirmed `units`, while rejected candidates remain visible under `unresolved_unit_candidates` for diagnostics;
- a unique registry match adds canonical callsign, region, station and vehicle type information to `vehicles` and `unit_details`; ambiguous or missing registry entries remain unresolved rather than being guessed;
- P2000 enrichment survives incident closure/history storage and can be reused when practical groups are rebuilt after restart;
- stale technical BrandweerRooster ids can become `group_closed_pending_api` from conservative group-level closure evidence while raw BWR lifecycle fields stay unchanged;
- pending API closures are rechecked every 30 minutes and automatically become normal API closures when BWR later supplies `end_time`;
- `fireservicerota.mark_incident_closed` and `fireservicerota.reopen_incident` provide explicit local-only operational overrides without writing to BrandweerRooster;
- polling is configurable from 30 to 3600 seconds;
- a P2000 status sensor exposes polling health, ring-buffer size and the latest buffered message for testing;
- RTL-SDR is not enabled in 1.2.0 and remains reserved for a future release after hardware validation.

### Recommended use in dashboards and automations

For vehicle-aware dashboards and automations, prefer `p2000_enrichment.units`
as the confirmed unit list and `p2000_enrichment.unit_details` for per-unit
metadata. Use `unit_details[].vehicle_type_code` for generic logic such as
TS/HV/AL/HW/WT/HA/PM/DB/BRV/NBT classification, and use the more descriptive
`vehicle_type` when presenting the registry description to a user.

Do not use arbitrary six-digit tokens from the raw incident text as authoritative
vehicle identifiers. `unit_candidates_raw` and `unresolved_unit_candidates`
exist for diagnostics; `units` is the consumer-facing confirmed list. Local
specialist mappings or presentation overrides can still be layered on top in
Home Assistant without hard-coding them into the integration.

### 1.3.0 beta: local RTL-SDR source

The `1.3.0-beta` branch adds an optional local `rtl` P2000 provider. It subscribes
directly to the MQTT attributes publication produced by the Cyberjunky P2000
RTL-SDR add-on and normalizes those messages into the same `P2000Event` model
used by the online provider. The source can be configured as `online`, `rtl`,
or `both`.

The default MQTT attributes topic is:

```text
homeassistant/sensor/p2000_rtlsdr/2005/attributes
```

This matches the add-on's default "P2000 Brandweer" sensor (`id: 2005`). If a
different sensor id or MQTT base topic is used, configure the matching attributes
topic in the Extended options. RTL-SDR reception remains supplementary and does
not replace official alerting.

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
    +-- optional legacy user preferences
    |     +-- do_not_disturb (only when supplied by the API)
    |
    +-- mobile devices (BrandweerRooster NL, privacy-filtered)
    |     +-- enabled / alert_notifications_enabled
    |     +-- platform / model / app version / network
    |     +-- last_heartbeat_at
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