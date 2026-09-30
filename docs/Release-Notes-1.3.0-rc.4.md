# FireServiceRota Extended 1.3.0-rc.4

Release candidate 4 refines the station availability write flow so it mirrors the BrandweerRooster quick action more closely.

## Station availability

- Availability is written per dynamically discovered **station membership**. No station or membership IDs are hard-coded.
- `next_schedule_change` now ends at the **end of the current agenda interval** for that member on that post.
- The calculated end time is independent of whether the requested state is paraat or niet paraat.
- Fixed quick periods remain available:
  - 1 hour
  - 2 hours
  - 4 hours
  - 8 hours
- Custom start/end periods remain supported.
- Writes use:
  `POST memberships/{membership_id}/schedule_exceptions`
- The integration refreshes membership duty after a successful write.
- The action response now includes read-back verification fields:
  - `previous_available`
  - `actual_available`
  - `confirmed`
  - `status_changed`
- `confirmed` is only true when refreshed BrandweerRooster membership duty matches the requested state. This supports reliable dashboard and Siri/CarPlay feedback instead of announcing success from the POST alone.
- Schedule warnings remain ignored by default for quick-action use, unless explicitly disabled.

## Home Assistant action

Use:

```text
fireservicerota.set_station_availability
```

Example:

```yaml
action: fireservicerota.set_station_availability
data:
  station_id: 123
  available: false
  mode: next_schedule_change
```

For fixed periods use `1h`, `2h`, `4h` or `8h`.

## Scope

Availability control is intentionally limited to station memberships. Team, platoon, task and specialist memberships are not used for paraat/niet-paraat writes unless BrandweerRooster behavior proves otherwise in a future release.


## Dashboard and CarPlay examples

- Added a privacy-safe Bubble Card station-availability popup example.
- Added a reusable Home Assistant package pattern with a central verified availability script.
- Added a Siri/CarPlay guide using Home Assistant script execution, read-back confirmation text and spoken feedback.
- Added `docs/examples/Station-Availability-CarPlay-Package.yaml` as a reusable starting point.

