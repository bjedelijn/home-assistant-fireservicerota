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

## Retained incident skill coverage (compact preview only)

The same `overview_only: true` action also performs a **local, read-only**
join with retained Home Assistant incident snapshots. No audit re-import, new
incident API call, or storage update is required.

For unambiguously station- and task-scoped `crew_requirements`, the preview
adds `crew_requirement_evidence` with `required`, recorded `assigned`,
and `shortfall` per skill. For example, a WTS with two assigned drivers
of two required, but two recorded manschap skill coverages of four required,
has a **two-manschap skill-coverage shortfall**. This does not establish two
missing unique personnel; overlapping role requirements are never summed.

The `coverage_source` value `warning_statuses_available_memberships`
indicates availability, not assigned crew; the preview deliberately returns
`assigned: null`, `shortfall: null`, and potentially `sufficient: null`.
If an incident snapshot or unambiguous task/station mapping is missing, a
`crew_coverage_status` describes missing evidence rather than guessing.

`crew_coverage_source` identifies this as a retained normalized incident
snapshot, **not** a snapshot taken at the time of the fairness proposal.
Neither assignments nor `dispatched` independently prove physical turnout.
The diagnostic remains descriptive, without scores or crew predictions.

### Regular TS crew versus supplementary aspirant

A TS `Asp` aspirant is an **additional position** rather than a required
position of the normal TS crew. The compact preview explicitly distinguishes:

- `sufficient`: the original comparison of **all** API-configured
  requirements, including supplementary positions and the API warning counts.
  It is retained for provenance and may be `false` for an otherwise fully
  staffed TS.
- `regular_crew_sufficient`: derived from the per-skill
  `individual_assignment_count` records for the regular crew, independent of
  the supplementary aspirant.
- `supplemental_positions_sufficient`: separate coverage of known additional
  Asp positions. `false` here alone does not make a regular TS6 deficient.
- `position_type`: `regular` or `supplemental`, on each skill entry.
  Classifying `Asp` as supplemental requires the resolved single task to be
  a TS, with an unambiguous `Asp` code. If the current incident omitted that
  code, it can be resolved using a matching station/task/skill code from
  another locally retained incident. No numeric skill ID is hard-coded.

The existing `assigned` field represents its original
`warning_statuses` count (or other source as indicated), **not** necessarily
the number of people with explicit role assignments. The separate
`individual_assignment_count` reports the latter type of evidence. The
`regular_crew_sufficient` and `supplemental_positions_sufficient` values
remain `null` where such count evidence is missing; neither proves who
physically boarded a vehicle. The derived TS distinction does not change
`crew_summary.sufficient`, any live operational behavior, or the stored
incident snapshot. Current task metadata may not represent historical rules.

## Inspect staffing for an incident no longer in the last 25

The ordinary `backfill_history_staffing` action is intentionally limited to
the incident snapshots still retained by Home Assistant. Older incident
fairness records can still exist independently in private historical storage.

If a cached incident has `no_retained_staffing_snapshot`, explicitly call:

```yaml
action: fireservicerota.inspect_historical_staffing
data:
  station_id: 194
  incident_id: "3076036"
```

This optional action verifies the account's station membership and requires
the incident to already exist in that station's private historical fairness
cache. It sends **exactly one authenticated GET** for
`incidents/{incident_id}`, never downloads the audit log, never changes
BrandweerRooster, and never modifies the local 25-incident history or
historical fairness cache.

The response contains an identity-free, on-demand `crew_requirement_evidence`
view (including regular versus supplemental role coverage where evidenced),
`crew_coverage_status`, resolved task metadata and explicit provenance. It
checks that the incident ID and task IDs returned by the API agree with the
stored fairness record; disagreement or missing staffing data is reported as
unknown instead of guessed. It is **retrospective current API data**, not an
independently verified turnout or a snapshot made at the fairness-proposal
time.

This is initially **inspection only**: the main compact fairness preview will
continue to show `no_retained_staffing_snapshot` for the older incident.
A separate, reviewed opt-in persistence step would be needed to save that
minimal staffing evidence in the local private fairness cache.

## Save inspected staffing evidence locally (explicit opt-in)

After confirming that an evicted incident's one-time API inspection returns
`crew_coverage_status: recorded_skill_requirements_found`, the operator may
**explicitly** save that evidence to Home Assistant private storage:

