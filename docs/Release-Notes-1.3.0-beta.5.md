# FireServiceRota Extended 1.3.0-beta.5

## Fixes

- Hardened P2000-to-BrandweerRooster correlation for providers without coordinates.
- Appliance/callsign overlap, exact postcode, and explicit city/street/location-reference evidence are treated as strong matching signals.
- A known P2000 city that is absent from the BrandweerRooster incident is rejected.
- Generic incident wording alone is no longer sufficient to attach a P2000 alert.
- Existing attached P2000 messages are revalidated on rebuild, so false-positive historical enrichment can be removed.
- Persistent match storage is revalidated using the same matcher.

## Concrete regression case

A Hardenberg incident with:

`P 2 BON-01 Stank/hind. lucht (binnen) Parkweg Hardenberg 042330`

must not absorb unrelated RTL-SDR alerts such as:

- `P 1 BDH-01 Stank/hind. lucht (binnen) Koningstraat Lisse 161130`
- `P 2 BDH-01 Stank/hind. lucht (binnen) Obrechtstraat 's-Gravenhage 157230`

The Hardenberg online/ether observations remain valid because they carry matching Hardenberg/Parkweg and/or `042330` evidence.
