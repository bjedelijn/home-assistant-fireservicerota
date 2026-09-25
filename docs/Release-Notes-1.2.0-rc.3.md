# FireServiceRota Extended 1.2.0-rc.3

This release candidate refines the Netherlands P2000 vehicle enrichment added in rc.2.

## Confirmed vehicles versus raw numeric candidates

P2000 message text can contain six-digit numeric tokens that look like appliance numbers but are not actual dispatched fire-service vehicles. rc.3 therefore separates extraction from confirmation.

- `unit_candidates_raw` retains every six-digit candidate extracted from the matched P2000 messages.
- `units` now contains only confirmed fire-service vehicle/unit numbers.
- A candidate is confirmed when it has either:
  - an exact unique match in the locally cached Brandbase vehicle registry; or
  - strong P2000 capcode evidence with an explicit appliance/unit suffix match.
- `unresolved_unit_candidates` retains rejected or still-unproven candidates for diagnostics instead of silently discarding them.
- `unit_details` records `vehicle_confirmed`, `vehicle_confirmation_source` and `vehicle_confirmation_reason`.
- `vehicles` contains confirmed vehicle records only.
- Existing stored P2000 messages can be rebuilt through the new resolver, so retained historical incidents with P2000 enrichment can also lose old false-positive unit candidates.

This specifically prevents unrelated six-digit values such as `732699` and `732701` from being presented as dispatched vehicles when no vehicle or strong capcode identity supports them.

## Scope

No station-specific vehicle list is hardcoded. Dashboards and local automations remain outside the integration. RTL-SDR remains reserved for a later release after real receiver validation.