```yaml
action: fireservicerota.save_historical_staffing
data:
  station_id: 194
  incident_id: "3076036"
```

This makes **one new read-only GET** for that incident. The response is
validated against the matching historical fairness cache entry and its task IDs.
Only a whitelisted, identity-free subset of the skill requirements, assigned
counts, individually assigned counts, regular/supplemental position status,
source, and GET timestamp is written to the *existing* private historical
fairness record. It preserves fairness candidate histories and their audit
timestamps. It does not store full API payloads, staff names, memberships,
individual responses, audit lines, or credentials.

If the API returns no usable staffing, mismatched tasks, or ambiguous evidence,
nothing is saved. This action never reimports the fairness audit, sends API
writes, modifies `sensor.incidenthistorie`, or raises the 25-incident history
retention limit. It does not run automatically.

After successful saving, rerun:

```yaml
action: fireservicerota.preview_fairness_history
data:
  station_id: 194
  overview_only: true
```

The evicted incident's existing fairness overview can then show the stored
`crew_requirement_evidence`, `regular_crew_sufficient`, and any separate
supplemental coverage. The row identifies
`crew_coverage_evidence_source:
explicitly_saved_single_incident_api_snapshot` and its
`crew_coverage_checked_at` time. Fresh HA retained incident snapshots take
precedence over separately saved evidence, if an incident is retained again.

The saved counts are **retrospective API evidence** and may differ from both
the state at the fairness proposal time and the physical crew that traveled.
Any later explicit fairness audit re-import of this same incident retains
opted-in staffing evidence as long as the incident task IDs still match.
The 100-record private storage limit still applies.

## Phase 1: task-scoped, read-only fairness advisory (NOT a lineup forecast)

This opt-in action is a preliminary diagnostic for an active station membership.
It requires a **task ID**, not a vehicle name or an assumed generic crew size.
For example, the previously observed Hardenberg task IDs are `7674` (TS),
`7689` (RV), and `7001` (WTS). Do not assume IDs are globally valid.

In Developer Tools -> Actions:

```yaml
action: fireservicerota.preview_fairness_advisory
data:
  station_id: 194
  task_id: 7674
```

The response is anonymous by default and contains:

- `historical_sample`: number of distinct full-audit incidents matching **only
  this single task at this station**, how many contained complete person/role
  matches, and how many multi-task / partial matches were excluded.
- `historical_roles`: exact recorded role labels and distinct candidate
  counts, repeated proposal appearances, and min/max observed proposed-role
  counts. These are **proposals**, not a count of actually staffed seats.
- `historical_crew_requirement_evidence`: explicitly observed per-skill
  required counts and regular coverage from historical incident snapshots,
  including separately saved post-retention snapshots. This is **not** a
  live task configuration. TS `Aspirant Manschap` is supplemental only
  when task metadata unambiguously confirms a TS.
- `current_station_roster_shape`: anonymous counts and safe field names from
  already cached BrandweerRooster group discovery. This is deliberately not
  treated as a live duty roster or validated task qualification.
- `prediction_status: historical_task_evidence_only_not_ready_for_lineup`
  and `predicted_lineup: null`; no percentages, selection probabilities,
  dispatches or staffing plans are calculated.

For a *private local* view of which historical memberships were proposed, set
`include_people: true`:

```yaml
action: fireservicerota.preview_fairness_advisory
data:
  station_id: 194
  task_id: 7674
  include_people: true
```

This adds the **already cached** name, membership ID, incident proposal count,
last proposal time and retrospective API statuses for each person per role.
People are listed alphabetically, **not** ranked by likelihood or fairness.
Never paste an identifiable output into a public issue or commit it to GitHub.
Neither the default nor this opt-in mode writes new data or contacts
BrandweerRooster; all inputs come from the existing private cache, locally
retained incident evidence and group discovery already held by Home Assistant.

### What is still needed for a real advisory prediction?

Before any ranking, staffing simulation or expected lineup can responsibly
be produced, obtain and test a properly **current**, station-scoped eligible
candidate pool, availability/on-duty evidence, actual task skill and
qualification requirements, and a reproducible **held-out historical backtest**.
A person's absence from a historical fairness proposal must not count as a
negative outcome, since we do not know whether they were eligible or on duty.
An API `dispatched` record is not physical confirmation that a person boarded
a vehicle. Different tasks (including WTS and RV) must remain separate.
A supplemental aspirant must never be used to make an otherwise complete
regular TS crew look deficient, nor automatically substitute for a regular
required skill. No live operational changes are permitted in this phase.

