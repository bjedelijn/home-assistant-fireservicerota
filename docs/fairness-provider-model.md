# Provider fairness model and validation roadmap

Sources checked 2026-11-24:
- [New algorithm](https://help.fireservicerota.com/nl/article/hoe-werkt-het-nieuwe-eerlijk-inzetvoorstel)
- [Old algorithm](https://help.fireservicerota.com/nl/article/hoe-werkt-het-oude-eerlijk-inzetvoorstel)
- [Corrections and scope](https://help.fireservicerota.com/nl/article/eerlijk-inzetvoorstel-corrigeren-en-afwijken)
- [Reports, boost and stop](https://help.fireservicerota.com/nl/article/rapportages-en-gebruikers-boosten)
- [Proposal delivery](https://help.fireservicerota.com/nl/article/waar-zie-ik-het-eerlijk-inzetvoorstel)

## Documented rules
Both versions prioritize on-call/piket, available in ready team, available in non-ready team, unavailable, in that order. Old version ranks within group by elapsed days since last turnout and allocates roles randomly. New version ranks by ascending (real + virtual turnouts) / alarms, using last ten turnouts or current calendar year, whichever is shorter. Virtual turnout requires an obligation to attend and failure/refusal to attend; attendance without departure contributes an alarm but not a turnout. Roles use role-specific historical percentages. Reports cover task/vehicle, skill and individual. Boost/stop can affect general or skill priority; historical incident UI can show these indicators. Corrections affect subsequent calculations; provider can configure vehicle and incident-type scope.

## Unknowns and safeguards
Do not infer algorithm version, eligibility, denominator membership, virtual turnout, boosts, tie-breaking, window boundaries or exact role optimization from proposal or current status alone. Zero denominator is undefined. Unknown outcome is not no-show. Do not equate priority group with incident priority. Provider report endpoint and permissions remain unverified; inspect existing authorized read-only capabilities before attempting any endpoint, never guess URLs or bypass permissions. Local statistics must not be described as provider scores until validated. No operational assignment or remote write.

## Implementation roadmap
1. Per-station algorithm mode (unknown/old/new), task/vehicle and incident priority scope, with separate inclusion and proposal-following policies; local configuration not assumed to equal provider configuration. Preserve existing Hardenberg prio-1/2 behavior pending verification.
2. Immutable first and subsequent proposal snapshots; first observed registration, latest registration, timestamped revisions and source provenance. Distinguish observed registration from physical turnout. Reconstruct audit transitions with fixed label vocabulary, unique station-authorized membership matching, timestamp ordering, chain continuity and current API reconciliation. Keep unresolved data explicit. No raw personal audit text in diagnostics or repository.
3. Recheck policies per station: proposed Hardenberg initial, 24h, 3d, 7d, 14d, 30d, optional 60d; Gramsbergen initial, 24h, 30d; configurable, no assumption corrections are impossible elsewhere. Idempotent revisions, bounded retention, local HA storage only.
4. Separate actual registered, virtual (only with historical obligation evidence), attendance without departure, unknown and proposal statistics. Maintain both year and rolling windows by task/vehicle/role, with coverage flags. Historical eligibility and skill evidence required. Never count a proposal as turnout.
5. Investigate authorized provider report availability and historical boost/stop flags; compare local results against official report fixtures before enabling any reconstructed score. No inferred boost amount.
6. Historical reads share existing per-entry 200/day UTC cap and 2-second spacing with provider throttling safeguards; this is not a known provider quota. Add synthetic tests for privacy, ambiguity, corrections, ordering, year boundaries, missing evidence, station isolation and budget. No bulk import or production merge until validated.
