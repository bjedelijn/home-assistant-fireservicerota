# FireServiceRota Extended 1.2.0-beta.9

Beta.9 adds practical-incident source timing for analysis. It builds on beta.8 and does not change incident matching, station precedence or lifecycle behavior.

## Source timing

Matched P2000 enrichment can now expose a `source_timing` block:

```yaml
source_timing:
  comparison_basis: home_assistant_observed_at
  first_detected_source: brandweerrooster
  first_detected_at: "2026-09-23T12:01:08.613+02:00"
  sources:
    brandweerrooster:
      observed_at: "2026-09-23T12:01:08.613+02:00"
      source_time: "2026-09-23T12:01:08.520+02:00"
      transport: websocket
      delta_from_first_ms: 0
    p2000_online:
      observed_at: "2026-09-23T12:01:30.115+02:00"
      source_time: "2026-09-23T12:01:00+02:00"
      transport: polling
      poll_interval_seconds: 30
      delta_from_first_ms: 21502
```

`first_detected_source` is based only on the local Home Assistant observation timestamp. This makes the comparison fair between transports. P2000 `event_time` and BrandweerRooster `start_time` / `created_at` are retained separately as `source_time` and are not used to decide which source reached Home Assistant first.

For additional analysis, every source also gets `source_time_delta_from_earliest_ms`; `earliest_source_time` and `earliest_source_time_source` describe the earliest provider/API timestamp. These values may have different precision and should not be interpreted as transport latency.

## BrandweerRooster first transport

New incidents retain `first_seen_source` (for example `websocket` or `rest`) alongside `first_seen_at`. Older restored history keeps its original `first_seen_at`; when no historical first transport was stored, beta.9 reports the BrandweerRooster transport as `unknown` rather than guessing.

## RTL-SDR readiness

The timing model is provider-agnostic within the Netherlands P2000 enrichment path. A future P2000 provider with source `rtl_sdr` will appear as `p2000_rtl` with transport `rtl_sdr` without changing the practical-incident timing schema.

FireServiceRota UK behavior is unchanged; the P2000 timing comparison remains contained in `enrichment/nl/p2000`.
