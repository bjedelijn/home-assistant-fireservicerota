# FireServiceRota Extended 1.2.0-rc.1

## Release-candidate scope

1.2.0-rc.1 consolidates the 1.2.0 beta line into the first release candidate. It is based on 1.1.0-rc.4 and contains no new operational write feature compared with beta.12.

The main goal of rc.1 is field validation, documentation cleanup and compatibility testing before 1.2.0 final.

## Netherlands P2000 enrichment

P2000 enrichment remains optional, Netherlands-only and disabled by default.

The 1.2.0 line includes:

- continuous online polling with a 60-minute in-memory ring buffer;
- persistent confirmed practical-incident matches in `sensor.p2000_matches`;
- correlation with incidents that arrive before or after the P2000 message;
- Dutch postcode/location-reference normalization;
- generic six-digit unit extraction;
- conservative station/unit hints from capcode descriptions;
- practical grouping of related BrandweerRooster technical incident IDs without merging the underlying API records;
- source timing that keeps Home Assistant observation time separate from provider/API source timestamps;
- local operational lifecycle fallbacks for stale technical IDs while preserving raw BrandweerRooster lifecycle fields;
- local-only manual close/reopen services;
- explicit, independent incident scales:
  - fire: `highest_fire_scale`;
  - hulpverlening: `highest_hv_scale`;
  - dangerous substances/IBGS: `highest_ibgs_scale`;
  - GRIP: `highest_grip`;
- an `escalation_timeline` containing only explicitly observed upward milestones per discipline.

Generic wording such as `Middel incident` does not imply fire, HV or IBGS. The discipline must be explicit in the P2000 message.

RTL-SDR is not part of 1.2.0 and remains reserved for a future release after hardware validation.

## Dynamic account affiliations

The authenticated account is discovered dynamically:

- `own_stations` contains active station memberships;
- `own_affiliations` also supports team/specialist memberships;
- `own_incident_affiliations` links incident task/response context back to the user's current affiliations.

No local station, user, membership, task or vehicle IDs are hard-coded in the integration.

## Duty and incident responses

Per-station duty/availability is read-only in 1.2.0-rc.1. Extended reads the current combined schedule but does not create planning/availability exceptions.

Per-membership incident-response support remains available for acknowledged/rejected responses. Those controls perform real service writes.

For safety:

- newly created incident-response switch entities are disabled by default;
- existing Home Assistant entity-registry choices are preserved;
- the standard dashboard documentation does not include response buttons.

## Pager and mobile communication diagnostics

The Pager sensor exposes selected fields such as battery level, last-seen timestamp and signal data when available.

BrandweerRooster Netherlands also gets a read-only Mobile devices sensor with selected fields such as:

- device ID;
- platform/model;
- OS and app version;
- enabled state;
- `alert_notifications_enabled`;
- network type;
- last heartbeat;
- battery level when supplied.

Mobile push tokens, UUIDs, IMEI, serial identifiers and live-update tokens are deliberately not exposed.

The optional legacy user-level `do_not_disturb` field remains separate from per-device mobile alert settings.

## Incident lifecycle, history and staffing

1.2.0-rc.1 retains the Extended lifecycle/staffing work from the 1.1 release-candidate line and later beta refinements:

- multiple concurrent incidents;
- unique retained history;
- real API end-time preference;
- no closure based only on `state: finished`;
- final staffing capture on real operational closure;
- restart-safe normalized staffing/own-response snapshots;
- opt-in historic staffing backfill;
- dynamic requirements, skill coverage and individual assignments when exposed by the API.

## Upgrade / testing

Use the release-candidate branch:

```bash
/config/update_fsr.sh 1.2.0-rc
```

Verify the installed manifest reports:

```text
1.2.0-rc.1
```

Continue to treat official pager/app/dispatch channels as leading. Home Assistant and optional P2000 enrichment are supplementary.

Questions, bug reports and contributions can be handled through the GitHub repository and issue tracker.