Existing stable `extended`, CarPlay/Assist, station availability actions,
and regular incident storage are not modified by this advisory preview.

## Phase 1b: opt-in single-candidate availability API probe

The authenticated integration already reads
`memberships/{membership_id}/combined_schedule` for the logged-in member's
per-station duty sensor. We have **not** established whether the API permits
reading a different, historically proposed member's schedule. Never infer a
whole-station eligible roster merely from the station's cached group membership
rows or a successful read for the logged-in member.

For a strictly bounded test of **one historical candidate** at an authorized
station/task, use Developer Tools -> Actions:

```yaml
action: fireservicerota.probe_fairness_availability
data:
  station_id: 194
  task_id: 7674
```

The service checks that the task is indexed for this station, intersects
historically proposed memberships from complete single-task audit records with
the active memberships of this station or its descendants in cached groups,
then chooses one reproducible *sample* from the latest matching proposal.
That selection is **not a fairness ranking or forecast**. If no match exists,
it returns a reason without making a request.

The response now also contains
`selected_candidate_relation_to_authenticated_user` with one of:
`same_authenticated_user`, `different_authenticated_user`, or
`not_verified`. It compares the cached active membership's `user_id`
with the already authenticated account's ID, **without returning either ID**.
When any ID is absent or conflicting across cached group entries, the relation
is `not_verified`. This does not change which historical candidate was
sampled and introduces **no additional GET requests**. A readable response
for a different user demonstrates that this particular GET was accepted by
the API; it still does not prove access to the entire station's current roster,
the person's operational availability or an authorization policy beyond this
request.

When a matching historical membership exists, the action makes **at most one
read-only authenticated GET** to that member's `combined_schedule` for the
current local calendar day, using the same day-window format as the existing
per-membership duty sensor.

Returned data is **anonymous**. The action reports only whether the
endpoint returned the expected `intervals` list and whether a valid interval
covers the current instant. When exactly one interval matches, the response now
includes `current_interval_field_presence`: a strict allowlist of boolean
checks indicating whether that interval contains a boolean `available` or
`active`, a list `skill_ids` or `assigned_function_ids`, and a recognized
`detailed_availability` object. If multiple intervals overlap, its value is
`null` rather than merging ambiguous person data. Only field **presence and
types** are returned: never the actual available/unavailable value, skill IDs,
assigned functions, or detailed schedule values. It does **not** return the selected member's
name, ID, actual available/unavailable state, duty type, detailed availability,
schedule timestamps, skill list or the raw API response, and it does not
store any schedule information. A failure is reported conservatively as
`api_schedule_unavailable_or_permission_denied`; it does not claim a
specific HTTP status or prove the person is unavailable.

Even a successful probe validates only API readability for **one member**.
It does not validate current task eligibility, coverage of all station members,
an expected incident crew, or BrandweerRooster's selection policy. A full
forecast would require explicitly authorized, scalable station-scoped reads,
current eligibility/skill evidence and out-of-sample validation before use.
The production `extended` branch and existing operational actions are
unchanged.

## Phase 1c: current aggregate appliance requirement (preferred over bulk person GET)

The official FireServiceRota API documents `GET
availability_requirements/{id}/schedule` for *current and projected
appliance statuses*. See
<https://fireservicerota.zendesk.com/hc/en-us/articles/360010210140-How-do-I-get-the-current-status-of-appliances-through-the-API>.
The day query must use midnight-aligned start/end times. Compared with
fetching dozens of individual members' schedules, a single availability
requirement represents the vehicle's aggregate staffing state.

**One-time, read-only diagnostic:**

```yaml
action: fireservicerota.probe_fairness_task_coverage
data:
  station_id: 194
  task_id: 7674
```

The service validates the account's active station membership, checks that the
task is indexed specifically for this station, and obtains the historical
staffing overview without any new requests. It looks for one **unique**
`availability_requirement_id` across completed, single-task, station-scoped
incidents. On Hardenberg TS, the previously inspected requirement ID is
`3690`. If zero or multiple IDs occur, the action returns an explicit reason
and **does not make any API request**. A historical requirement is never
silently assumed to be the current task configuration.

Only after that selection is unambiguous, one authenticated
`GET availability_requirements/{id}/schedule` is made for the current
calendar day. Its response requirement ID and task IDs are checked. The
current time must match **exactly one** interval. If a requirement ID or task
link disagrees, the API response has an unexpected structure, or intervals
overlap, the action refuses to claim usable coverage.

