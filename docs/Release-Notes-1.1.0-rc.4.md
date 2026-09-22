# FireServiceRota Extended v1.1.0-rc.4

RC4 fixes restart persistence for historic staffing / turnout data and refreshes the public Home Assistant automation examples.

## Fixed

### Staffing history now survives Home Assistant restart

RC3 could restore retained incident history after a Home Assistant restart while dropping already-normalized staffing and own-response fields from the compact snapshot.

The incident itself remained present, but fields such as:

- `crew_summary`
- `crew_requirements`
- `crew_assignments`
- `own_responses`
- `own_response`
- `own_responding`
- `own_assignment`
- `assignment_revision`
- `assignment_last_changed_at`
- `assignment_final`
- `assignment_finalized_at`
- `staffing_final_checked_at`
- `staffing_backfilled_at`

could disappear until `fireservicerota.backfill_history_staffing` was run again.

RC4 preserves these normalized fields directly during `RestoreEntity` reconstruction. Historic data that was already known before shutdown therefore remains available after restart without an unnecessary REST refetch.

## Validated

The restart fix was validated against retained real-world history:

```text
matched: 14
checked: 0
updated: 0
unavailable: 0
failed: 0
skipped: 14
```

This confirms that all 14 retained snapshots already contained their staffing data after restart and no history backfill was required.

## Manual backfill remains available

`fireservicerota.backfill_history_staffing` is still available for legacy/imported history that genuinely never contained normalized staffing fields.

## Automation example updates

The privacy-safe complete automation package and incident automation documentation now also demonstrate:

- queued TTS with repeated incident wording;
- separate daytime and nighttime speech volumes;
- optional nighttime on-duty / Do Not Disturb gating;
- explicit `media_player.media_stop` after Google Cast / Nest speech to close lingering Cast sessions;
- leaving tablet targets untouched by that Cast-stop behavior;
- own-response speech only during daytime;
- media pause without powering devices on;
- live `new` / `update` protection and deduplication;
- `fireservicerota_assignment_finalized` handling.

All example entity IDs remain generic and privacy-safe.

## Compatibility

- Home Assistant integration version: `1.1.0-rc.4`
- `pyfireservicerota`: `0.0.49`
- Upgrade path: replace/update the custom integration from the `extended` branch and restart Home Assistant.

## Safety

Home Assistant and this integration remain an additional information and automation layer. Official pager, app, P2000 and/or other approved alerting channels remain leading.
