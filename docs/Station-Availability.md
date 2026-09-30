# Station availability / paraat

From **1.3.0-rc.2**, FireServiceRota Extended can create temporary BrandweerRooster availability exceptions per station membership.

The integration discovers active station memberships dynamically. No station name, group ID or membership ID is hard-coded in the integration.

## Home Assistant action

Use:

```text
fireservicerota.set_station_availability
```

Select one station by `membership_id` or `station_id`. When an account has exactly one active station membership, both fields may be omitted.

### Paraat for a fixed period

```yaml
action: fireservicerota.set_station_availability
data:
  station_id: 123
  available: true
  mode: 2h
```

### Niet paraat for a fixed period

```yaml
action: fireservicerota.set_station_availability
data:
  station_id: 123
  available: false
  mode: 4h
```

Fixed modes are:

```text
1h
2h
4h
8h
```

### Until the schedule takes over again

```yaml
action: fireservicerota.set_station_availability
data:
  station_id: 123
  available: true
  mode: next_schedule_change
```

For `next_schedule_change`, the integration reads the membership's combined schedule. If the current effective schedule already has the requested state, the override ends at the end of that contiguous period. If the current effective schedule has the opposite state, the override ends when a future schedule interval first has the requested state.

The lookup window is seven days. If no suitable takeover point is found, the action fails instead of creating an open-ended exception.

### Custom period

```yaml
action: fireservicerota.set_station_availability
data:
  station_id: 123
  available: false
  mode: custom
  start_time: "2026-09-30 10:00:00"
  end_time: "2026-09-30 14:00:00"
```

Start and end times are normalized to BrandweerRooster 15-minute blocks. If `start_time` is omitted, the current 15-minute block is used.

## Per-post behavior

Availability is always written to the selected **station membership**:

```text
POST memberships/{membership_id}/schedule_exceptions
```

Team/specialist memberships are not used for this action. Multi-station users therefore keep independent paraat/niet-paraat state per post.

The service validates that a supplied membership belongs to the authenticated user's active station memberships. A supplied `station_id` must resolve to exactly one active station membership.

## Schedule warnings

By default the action sends:

```text
ignore_schedule_warnings: true
```

This matches the intended quick-action behavior: staffing warnings do not cause an otherwise valid CarPlay/Home Assistant action to fail unexpectedly. Set the field to `false` if you explicitly want BrandweerRooster staffing warnings to reject the write.

## CarPlay / dashboards

CarPlay presentation is intentionally not implemented inside the integration. Build the driving UI in Home Assistant and call the service above.

A practical per-post set is:

```text
Paraat tot volgende rooster-overgang
Niet paraat tot volgende rooster-overgang
Paraat 1 uur
Paraat 2 uur
Paraat 4 uur
Paraat 8 uur
Niet paraat 1 uur
Niet paraat 2 uur
Niet paraat 4 uur
Niet paraat 8 uur
```

Use the station-specific duty binary sensors to discover the relevant `station_id` / `membership_id` attributes instead of hard-coding personal IDs into reusable blueprints or public examples.

After a successful write, the integration refreshes membership availability so Home Assistant reflects the updated BrandweerRooster state.

> Home Assistant is an additional operational convenience layer. Official BrandweerRooster and organization procedures remain leading.
