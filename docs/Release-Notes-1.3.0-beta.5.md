# FireServiceRota Extended 1.3.0-beta.5

## Changes

- Tightens P2000 -> BrandweerRooster matching when one provider has no coordinates.
- A six-digit appliance/callsign present on both the BWR incident and P2000 alert is treated as strong evidence.
- Exact postcode remains strong evidence when available.
- Explicit city information that conflicts with the BWR incident is a hard reject.
- Explicit street/city/location-reference data must substantively match the BWR incident.
- Generic incident wording alone is no longer sufficient to correlate an alert.
- Previously attached P2000 messages are revalidated during each rebuild.
- Stale false-positive messages are removed from incident enrichment automatically.
- Persistent P2000 matches are rebuilt from revalidated events and removed when no valid evidence remains.
- Clearing stale P2000 enrichment never changes incident lifecycle, closure, staffing, responses, or original BrandweerRooster data.

## Anonymized regression case

An anonymized test incident correctly matched:

- P2000 online: Example Street, Example City, unit 012345
- P2000 via ether: Example Street, Example City, unit 012345

Later RTL-SDR alerts from two unrelated example locations, using placeholder units `023456` and `034567`, had the same generic incident wording and were incorrectly attached by the beta.4 text fallback.

Beta.5 rejects those alerts because their location evidence does not match the target incident. Existing stored enrichment is revalidated so the incorrect units can disappear automatically after the manager runs.

## Compatibility

- Internal P2000 source ids remain `online` and `rtl`.
- Raw provider buffering, practical online/ether grouping, source labels and beta.4 timing diagnostics remain available.
- Stable `extended` remains 1.2.0.
