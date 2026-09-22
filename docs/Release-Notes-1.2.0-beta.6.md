# FireServiceRota Extended 1.2.0-beta.6

Beta.6 improves the Netherlands-only optional P2000 enrichment path.

## Changes

- Splits a provider location code into:
  - `postcode` for a valid Dutch postcode;
  - `location_reference` for non-postcode values such as motorway/hectometer references.
- Keeps normalized P2000 city names without duplicated postcode prefixes.
- Keeps generic six-digit appliance/unit extraction introduced after beta.4.
- Adds optional normalized P2000 `talkgroups` hints when the provider exposes a compatible field.
- Adds logical `incident_group` metadata for multiple BrandweerRooster API incident ids that appear to represent one practical incident.
- Groups are based on time plus strong location evidence, with radio-channel overlap and incident text used as supporting evidence.
- Original BrandweerRooster incident ids, lifecycle, staffing and history entries remain separate; grouping is metadata only.
- P2000 enrichment is correlated to the logical group and then attached to every technical BrandweerRooster incident id in that group.
- BrandweerRooster station/alert `groups` are not treated as C2000 talkgroups.

## Notes

The grouping logic is deliberately conservative. It does not merge BrandweerRooster records and does not change incident lifecycle behavior.

Dashboard changes are intentionally deferred until real incidents have validated the new `incident_group` and `p2000_enrichment` structures.
