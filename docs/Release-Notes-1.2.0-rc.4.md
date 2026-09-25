# FireServiceRota Extended 1.2.0-rc.4

This release candidate hardens the Netherlands online P2000 provider against cross-discipline subitems in AlarmeringDroid grouped incidents.

## Brandweer-only source filtering

The AlarmeringDroid request already asks for service `2` (Brandweer), but grouped incident results can contain related records from other emergency services in `subitems`.

rc.4 now:

- expands the main item and grouped `subitems` as before;
- checks the provider's per-record `dienst` field on every expanded record;
- accepts only records whose service is `2` (Brandweer);
- drops related non-fire-service records before normalization into `P2000Event`;
- keeps the rc.3 confirmed/unresolved vehicle resolver unchanged as an additional safety layer.

The filter is generic and contains no station, region, user, membership, task or local vehicle identifiers.

## Hardenberg validation case

For the Stelling/McDonald's incident the expected confirmed fire-service units remain:

- `041095`
- `042330`
- `042334`
- `042270`
- `053171`

The unrelated six-digit candidates `732699` and `732701` must no longer enter the normal online P2000 buffer when they originate from grouped non-fire-service records. The rc.3 resolver still protects enrichment if malformed, historic or alternative-source data contains an unconfirmed six-digit candidate.

## Scope

RTL-SDR remains outside 1.2.0. Dashboards, local automations, Telegram rendering and blueprints remain outside the integration.
