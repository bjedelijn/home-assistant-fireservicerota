# FireServiceRota / BrandweerRooster Extended documentation

**Extended maintainer:** Bernd Edelijn

These pages contain practical examples for **FireServiceRota Extended**. They are written to be reusable for different users and organizations and intentionally avoid local station IDs, vehicle numbers, private addresses, personal device names and other installation-specific data.

Current examples target **`1.1.0-rc.2`**.

> Home Assistant is an additional information and automation layer. Do not use it as the only emergency alerting method. Official pager, app, P2000 and/or other approved alerting channels remain leading.

## Documentation

- [Getting started](Getting-Started.md)
- [Incident automations](Incident-Automations.md)
- [iPhone critical alerts](iPhone-Critical-Alerts.md)
- [Incident lifecycle and history](Incident-Lifecycle-and-History.md)
- [Crew staffing and assignments](Crew-Staffing.md)
- [Dashboard examples](Dashboard-Examples.md)
- [Updating from Git](Updating.md)
- [Privacy and safety](Privacy-and-Safety.md)

## Main entities

Typical Dutch entity IDs are:

```text
sensor.incidents
sensor.actieve_incidenten
sensor.incidenthistorie
```

Multi-station installations can also expose station-specific duty and incident-response entities. Exact entity IDs depend on Home Assistant naming, language and the station names returned by the API.

## Example philosophy

The examples focus on information exposed by the integration itself:

- `trigger` (`new` / `update`)
- incident ID and lifecycle
- active incidents and unique history
- resolved tasks and stations
- per-membership responses
- `own_assignment`
- `crew_requirements`
- `fireservicerota_assignment_finalized`

Copy examples only after replacing placeholder entity IDs with the entities from your own Home Assistant installation.