**Investigating task mapping:** Historical requirement `3690` was confirmed
for Hardenberg TS (`7674`) in 14 stored incident snapshots, but a first live
schedule probe returned `api_task_ids_do_not_match`. This can result from a
different task mapping or a requirement shared across multiple tasks. The
follow-up diagnostic includes `api_reported_task_ids` (a bounded, strictly
numeric list with no personal information),
`current_api_requested_task_included`, and
`current_api_task_mapping_status`:
`single_requested_task`, `shared_across_tasks`, `different_tasks`,
`task_ids_missing` or `task_ids_invalid`.

Current aggregate staffing data is returned only when the response
explicitly includes the requested task **and its full task scope can be
validated**. A single-task requirement remains task-scoped. A shared
requirement is now permitted **only at requirement level**, provided **all**
of its task IDs resolve to a unique name and the **same station** in the
already cached authenticated task index. Such results explicitly report
`current_api_task_mapping_status: shared_same_station_tasks_verified`,
`current_aggregate_scope:
shared_requirement_same_station_not_task_specific`, and
`resolved_requirement_tasks`. A verified Hardenberg shared requirement
`3690` lists `7674` (TS) and `7678` (TS-BT). This does **not** imply two
separate appliances, two independent sets of crew, or historical fairness
coverage for TS-BT. In the 17 currently retained fairness records, TS has 14
complete single-task incidents and TS-BT has none.

If any linked task is missing, ambiguous, belongs to another station, or has
an unsafe label, the action returns the previous
`api_requirement_shared_across_tasks` diagnostic **without any live counts**.
A missing or contradictory API task mapping likewise remains unverified. A
shared aggregate must never be added twice to a total by summing across
both tasks. The documented `GET /availability_requirements` list also
contains `task_ids`, but this preview still does not automatically make
a second request or broaden its scope.

It returns only **aggregate** per-skill values:
- `current_aggregate_service_level` and `current_aggregate_warning_level`
  (strict known enum labels).
- `current_requirement_configuration`, where present: current configured
  skill IDs and required counts, excluding memberships.
- `current_aggregate_skills`: known skill IDs with API-reported
  `minimum`, `buffer`, `assigned_count` and warning level.
- `current_aggregate_scope` tells you whether the measurements apply to a
  single task or to a requirement shared by tasks from the same station.
  This is *not* verified physical vehicle crew or person eligibility.
- `current_api_requirement_id_matches`, `current_api_task_ids_match`,
  and `current_configuration_matches_historical_skill_ids`, preserving
  **unknown** when the API omits a field.
- Historical skill context, including TS's supplementary aspirant position,
  clearly labelled as historical, not current eligibility.

No personal `available_memberships`, names, user IDs, individual candidate
responses, schedules, geolocation or credentials are returned or saved. No
BrandweerRooster writes, Home Assistant state changes, cache modifications,
forecast percentages or candidate ranking take place. API `assigned_count`
is an aggregated status count, not proof that those people actually rode a
vehicle or that a specific candidate can fill a current seat. If the current
requirement configuration differs from history, investigate before reusing
historical skill codes or crew assumptions.

This first probe remains diagnostic. Official operations and vehicle dispatch
procedures take precedence; a true person-level advisory would require
explicit authorization and evidence for live individual eligibility plus
a held-out prediction backtest.

## Phase 1d: read-only task P2000 vehicle filter probe

The BrandweerRooster task settings UI shows a task's GMS station/team
filters and the required/excluded terms in a P2000 incident message. For
Hardenberg TS-BT, task `7678`, a user screenshot confirms:
`GMS station=HARDBG`, `GMS team=b-ts`, **required P2000 term
`042340`**, excluded term `Intrekken`. This is a **task matching rule**,
not proof of which vehicle physically attended an incident.

The existing `GET /groups` cached task discovery is already available at
integration setup, but the current `task_index` deliberately contains only
task ID, name, station and group associations. Before changing or creating
a persistent vehicle map, a narrowly scoped API probe checks whether
the official `GET /tasks/{id}` returns the matching fields:

```yaml
action: fireservicerota.probe_task_p2000_mapping
data:
  station_id: 194
  task_id: 7678
```

