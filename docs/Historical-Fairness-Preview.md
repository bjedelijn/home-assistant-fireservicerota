# Historical fairness role preview (experimental)

> **Development branch:** `feature/historical-fairness-preview`. This is **not**
> included in stable 1.3.3. The stable `extended` branch is unchanged.

## Purpose

Collect a **small, user-requested** sample of historical BrandweerRooster
fairness suggestions, once, for stations where the authenticated user has an
active station membership. Store only minimal person/role evidence locally
inside Home Assistant's private `.storage`, **not in sensor attributes**.

This can seed a future advisory staffing forecast. It does **not** currently
predict who will respond to the next incident. It does not calculate
BrandweerRooster's proprietary fairness ranking.

## Import a known historical incident (developer branch only)

From **Developer Tools → Actions**, select:

```yaml
action: fireservicerota.import_fairness_history
data:
  station_id: 100
  incident_ids:
    - "1234567"
  max_pages: 5
```

Replace `100` and `1234567` with an authorized station ID and a real
incident ID. Without `incident_ids`, the service reads up to `limit` of
the most recent **25 retained closed** Home Assistant incidents:

```yaml
action: fireservicerota.import_fairness_history
data:
  station_id: 100
  limit: 5
  max_pages: 5
```

For a targeted set of older incidents, specify up to 10 IDs per action call.
The service fetches audit pages sequentially and uses only the *last observed*
proposal per distinct incident. A short audit page is not treated as proof that
the audit history is complete. When an audit is incomplete, its data is **not
imported**.

Already imported incident IDs are skipped without extra API requests by default.\nSet `refresh: true` to explicitly re-fetch previously cached incidents.\n\nThe tool rejects unresolved/multiple responding stations, repeated member
names mapping to multiple membership IDs, unknown proposal names, and
non-matching station identities. It reports why a particular incident was
skipped. A successful import may still contain unmatched proposed seats; those
are counted as missing evidence, not assigned to guessed people.

## View the candidate history

```yaml
action: fireservicerota.preview_fairness_history
data:
  station_id: 100
```

Returns the number of distinct complete audit incidents imported and an
observational list of members **per role**, identified by membership ID,
with `incidents_in_latest_proposal` and last observed timestamp.

These are **historical appearances**, not dispatches, confirmed seats, fairness
percentages, or selection probabilities. Frequent past appearances do not imply
a higher probability of being selected by a fairness-based algorithm. Neither
current availability nor task/vehicle competency requirements are evaluated,
so `prediction_status` is currently
`history_only_not_a_lineup_prediction`.

For Gramsbergen-like stations without automatic assignment, proposal history
will normally be absent. No suggestions **does not** automatically prove that
the setting is disabled.

## Storage and privacy

- Local private key: `fireservicerota.historical_fairness_<entry_id>`.
- A maximum of **100 imported incident summaries per integration entry**,
  across stations; newer observations evict the oldest if necessary.
- Each record stores only the incident ID, station ID, latest proposal timestamp,
  proposal count, role, unique person label and membership/user IDs, and
  unmatched/ambiguous counters. It does **not** store the full audit report,
  raw incident responses, exact pager details, or OAuth tokens.
- The feature runs **only when invoked**. It does not poll older incidents or
  automatically capture future alerts.
- Clear any station's locally stored data:

```yaml
action: fireservicerota.clear_fairness_history
data:
  station_id: 100
```

- Home Assistant backups can contain the `.storage` data. Protect backups and
  share only anonymized logs/fixtures.
- Do not publish live names, member IDs or incident reports on GitHub.

## Current limitations and roadmap

1. The API audit-report endpoint is observed working with an OAuth account but
   is not a guaranteed stable public API. Request bounds are small to prevent
   undue load.
2. Only 25 closed incidents are available in the existing HA incident sensor
   history. Older IDs must be provided explicitly; an authorized and
   documented incident-list API is not yet established.
3. First-stage preview only describes fairness proposals and uniquely matched
   membership IDs. It cannot verify actual vehicle occupation.
4. Future forecasting requires current staff availability, eligibility,
   task/vehicle requirements, overlapping roles, and the specific policy's
   historical real/virtual turnout accounting. **No exact lineup or
   confidence percentage is claimed until those inputs can be tested.**
5. CarPlay/Assist prompts and iPhone push actions are separate dashboard and
   automation work; CarPlay supports concise read-aloud status, not an
   unrestricted Home Assistant dashboard.

This feature remains in a **draft PR** until tests pass and the user verifies
real historical incidents. No automatic response or dispatch changes are made.
