# Year and month statistics by station, vehicle and speciality

The eventual Home Assistant view should offer an annual selector and January–
December rows, split by **priority 1 / priority 2** and by:
- distinct incidents per authorized station;
- vehicle/callsign within that station;
- generic speciality (TS, RV, HV, WO, WTS, etc.).

**Source quality is a first-class dimension**, not a footnote. Count
`alerted`, `reported_departure` and `verified_departure` separately. P2000
units are *alerted* only; BWR tasks (including shared requirements) do not
prove a unit's physical turnout. A priority must come from verified incident
metadata; do not infer it from arbitrary text or a task ID.

The pure, tested `dispatch_statistics.py` aggregator now supports 12-month
and annual roll-ups with deduplication by incident/station/vehicle, and a
generic speciality allowlist. It is **not yet wired into HA sensors or real
incident ingestion**, because that would risk reporting partial existing
25-incident snapshots as a complete annual total.

## Retention plan

- Private, detailed historical incidents and fairness audits: target 90 days
  with time-based expiry and an adequate safety cap, subject to implementation
  and review. The existing 25-item operational history and 100-item fairness
  cache have **not** been changed by this statistics module.
- Durable aggregate yearly/monthly counters: separate private HA Store.
- Deduplication needs a minimally retained opaque incident/station/vehicle
  ledger so restarts and late updates cannot double-count incidents. Retention
  and correction handling must be explicitly verified before automated ingest.
- Do not expose station/unit operational identifiers, free-text speciality
  labels, or real call data in public GitHub issues/PRs/tests/logs.
- Only display `complete` annual figures after reliable historical backfill
  or continuous, persistent event ingestion; otherwise label them `partial`.

## Example layout (all numbers fictional)

Year | Station | Vehicle or speciality | P1 | P2 | Total
:-- | :-- | :-- | --: | --: | --:
2025 | Example Station | Entire station | 12 | 18 | 30
2025 | Example Station | TS | 8 | 13 | 21
2025 | Example Station | RV | 4 | 5 | 9

Each row also contains January–December counts. Do not add station totals
and unit totals together; one incident may involve several vehicles.