The service refuses to query a task unless it is uniquely indexed for the
authenticated user's station. It inspects only related cached raw task
records and makes **at most one** read-only authenticated task GET. The
response is deliberately restricted to safely named, bounded field keys
and exact six-digit numerical values from *recognized required-message
term keys*. Excluded terms, capcodes, incident bodies, credential fields,
names, users, memberships, coordinates, arbitrary strings and all raw
responses are omitted. Returned terms are not saved to HA storage or sent
anywhere else.

Important response fields:

- `api_task_id_matches` and `api_task_station_scope_matches`: confirm that
  available current API identity/scope metadata agrees with the request.
- `cached_task_field_names` and `api_task_field_names`: safe schema
  diagnostics to identify a provider-specific P2000 filter key not yet
  supported by the narrow parser.
- `cached_required_p2000_vehicle_terms` and
  `api_required_p2000_vehicle_terms`: recognized numbers with explicit
  source distinction, and accompanying `*_required_term_paths`.
- `vehicle_number`, `vehicle_mapping_source`, `vehicle_mapping_status`:
  a candidate number is shown **only** when exactly one exact numeric
  required message term was recognized. A cached-only value can be stale,
  even if the live task API is readable.
- `operational_vehicle_dispatch_verified: false` always: an alarm filter
  does not independently verify vehicle arrival or assignment.

A task's separate **Audit Log** endpoint can expose historical changes:

`GET /api/v2/reporting/general_report/audit_log/data?object_ids=7678&object_type=task&order=desc&debug=false&cols=&page=2`

The `object_type=task` parameter selects *task-change history*, not a
current task snapshot. `page=2` is its second page. Because reports may
contain personal names and arbitrary change descriptions, this experiment
does **not** automatically read or echo task audit records. It can later be
used to verify when the required P2000 term changed (e.g. from a temporary
reserve-vehicle number) if the relevant records are available.

The screenshot and independent P2000 record for incident `3012389` support
the historical relationship between TS-BT and `042340`. A future general
task-to-vehicle map should be derived only from verified, current
per-task message filters and should not hardcode Hardenberg task IDs.

**Observed live result (25 October 2026):** `GET /tasks/7678` succeeded
but exposed only `alertable`, `description`, `group_ids`, `id`,
`name`, `order`, and `station_ids`. The cached `/groups` task copies
had exactly the same fields. The current matching term `042340` is
therefore **not exposed by either of these observed API payloads**.
Do not infer that the UI filter is absent, and do not hardcode a mapping.

### Historical task-change audit (one page, read only)

For the explicit task Audit Log URL provided by the user, a separate
bounded service can now inspect **one authenticated page** of historical
task changes, returning only numeric candidates from P2000-related
*required* filter changes:

```yaml
action: fireservicerota.probe_task_p2000_audit
data:
  station_id: 194
  task_id: 7678
  page: 2
```

To inspect the newest page, use `page: 1`. The service requires an
authenticated station-task match before one GET with
`object_ids=7678`, `object_type=task`, `order=desc`, and a page
between 1 and 5. There is no pagination loop. Records containing private
auditor identity, free-form change text, member details or credentials
are never returned or persisted. It displays only
`historical_numeric_p2000_terms`,
`filter_change_record_count`, and bounded examples with dates and
candidate six-digit terms (such as `042340`). An empty result only
means no matching audit change was recognized on that page; it does not
prove a term was never configured.

**Crucial:** the audit records are historical configuration changes, not
a current configuration snapshot. A historical term may represent an
old or new value, and neither occurrence proves a current vehicle
mapping. The current matching setting may live in an admin-only
resource not exposed through the public tasks API. Inspecting the
Browser Developer Tools Network requests made while opening the task
settings is the best way to identify the live API endpoint/field.
Never send browser authentication headers, cookies or private audit
payloads into issue trackers.

## Phase 1e: one-shot task webpage OAuth test

The authenticated BrandweerRooster browser page for
`/groups/194/tasks/7678?locale=nl` contains task-specific data directly in
its **server-rendered HTML**:

- Station: Hardenberg, task ID `7678` (`TS-BT`)
- GMS kazerne filter: `HARDBG`
- GMS ploeg soortcode filter: `b-ts`
- P2000 **required** incident-message term: `042340`
- P2000 excluded term: `Intrekken`
- Shared availability requirement: `3690` (tasks `7674`, `7678`)

