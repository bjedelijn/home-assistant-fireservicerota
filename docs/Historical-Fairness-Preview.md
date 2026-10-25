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

For the next pages of locally retained history, use `offset`:

```yaml
action: fireservicerota.import_fairness_history
data:
  station_id: 100
  offset: 10
  limit: 10
  max_pages: 5
```

After that, use `offset: 20` and `limit: 5` (provided 25 incidents are
actually retained). The result includes `available_retained_incidents`
and `next_offset` to show whether another batch remains. Each request
fetches at most ten incidents. `offset` cannot be combined with explicit
`incident_ids`.

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

## Compact, incident-by-incident audit (no personnel list)

The cache now exposes an optional read-only view that avoids returning
individual names or membership/user IDs. In Developer Tools → Actions:

```yaml
action: fireservicerota.preview_fairness_history
data:
  station_id: 194
  overview_only: true
```

The response includes `incident_evidence_overview` ordered newest first:
incident ID, original proposal timestamp, task context/IDs, source role
labels with proposed seat counts, number of distinct proposed memberships,
members who appear in several distinct roles in one proposal, and
retrospective API-reported status and skill-assignment counts.

When a task ID is still present in the authenticated station's **current**
`groups[].tasks` metadata, the compact preview now additionally includes
`resolved_tasks` entries with the actual `name` from BrandweerRooster
(e.g. a WTS task), station-scoped by both ID and membership. The output also
contains `task_name_source:
current_station_task_index_not_historical_task_snapshot`.
A task absent from that current index or appearing with conflicting names
remains unresolved; the integration will not invent a vehicle type or assume
today's name proves the historical configuration. It uses the existing in-memory
discovery index without an additional network request or re-import.

This is useful to inspect a case with two `Chauffeur` proposals or
an overlapping proposed person without publishing full personnel lists.
More than one proposed chauffeur is **not by itself evidence of a bug or
two vehicles**, and a single API task ID does not prove everyone physically
travelled in one crew.

The full `historical_roles` candidate list is deliberately omitted
when `overview_only: true`. This does not alter stored data, fetch
anything from the API, or create a next-crew prediction.

## Task/vehicle context and registered API response comparison

The import now retains the numeric `incident_task_ids` in each private summary
and reports `task_context_incident_counts` in the preview:

- `single_incident_task`: the incident API listed only one task.
- `multiple_incident_tasks`: multiple possible tasks/vehicles. **No proposal
  person or role is attributed to any specific vehicle.**
- `no_task_ids`: task information not provided.
- `legacy_not_imported`: cached before this extension; task context is
  unknown until deliberately refreshed.

Role names such as "Manschap", "Chauffeur" or "Chauffeur Redvoertuig" remain
exact source labels, **not** a unique vehicle/task identifier. Vehicle/task
allocation will be supported only after source relationships are confirmed.

The new `proposal_to_api_record_comparison` section summarizes, per role,
the number of uniquely identified people from the **latest proposal** with
a corresponding API-reported status (e.g. `dispatched`, `shown_up`,
`no_show`, or `unknown`) and whether an API skill-assignment record exists
for that explicit membership. These are aggregated counts, **not**
independently verified turnout or confirmed seats. An API skill assignment
might describe a *different skill* than the proposed role. Conflicting
reported statuses are counted as ambiguous, never guessed.

Literal API status `unknown` is recorded as `unknown`. A missing or blank
reported status is recorded as `missing`. Earlier development revisions
produced `unmapped:unknown`; previews now automatically display those
previously cached values as `unknown` without an API refresh.
Neither value is proof of physical attendance or nonattendance.
Unknown machine-readable API status tokens now appear as
`unmapped:<api_status_code>` (for example, `unmapped:not_dispatched` only
if the API actually returned that value) instead of all being grouped into
`other`. `other` remains for invalid, free-form or unbounded status
values. The prefix means **uninterpreted source data**, not that someone
did or did not physically respond. Previously imported records still
have the older `other` grouping until explicitly refreshed; an import
with `refresh: false` will not recalculate their status breakdown.

Existing `.storage` records stay intact, and the preview will clearly show
how many imported incidents still lack this extra context. To populate the
additional evidence, **explicitly** reload a small batch:

```yaml
action: fireservicerota.import_fairness_history
data:
  station_id: 100
  offset: 0
  limit: 5
  max_pages: 5
  refresh: true
```

Do this only if you need the comparison. `refresh: true` re-reads complete
audit logs and uses the freshest recorded statuses available at query time,
which may differ from the recorded states at incident time. Regular calls
(`refresh: false`) skip cached incidents.

## Storage and privacy

- Local private key: `fireservicerota.historical_fairness_<entry_id>`.
- A maximum of **100 imported incident summaries per integration entry**,
  across stations; newer observations evict the oldest if necessary.
- Each record stores only the incident ID, station ID, latest proposal timestamp,
  proposal count, incident task ID context, role, unique person label and
  membership/user IDs, per-person retrospective API status and matching skill-assignment presence,
  plus role-level totals, and unmatched/ambiguous counters.
  It does **not** store the full audit report, individual response histories,
  exact pager details, or OAuth tokens.
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
3. The preview describes historical proposal candidates, incident-level task
   context and aggregate per-role API-record comparisons. It cannot verify
   actual vehicle occupation or attribute a proposal to a specific task when
   multiple incident tasks are present.
4. Future forecasting requires current staff availability, eligibility,
   task/vehicle requirements, overlapping roles, and the specific policy's
   historical real/virtual turnout accounting. **No exact lineup or
   confidence percentage is claimed until those inputs can be tested.**
5. CarPlay/Assist prompts and iPhone push actions are separate dashboard and
   automation work; CarPlay supports concise read-aloud status, not an
   unrestricted Home Assistant dashboard.

This feature remains in a **draft PR** until tests pass and the user verifies
real historical incidents. No automatic response or dispatch changes are made.
