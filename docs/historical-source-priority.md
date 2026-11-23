# Historical statistics source policy: BWR leads, P2000 fills gaps

## Purpose

The user-visible historical statistics should prefer verified BrandweerRooster
(BWR) data. P2000/p2000.page can add missing older **alerts** or enrich
proven matched BWR incidents. Fairness, roster assignments and personal
attendance evidence **must only** originate from BWR and require the
separate historical audit validation rules.

The 392 locally indexed BWR records are only incident IDs and `created_at`
timestamps. They do not presently contain validated title, post, priority,
vehicle dispatch, or fairness records. No claim of full coverage is permitted
for 2019 through 2026. Older BWR visibility may be limited by when station
memberships were added.

## Implemented pure merge

`historical_source_merge.merge_bwr_p2000()` is deterministic and has **no
network access, no HA storage writes**. Input must be privacy-minimized,
validated metadata produced by an approved adapter, not raw provider output.

- BWR ID is the unique primary incident key.
- P2000 event ID is a separate stable source key.
- A P2000 event may join a BWR incident **only** via an externally verified
  `verified_links` mapping from P2000 ID to BWR ID. Similar timestamp,
  narrative, priority or station alone never qualifies.
- On an exact verified link, BWR scalar values remain authoritative.
  P2000 only fills fields not present in BWR. Conflicts are signaled; they
  never silently overwrite the BWR value.
- Without a verified match, the P2000 alert stays separate, whether or not
  an unrelated BWR incident shares a timestamp or a title.
- Multiple unmatched P2000 alert messages are **not automatically distinct
  incidents**. Consolidating multiple alarms/repeats for the same incident
  or vehicle requires a separately validated correlation algorithm.
- Provenance `field_sources` is retained for each filled value.
- The result intentionally excludes raw payloads, names, crew response
  objects, member IDs and incident IDs from any user-facing *summary*
  output. The per-record return value is an **internal** local processing
  representation; do not expose or log it directly.
- A record having `fairness_source: bwr_only` indicates **source
  eligibility**, not proof that audit evidence or member turnout exists.
  BWR incident audit must still validate before fairness counts are made.

## Integration steps still pending

1. Determine the exact normalized fields available from actual BWR incident
   detail, with a small manually approved and shared-budget-constrained
   diagnostic. Do not fetch all 392 incident details without this test.
2. Check p2000.page historical API scope, authorization, retention and
   pagination. The current live-event connection does not prove access to
   historical raw events. Build bounded retrieval and provider-specific
   limits only when its historical API is confirmed.
3. Convert each source into minimal normalized records with stable IDs,
   explicit station scope, timezone-aware event timestamp, and evidence
   levels. Reject ambiguous values.
4. Correlate on independently validated evidence, with explicit handling
   of conflicting, duplicated or cancelled alerts. Never imply departure
   from an alarm alone.
5. Persist merged incident statistics and source provenance separately from
   restricted historical BWR fairness evidence. Apply archive retention and
   do not send raw incident titles or station identities to GitHub.
6. Add a read-only aggregate action to inspect coverage and compare yearly
   BWR-only / verified-merged / P2000-only counts, without revealing IDs.
   Only then introduce user-facing combined yearly totals.

## API precautions

All future historical BWR requests must pass through
`HistoricalRequestBudget`, which currently enforces a conservative
per-entry daily ceiling and pacing. The actual provider quota remains unknown.
The existing offline index analysis and the pure merge add **zero** BWR
or p2000.page requests.
