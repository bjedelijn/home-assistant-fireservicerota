# Incident staffing insights and forecast design

This is a design note for a **read-only, optional** feature of FireServiceRota
Extended. It does not affect response, alerting, or vehicle dispatch. Treat all
prediction outputs as advisory and never as operational proof of staffing.

## Identifiers and data sources

- `incident_id`: one BrandweerRooster incident record.
- `incident_group`: relate several incident records if the API explicitly
  provides a common incident group; never join incidents by time alone.
- `task_id`: vehicle or operational task. One incident may have several tasks.
- `group_id`: responding affiliation; may refer to a team or organizational
  group rather than directly to a station.
- `station_id`: resolve only from unambiguous group/task metadata.
- `membership_id`: join an individual response and skill assignment to the
  correct group; a `user_id` may have several station memberships.
- `skill_id`: use dynamic skill metadata; do not hard-code Dutch function
  identifiers or assume a single skill corresponds to a particular vehicle.

Read `GET /api/v2/incidents/{id}` for status, assignments and skill
requirements; use the JSON audit report to inspect changes and the actual
logged `Suggestion based on fairness` entries. The audit report path is not
verified as a stable documented public API. Only access information that the
authenticated account is authorized to see.

## Three distinct staffing views

1. **Live response state:** what is available, alerted, acknowledged or
   rejected; current skill requirements and assigned roles.
2. **Algorithm proposal:** timestamped snapshots of which member was
   suggested for each role. A proposal may change multiple times while the
   response window is open. Do not present it as a confirmed vehicle crew.
3. **Post-incident truth:** reported `dispatched`, `shown_up`, `no_show`,
   together with any verified correction to actual vehicle occupancy.
   Reported `dispatched` does not independently prove physical attendance.

Do not attribute an audit fairness proposal to a particular station if it
contains only names and roles without a unique station/task reference.
Incomplete or ambiguous mappings must be labelled as such.

## Proposed implementation stages

### 1. On-demand incident inspection (available on feature branch)

- Home Assistant action `fireservicerota.analyze_incident_fairness`.
- OAuth-authenticated read-only audit pages, role proposal summaries and
  recorded incident status.
- `staffing_by_group`: cross-group recorded responses and skills joined
  on membership ID, with station hierarchy resolved where possible.
- `automatic_staffing` within each response group has one of `enabled`,
  `disabled`, `unknown`, scoped to **this incident only**. Observed audit
  fairness proposals can indicate `enabled` when the incident record
  unambiguously contains one responding station. No proposals alone never
  proves the feature was disabled.
- Optional action data `station_staffing_modes` supplies an explicit
  operator confirmation per station ID, e.g. `{'3853': disabled}`. This
  confirmation is **not persisted**, does not configure BrandweerRooster,
  and applies only to the currently examined incident. Conflicts between
  a confirmation and observed proposals are surfaced as warnings. Actual
  server-side policy flags cannot yet be verified from the API.
  BrandweerRooster can enable proposals per vehicle/incident type, so
  future configuration discovery must preserve that specificity.
- Anonymized test fixtures: one group, two groups, shared user across
  memberships, unknown groups and ambiguous assignments.

### 2. Incident-time snapshots (future, opt-in)

- Capture a compact snapshot at live WebSocket alert, key response changes
  and the final response window. Use the existing incident-store refresh
  mechanism; do not create a parallel high-frequency poller.
- Track source and timestamp of each observation. Distinguish genuinely
  observed historical state from a state fetched retrospectively.
- Include `incident_group`, `task_id`, `group_id`, `membership_id` and
  `skill_id` where supplied.
- Apply configurable retention and minimize personal details stored in
  Home Assistant's recorder or persistent store.

### 3. Historical comparison (future)

- Compare multiple incidents **per station, task and skill**: alerts,
  acknowledged responses, fairness proposals, API-dispatched,
  API-shown-up, no-shows and verified turnout.
- Avoid counting each repeated fairness proposal as a separate turnout.
  One incident may generate multiple candidate lineups.
- Flag uncorrected reports, missing group mappings and history gaps.
- Preserve the distinction between 'proposal appearances' and percentage
  of actual dispatches.

### 4. Indicative future lineup simulation (future)

- Check the selected algorithm/policy and availability priorities.
- Use eligible members, memberships, duties, available skill coverage and
  historic **corrected** turnout records as the candidate pool.
- For the new fairness algorithm, compare recent real plus virtual dispatches
  against alerts and examine role-specific turnout rates.
- Account for role overlap and vehicle-level staffing requirements without
  counting a multi-skilled responder twice.
- Where available, include boost/stop settings and policy overrides. If a
  required input cannot be read, report reduced confidence rather than
  inventing a ranking.
- Return a **scenario**: eligible candidates per role, explanation, missing
  data and confidence — never a definitive dispatch plan.

## Safety and acceptance criteria

- No write calls, no automatic response/dispatch decisions.
- Multi-station/vehicle association must follow explicit API relationships.
- Unresolved personnel or station joins must stay unresolved.
- Changes to incidents or local staff records require authorized review.
- Do not commit live incidents, names, rosters, capcodes, or tokens to this
  public repository.
- Keep `extended` untouched until CI and Home Assistant field testing pass.


