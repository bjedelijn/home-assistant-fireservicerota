# FireServiceRota Extended 1.2.0-beta.8

Beta.8 adds conservative Netherlands-only station and unit hints from matched P2000 capcode descriptions. It is built on beta.7 without changing FireServiceRota UK behavior.

## Station hints

Matched P2000 enrichment can now expose:

```yaml
station_hints:
  - name: Example-Station
    source: p2000_capcode
    confidence: high
```

Station hints are only accepted from descriptions that look like station/appliance paging roles. Monitor codes, regional functions, officers, press information, dispatch-centre labels and non-fire disciplines are deliberately rejected.

## Unit fallback

For each six-digit P2000 unit, `unit_details` can provide a station fallback:

```yaml
unit_details:
  - unit: "209031"
    station_name: Example-Station
    station_source: p2000_capcode
    station_confidence: high
    station_reason: unit_suffix_match
```

Confidence rules are deliberately conservative:

- `high`: the capcode description contains a vehicle/unit suffix that matches the six-digit P2000 unit;
- `medium`: the P2000 event contains exactly one credible station hint;
- ambiguous multiple-station evidence is retained in `station_candidates` but no `station_name` is selected.

BrandweerRooster / FireServiceRota resolved station data is not overwritten. These fields are enrichment/fallback metadata only. Multiple P2000 station hints can coexist for one practical incident; beta.8 does not select one incident-wide main station.

## Escalation timeline

Explicit P2000 scale changes are normalized into a group-level timeline. Repeated messages at the same level are deduplicated and a later lower level never creates a downgrade event.

```yaml
escalation_timeline:
  - event_time: "2026-09-22T22:36:00+02:00"
    type: fire_scale
    level: medium_fire
  - event_time: "2026-09-22T22:45:00+02:00"
    type: fire_scale
    level: large_fire
  - event_time: "2026-09-22T22:52:00+02:00"
    type: grip
    level: grip_1

highest_fire_scale: large_fire
highest_grip: grip_1
```

Only explicit P2000 wording is used. Beta.8 does not invent an earlier lower fire scale when the first matched message already says `Middel BR`, nor does it infer arrival order or incident command from this timeline.

## Scope

All parsing is contained in `enrichment/nl/p2000`. FireServiceRota UK entries do not start the Netherlands P2000 enrichment path and are unaffected.
