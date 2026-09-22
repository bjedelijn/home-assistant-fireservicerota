# FireServiceRota Extended 1.2.0-beta.3

## P2000 ring buffer

Beta 3 changes the online P2000 enrichment path from incident-triggered polling to continuous reception while P2000 enrichment is enabled.

- Polls the online Brandweer P2000 feed continuously at the configured interval.
- Maintains an in-memory rolling buffer of unique recent P2000 events for 60 minutes.
- Supports a P2000 alert arriving before the corresponding BrandweerRooster incident.
- Continues matching later P2000 escalation messages while the BrandweerRooster incident is active.
- Deduplicates repeated provider results by external P2000 id, falling back to event time plus message.
- Keeps the first observed receive time for a repeated online event.
- Exposes a P2000 status sensor with buffer size, last poll result, provider health and latest event.
- Avoids rewriting unchanged incident enrichment on every poll.

## Still pending

- RTL-SDR provider and online-vs-ether timing comparison.
- Persistence of the rolling P2000 buffer across a Home Assistant restart; beta 3 buffer is intentionally memory-only.
- Final correlation threshold tuning based on real incidents.
- Region filtering / automatic region selection.
- Dashboard presentation for P2000 timeline and external units.

## Safety

P2000 enrichment is supplementary. Official pager/app/dispatch channels remain leading.
