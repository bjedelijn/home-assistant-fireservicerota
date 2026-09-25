# FireServiceRota Extended 1.2.0

FireServiceRota Extended 1.2.0 is the stable release built from the field-tested 1.2.0 beta and release-candidate line. The final code is based on 1.2.0-rc.8; the finalization itself promotes the version and documentation without changing the rc.8 runtime behavior.

## Main additions

- Optional Netherlands-only P2000 enrichment with continuous online polling.
- A rolling P2000 discovery buffer plus persistent confirmed practical-incident matches in Home Assistant storage.
- Correlation between BrandweerRooster incidents and P2000 messages, including messages that arrived before the BrandweerRooster incident.
- Separate fire, hulpverlening and IBGS escalation axes plus independent GRIP handling.
- Logical `incident_group` linking for multiple technical BrandweerRooster IDs that represent one practical incident without merging the underlying API records.
- Source timing that keeps Home Assistant observation time separate from provider/API source timestamps.
- Dutch postcode and provider location-reference normalization.
- Optional P2000 talkgroup/radio-channel hints as supporting evidence.

## Vehicle and station enrichment

- Six-digit P2000 tokens are retained as `unit_candidates_raw`.
- `units` contains only confirmed fire-service vehicles/units.
- `unresolved_unit_candidates` retains rejected or unresolved numeric candidates for diagnostics.
- Confirmation uses an exact unique locally cached Brandbase vehicle-registry match or strong P2000 capcode/unit-suffix evidence.
- `vehicles` and `unit_details` can expose callsign, region, station, vehicle type and normalized vehicle type code.
- The Brandbase dataset is not bundled in the repository; normalized data is fetched dynamically and cached only in Home Assistant storage.
- No station-specific or local vehicle list is hardcoded.

## Brandweer-only P2000 filtering

The final online provider keeps the AlarmeringDroid query restricted to service `2` and independently validates every expanded main item and grouped subitem.

- `dienstid == "2"` is the authoritative discipline check.
- `dienst == "Brandweer"` is used only as a fallback when the numeric id is absent.
- Explicit police/ambulance items are rejected before normalization into `P2000Event`.
- The confirmed/unresolved vehicle resolver remains active as an additional safety layer.

This behavior was validated against the live provider schema during rc.5 through rc.8.

## Lifecycle, persistence and account model

- Multiple concurrent incidents and unique retained history.
- Operational closure based on real API end timestamps, without treating `state: finished` alone as a definitive end.
- Conservative local group-level closure fallback for stale technical IDs while preserving raw BrandweerRooster lifecycle data.
- Persistent normalized staffing/response snapshots across Home Assistant restart.
- Final staffing capture on operational closure and optional historic staffing backfill.
- Dynamic authenticated-user station/group/membership discovery.
- Generic `own_stations`, `own_affiliations` and incident-level affiliation resolution.
- Read-only duty/availability support for multiple memberships.
- Per-membership incident response data and response switches; new response switch entities remain disabled by default.
- Pager and privacy-filtered mobile-device diagnostics.

## Validation from the RC line

The release-candidate tests included the Hardenberg practical incident around Stelling/McDonald's. The final resolver produced exactly the five expected confirmed fire-service units:

- `041095`
- `042270`
- `042330`
- `042334`
- `053171`

Unrelated six-digit values `732699` and `732701` were no longer presented as fire-service vehicles, and rc.8 corrected the provider discipline filter using the live-verified AlarmeringDroid fields.

## Compatibility and scope

- Home Assistant integration version: `1.2.0`.
- Python dependency remains `pyfireservicerota==0.0.49`.
- P2000 enrichment remains optional and Netherlands-only.
- Dashboards, local notification automations, Telegram rendering and blueprints remain outside the integration.
- RTL-SDR/FLEX is intentionally not part of 1.2.0 and remains planned for a later release after real hardware validation.

## Upgrade check

After updating, verify the installed manifest reports:

```text
1.2.0
```

Continue to treat official pager/app/dispatch channels as leading. Home Assistant and optional P2000 enrichment are supplementary.
