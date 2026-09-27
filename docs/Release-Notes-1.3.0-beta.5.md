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

## Field regression case

Incident 3068369 in Hardenberg correctly matched:

- P2000 online: Parkweg Hardenberg, unit 042330
- P2000 via ether: Parkweg Hardenberg, unit 042330

Later RTL-SDR alerts from Lisse (161130) and Den Haag (157230) had the same generic text `Stank/hind. lucht (binnen)` and were incorrectly attached by the beta.4 text fallback.

Beta.5 rejects those alerts because their location evidence does not match Hardenberg. Existing stored enrichment is revalidated so the incorrect units can disappear automatically after the manager runs.

## Compatibility

- Internal P2000 source ids remain `online` and `rtl`.
- Raw provider buffering, practical online/ether grouping, source labels and beta.4 timing diagnostics remain available.
- Stable `extended` remains 1.2.0.
