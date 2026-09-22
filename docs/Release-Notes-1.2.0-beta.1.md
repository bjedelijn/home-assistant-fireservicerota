# FireServiceRota Extended 1.2.0-beta.1

## Purpose

This beta starts the Netherlands-only P2000 enrichment work without changing the existing BrandweerRooster / FireServiceRota incident flow when the feature is disabled.

## Included in beta 1

- Based on 1.1.0-rc.4, including restart-safe staffing history.
- Optional P2000 enrichment for BrandweerRooster Netherlands only.
- Online P2000 provider using the AlarmeringDroid feed directly from Extended.
- No separate HA P2000 integration required for online mode.
- Polling only while one or more BrandweerRooster incidents are active.
- Configurable polling interval (30-3600 seconds, default 30).
- Correlation by incident time and coordinates when possible, with address/text fallback.
- Normalized P2000 messages, vehicle codes, capcodes, source and escalation flag stored under `p2000_enrichment`.
- Enrichment remains part of the incident snapshot when it moves into history.

## Not yet in beta 1

- RTL-SDR provider.
- Online-vs-ether latency comparison.
- Final tuning of incident grouping and matching thresholds based on live incidents.
- Dashboard changes for P2000 timeline / external units.

These are planned for a follow-up beta after testing with a real RTL-SDR receiver.

## Safety

P2000 enrichment is supplementary. Official pager/app/dispatch channels remain leading.