## Phase 2 groundwork: verified-slot feasibility (development only)

`fairness_scenario.evaluate_verified_seat_scenario` is a pure, unregistered
helper with anonymous tests. It checks whether **explicitly supplied**
currently available, eligible memberships can cover *current* required skill
slots, with unique memberships and task/station scope. Repeat a skill slot for
requirements such as WTS's two chauffeur positions. Supplemental aspirant
qualifications never substitute automatically for a regular crew skill.

This is **not wired to Home Assistant actions**, makes no API calls and never
calculates fairness rankings or a predicted lineup. Provenance flags in test
inputs are caller attestations, not independent verification. Until a complete,
authorized, fresh per-member availability/eligibility source and verified
current task configuration are validated, a caller must refuse to set those
flags and no operational or predictive display should use this helper.

Tests intentionally use synthetic memberships. By default the helper returns
only aggregate slot coverage; an explicitly opted-in developer scenario can
include membership IDs. That illustrative assignment is not a prediction.


### Distinct seat model must be verified, not inferred from skill totals

BrandweerRooster `crew_requirements[].skills[].required` may describe
**overlapping skill coverage**. Do not sum these counts into a number of
unique seats and do not infer a fixed crew layout from a historic fairness
proposal. The pure helper now rejects task inputs unless they explicitly
attest `coverage_model: explicit_distinct_seat_slots` and
`slot_model_verified: true`. This is a deliberate interface guard, **not**
independent verification: only a future reviewed adapter backed by task
configuration proving distinct positions may set these fields.

For example, the historic Hardenberg WTS requirement Bev 1, Ch 2,
Ms 4 cannot automatically be treated as seven unique positions, even
though two separate chauffeur candidates were actually observed.
The WTS regression test uses only synthetic *explicit distinct seat*
definitions. Do not reuse API aggregate requirements as this model.


## Presentation label policy: task ID versus vehicle callsign

The fairness engine must key all evidence by `station_id` and `task_id`.
Neither a task ID nor a task name is a callsign. In Home Assistant a verified
current association can be displayed as `TS 04-2330` instead of task ID
`7674`. The example numbers are illustrative and **not hardcoded**.

`fairness_vehicle_display.describe_task_vehicle` is a pure, currently
unregistered helper with synthetic tests. A future reviewed adapter must
independently verify that a **current, unique, station-scoped** task/vehicle
association exists. The P2000 required incident-message term by itself is
insufficient: a matching filter does not prove physical vehicle dispatch.
If no authoritative mapping is available, return the task label `TS`
rather than assume `04-2330`.

If there is one active station- and original-vehicle-specific replacement
in `ReplacementVehicleStore`, show its callsign while retaining the
original separately. In historical views use the event-time replacement
mapping rather than today's active mapping. Ambiguous mappings or active
replacement conflicts fail closed. The presentation does **not** change
fairness evidence, the source P2000 message or operational dispatch.


### Bounded matching complexity (regression hardening)

The pure scenario helper uses deterministic augmenting-path bipartite matching
rather than enumerating permutations of personnel. It can evaluate up to 32
distinct verified slots and 100 candidate memberships without exponential
search; synthetic tests cover multi-skilled reassignment, full-sized candidate
sets and insufficient unique candidates. This remains a feasibility check,
not a ranking or predicted deployment. Missing current verified individual
availability, skill eligibility, or distinct seat provenance still fails closed.


### Availability probe interval ambiguity hardening

The one-candidate schedule probe now returns
`ambiguous_overlapping_current_intervals` when more than one current interval
matches; it does not merge the private values or infer availability. A
timezone-naive comparison time is rejected and a schedule with more than
500 intervals fails closed instead of silently truncating. No current member
availability is published, no complete station eligibility is inferred and
no operational lineup prediction is produced.


## Readiness gate: evidence is not a verified lineup

The pure, unregistered `fairness_readiness.summarize_forecast_readiness`
compares three **already sanitized** sources for one station/task:
historical proposals, one-candidate schedule structure, and current aggregate
coverage. It returns only missing evidence categories and never exposes names,
memberships, schedules, ranks or proposed vehicle crew.

All three may be observable while a forecast is **still blocked**:
one successfully readable candidate is not the full station's available
candidate pool; aggregate warning/skill counts are not person-specific,
and task skill requirements need verified *distinct seat* interpretation.
A held-out prediction backtest is also required. The helper makes no live
API calls and cannot itself establish source authorization or freshness.


### Current availability-requirement probe contract

The readiness gate now matches the actual sanitized diagnostic keys emitted by
`summarize_task_requirement_schedule`. For a single task, scope is
`single_task_requirement` and `current_api_task_ids_match=True`. For a
multi-task requirement belonging to the same station (e.g. TS and TS-BT),
scope is `shared_requirement_same_station_not_task_specific`, the exact
single-task equality flag is **False**, and the separately resolved
`shared_task_station_scope_verified=True` plus
`current_api_requested_task_included=True` are needed. Require a positive
requirement-ID match, readable interval/status, and aggregate skill inspection
before marking aggregate diagnostic evidence observed.

Shared aggregate evidence must NEVER be called verified exclusive staffing
for a single vehicle; no person-level roster or predicted lineup follows.
