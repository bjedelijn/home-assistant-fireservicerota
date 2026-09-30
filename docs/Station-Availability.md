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

For `next_schedule_change`, the integration reads the selected station membership's `combined_schedule` and uses the **end of the current agenda interval**. This matches the BrandweerRooster quick action: paraat and niet paraat both run only until the next roster change for that member on that post. The requested new availability state does not change the calculated end time.

The lookup window is seven days. If no current or next schedule interval can be found, the action fails instead of creating an open-ended exception.

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

## Write -> read-back verification (rc.4)

In rc.4 the service does not stop at a successful POST. After BrandweerRooster accepts the schedule exception, the integration refreshes the membership duty data and compares the **actual** availability with the requested availability.

When the action response is requested, these fields are returned:

```text
previous_available
actual_available
confirmed
status_changed
start_time
end_time
```

Meaning:

- `confirmed: true` means the refreshed BrandweerRooster membership state matches the requested state.
- `status_changed: true` means the refreshed state is different from the state seen before the write.
- `confirmed: true` together with `status_changed: false` means the requested state was already active; the temporary period can still have been updated.
- `confirmed: false` means the requested state was not confirmed by the read-back and should not be announced as successful.

Example with a Home Assistant response variable:

```yaml
- action: fireservicerota.set_station_availability
  data:
    station_id: 123
    available: true
    mode: next_schedule_change
  response_variable: availability_result

- choose:
    - conditions:
        - condition: template
          value_template: "{{ availability_result.confirmed | default(false) }}"
      sequence:
        - action: logbook.log
          data:
            name: FireServiceRota
            message: >-
              Confirmed: {{ availability_result.station_name }}
              is paraat until {{ availability_result.end_time }}.
  default:
    - action: logbook.log
      data:
        name: FireServiceRota
        message: "Availability write was not confirmed."
```

This verification is useful for dashboard confirmation, Siri/CarPlay speech and any automation where a successful HTTP response alone is not enough.

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

## Dashboard quick actions

A practical per-post set is:

```text
Paraat tot volgende roosterwijziging
Niet paraat tot volgende roosterwijziging
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

See [Dashboard examples](Dashboard-Examples.md) for a Bubble Card popup pattern and [CarPlay / Siri availability](CarPlay-Siri-Availability.md) for spoken, verified feedback.

> Home Assistant is an additional operational convenience layer. Official BrandweerRooster and organization procedures remain leading.