This establishes the website's **current alert-matching configuration**,
not proof of a dispatched or physically deployed vehicle. The JSON
`GET /api/v2/tasks/7678` response did **not** expose these settings; the
task audit report on pages 1 and 2 returned zero records.

The HTML page normally uses a logged-in browser session. We must **not**
assume the integration's API OAuth bearer token can access that page.
The following deliberate diagnostic makes **at most one** GET to the exact
official HTTPS host with the existing OAuth bearer token and no browser
cookies, manual session copying, redirects, refresh retries or API writes:

```yaml
action: fireservicerota.probe_task_webpage_p2000
data:
  station_id: 194
  task_id: 7678
```

Safety and scope:

- The user must be a current member of the requested station, and the
  task must resolve **uniquely** to that station in the existing task index.
- The authentication token is sent only to the fixed
  `https://www.brandweerrooster.nl` origin. A different base URL is rejected.
- The web request uses `allow_redirects=False`, a 10-second timeout,
  and a hard 400 KB response cap. No raw HTML, tokens, cookies, personnel
  data, audit records or response bodies are returned or persisted.
- If OAuth fails or the web endpoint redirects, the action
  returns `oauth_not_authorized_for_webpage` or
  `redirect_to_web_session_or_other_page` and **stops**. It also reports
  `redirect_destination_type` as a *safe category*, never the raw
  Location URL or its query/credentials. This distinguishes a login
  redirect from a same-task canonical URL redirect without following either.
  This is a diagnostic result, not an invitation to inject browser cookies.
- On HTTP 200 HTML, the parser accepts only the explicit task-show page,
  a matching station breadcrumb, the exact task name from the authorized
  index, and specific rows in the `Algemeen` settings table. It exposes
  the two GMS filters and unambiguous whole six-digit *required* P2000
  message terms, never excluded terms or numbers in unrelated HTML.
- It does **not** modify the existing task index, persist a mapping,
  infer actual operational turnout, or change the live fairness computation.

Relevant response fields: `probe_status`, `http_status`,
`task_page_identity_verified`, `task_station_breadcrumb_verified`,
`gms_station_filter`, `gms_team_type_filter`,
`required_p2000_terms`, `vehicle_number`, and
`vehicle_mapping_status`. A single configured required term is a
**candidate matching term**, not independently verified appliance attendance.

**Observed result (25 October 2026):** The user ran the opt-in diagnostic
for station 194, task 7678. The server returned HTTP `302` and the
safely categorized Location was `sign_in_redirect`. This conclusively
distinguishes the observed response from a same-task canonical URL redirect:
the existing API OAuth bearer token cannot read this web page. Do **not**
retry with cookies, login credentials or forced redirects. The HTML
`042340` proof is user-supplied from an authenticated browser and not
readable by our current OAuth API client.

The official public documentation confirms that tasks can have required/
excluded P2000 message terms and GMS filters, but we have **not**
verified an authorized JSON endpoint that exposes these settings. Do not
speculate about its path or treat the bare task endpoint as the full settings
model. Request the appropriate read-only endpoint/fields from the provider,
or use a separate explicit, user-maintained task-to-P2000 mapping if
automated access cannot be provided. This diagnostic never populates
a mapping or affects historical fairness accounting.

## Phase 1f: bounded incident/P2000 task association (read only)

To work around missing current per-task P2000 required-filter data in the
JSON API, this experimental action correlates a single authorized station
task with six-digit `0xxxxx` terms observed in *historical incident bodies*.
This is a retrospective **association only**: the same message may mention
multiple units and stations. A correlation does **not** prove a task's
configured filter, which vehicle responded, whether a particular unit was
on scene, or which people crewed it.

The default action reads up to 25 closed incidents from the local
`IncidentStore.history` sensor snapshots (no API calls or persistence):

```yaml
action: fireservicerota.analyze_task_p2000_history
data:
  station_id: 194
  task_id: 7678
  limit: 25
```

Older incidents may no longer be retained because `HISTORY_LIMIT=25`.
For the **five incident IDs previously shown in the user's TS-BT task
website**, the same service also accepts a bounded explicit list:

```yaml
action: fireservicerota.analyze_task_p2000_history
data:
  station_id: 194
  task_id: 7678
  limit: 25
  incident_ids:
    - "3012389"
    - "2992516"
    - "2969366"
    - "2864999"
    - "2805609"
```

