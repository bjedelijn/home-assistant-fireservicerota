# FireServiceRota / BrandweerRooster Extended documentation

**Extended maintainer:** Bernd Edelijn

These pages contain practical examples for **FireServiceRota Extended**. They are written to be reusable for different users and organizations and intentionally avoid local station IDs, vehicle numbers, private addresses, personal device names and other installation-specific data.

Current examples target **`1.2.0`**.

> Home Assistant is an additional information and automation layer. Do not use it as the only emergency alerting method. Official pager, app, P2000 and/or other approved alerting channels remain leading.

Questions, bug reports and contributions can be handled through the GitHub repository and issue tracker. No personal contact details are published here.

## Documentation

- [Getting started](Getting-Started.md)
- [Incident automations](Incident-Automations.md)
- [Complete automation package](examples/Complete-Automation-Package.yaml)
- [iPhone critical alerts](iPhone-Critical-Alerts.md)
- [Incident lifecycle and history](Incident-Lifecycle-and-History.md)
- [Crew staffing and assignments](Crew-Staffing.md)
- [Dashboard examples](Dashboard-Examples.md)
- [Updating from Git](Updating.md)
- [Privacy and safety](Privacy-and-Safety.md)
- [1.2.0 release notes](Release-Notes-1.2.0.md)
- [1.2.0-rc.8 release notes](Release-Notes-1.2.0-rc.8.md)

## Main entities

Typical Dutch entity IDs include:

```text
sensor.incidents
sensor.actieve_incidenten
sensor.incidenthistorie
sensor.pager
sensor.mobiele_apparaten
```

Multi-station installations can also expose station-specific duty entities and incident-response switches. Exact entity IDs depend on Home Assistant naming, language and the station names returned by the API.

Duty/availability is read-only in 1.2.0. Incident-response switches can write acknowledged/rejected responses and are disabled by default for newly created entity-registry entries. Public dashboard examples intentionally do not provide response buttons.

The legacy user-level `do_not_disturb` binary sensor remains for compatibility only when the API supplies that field. It is not the same as the per-device `alert_notifications_enabled` field on `sensor.mobiele_apparaten`.

## Example philosophy

The examples focus on information exposed by the integration itself:

- `trigger` (`new` / `update`)
- incident ID and lifecycle
- active incidents and unique history
- resolved tasks and stations
- dynamic `own_stations`, `own_affiliations` and incident affiliations
- per-membership response data
- `own_assignment`
- `crew_requirements`
- `crew_summary.individual_assignments_available`
- `fireservicerota_assignment_finalized`
- final staffing capture on operational closure
- restart-safe restoration of normalized staffing / own-response history
- opt-in `fireservicerota.backfill_history_staffing` for older retained history that genuinely lacks staffing data
- read-only pager/mobile communication diagnostics
- optional Netherlands-only P2000 enrichment, including separate BR/HV/IBGS scales and GRIP

The complete package combines these building blocks in one privacy-safe example. It demonstrates repeated TTS wording, separate day/night volumes, an optional on-duty guard for nighttime speech, and explicit Cast-session stop for speaker targets while leaving tablet targets untouched. BrandweerRooster mobile notification settings are not used as Home Assistant TTS gating.

Copy examples only after replacing placeholder entity IDs with the entities from your own Home Assistant installation.