Each requested ID causes at most **one** authenticated
`GET /api/v2/incidents/<id>`; at most ten explicit IDs per invocation.
The service verifies that each response matches the requested incident ID,
deduplicates incident IDs across local and fetched history, and performs
no auditing, pagination, writes, background scans or cache updates.
A failed/unavailable ID is listed only by its numeric ID, never with
the private API response.

### Evidence grading

The action counts each six-digit term **once per distinct incident**.
It separately counts:

- **Single-task incidents**: one task ID in the incident; useful but still
  not definitive, because the P2000 message can mention several vehicles.
- **Single-task, single-term incidents**: one task and only one six-digit
  P2000 term in the incident body; stronger direct association.
- **Multi-task incidents**: shared incident-level evidence only.
  These NEVER independently establish a per-task mapping.
- Other incident examples for another currently indexed task in that
  station: useful *comparison*, not proof of missing task filters.

`candidate_terms` provides the top numeric terms, their unique incident
counts, single-task counts, up to eight supporting incident IDs and a
**heuristic evidence index**, not a statistically calibrated probability.
A `strong_historical_candidate_not_verified` requires at least three
supporting incidents, at least two single-task incidents, one single-task
single-term incident, at least 80% coverage of this task's usable incidents,
and a distinct top term. A `tentative_historical_candidate_not_verified`
only identifies a weaker, still unique association. Ambiguous ties, one
observation or exclusively multi-task evidence result in no proposed
`candidate_p2000_term`. No rule hardcodes `7678`, `042340`, a post
name or a vehicle type.

**Privacy and stability:** Only task ID/name, numeric terms, counts and
numeric incident IDs are returned. The action never includes raw
messages, addresses, names, members or responses, and never persists a
task-to-vehicle mapping. It does not modify historical fairness
profiles, forecast crews, or feed current operational decisions.
Current `task_index` is used only to validate station/task membership:
it is **not** proof of the task configuration at the incident date.

**Interpretation for the earlier TS-BT example:** in the five website
incident examples, `042340` appears five times; two of those incidents
list only TS-BT as a task, and one of those messages has just `042340`
as its six-digit term. This is compelling *historical co-occurrence*
compatible with the separately observed current website filter, but
still is **not** evidence of physical vehicle attendance or a general
API-backed config map. Verify using the HA action output before relying
on the local history or additional authenticated incident GETs.

## Phase 1g: post-wide P2000 candidate overview (read-only)

The one-task API experiment for Hardenberg TS-BT succeeded. In the user's
actual Home Assistant result, all five explicitly requested JSON API
incidents were readable, and the five TS-BT task incidents all contain
`042340`. Two incidents have only task `7678`, one incident has only
that single six-digit term, and the correlator therefore returned
`strong_historical_candidate_not_verified` with score `100`.
This score is **not a probability** and this step still does not prove an
appliance was on scene. The separately observed authenticated BWR website
form does prove that the task currently uses required term `042340`.

To generalize this without hardcoding station/task/vehicle mappings, a new
preview runs the same conservative single-task test for every currently
indexed task for one authorized station, capped at 40 tasks:

```yaml
action: fireservicerota.preview_station_task_p2000_history
data:
  station_id: 194
  limit: 25
  incident_ids:
    - "3012389"
    - "2992516"
    - "2969366"
    - "2864999"
    - "2805609"
```

Leave off `incident_ids` for a local-only analysis with **zero** provider
API calls. When supplied, the list is capped at ten explicit numeric IDs;
each ID permits exactly one existing OAuth JSON incident detail GET.
The action deduplicates observations by incident ID and returns a
bounded `task_results` list of task names/IDs, candidate terms,
single-vs-multi-task evidence counts and the top three code candidates.
No raw incident messages, location or personnel data leave the helper.
The output includes `tasks_omitted_due_to_limit` if more than 40 station
tasks are indexed.

**Cross-task conflicts are surfaced, not resolved by guessing:** if two
station tasks both obtain the same non-empty candidate code, both rows show
`candidate_conflict: true`,
`review_status: candidate_shared_by_multiple_station_tasks` and the
other relevant numeric task IDs. A distinct strong candidate is labeled
`strong_candidate_for_manual_verification`; none are persisted or
used to make operational assignment decisions.

Caveats: provider task JSON omits actual configured P2000 filters. A
station-wide correlation remains a retrospective co-occurrence diagnostic,
not an API-verified configuration, and current task-index station scope
is not a historical record of which tasks existed at the incident date.
The script does not modify staffing fairness evidence or station readiness.
