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


### Malformed intervals fail closed

The single-person read-only schedule probe refuses a positive unique-current
interval claim if **any** of up to 500 returned intervals has malformed,
missing, timezone-naive or reversed timestamps. Invalid entries might overlap
the current time, so silently skipping them would create false confidence.
The diagnostic reports only an invalid interval count, never raw times or
private availability. It still does not certify person-level operational
availability or the complete station pool.


### Current aggregate availability: invalid intervals must fail closed

The task-aggregate (including same-station shared TS/TS-BT) schedule probe now
rejects a positive current-coverage claim if **any** interval is malformed,
has missing or naive timestamps, or has a reversed range. A malformed interval
could also overlap the checked time and therefore cannot be ignored. The
read-only diagnostic provides only the number of invalid intervals and the
`invalid_schedule_intervals_cannot_verify_current` status; it never returns
member schedules, identities or a forecast. The comparison timestamp must
be timezone-aware. Current individual eligibility remains **unverified**.


### Duplicate membership identity fail-closed guard

A person can hold more than one BrandweerRooster membership. The pure scenario
solver now requires an explicitly linked `user_id` for **every** supplied
membership. If user identity is missing, or if the same user appears with
multiple membership IDs, it refuses to evaluate the scenario rather than
incorrectly assigning one firefighter to two positions. A future reviewed
adapter may safely consolidate memberships per user when it can validate
availability and skills per station/task; the pure helper does not guess.
No member IDs or names are included by default.


### Explicit timestamp freshness gate for scenario inputs

The pure scenario solver now **requires** a timezone-aware `evaluated_at`
timestamp supplied by its caller. It parses the timezone-aware snapshot
`observed_at` and refuses observations older than five minutes, over thirty
seconds in the future, malformed timestamps or absent/naive evaluation time.
This does not independently verify the caller's clock or the remote
observation provenance; production callers still require a reviewed,
authorized station-wide source. No live request, fairness ranking or
predicted lineup is introduced.


### Task-configuration timestamp freshness

A recent personnel snapshot alone is insufficient. The pure seat scenario
helper additionally requires a separate timezone-aware `observed_at` on the
verified task requirement configuration. If absent, malformed, more than five
minutes old or over thirty seconds in the future, it refuses to evaluate.
These conservative development thresholds do not establish the reliability of
the task API source or the caller's clock and are not intended as immutable
operational SLAs. This feature remains disconnected from live HA services.


## Existing authenticated-client scope audit

A review of the current integration's `FireServiceRotaClient` found that
`membership_index` contains **only the currently authenticated user's**
active memberships. `_async_update_membership_duty` iterates that index
and populates `membership_duty`; it is therefore **not a station roster**.
A successful duty refresh must never be promoted to a full-station candidate
snapshot. No existing method certifies a complete authorized station-wide
roster, its individual skills, and per-person current availability.

The new pure unregistered `fairness_roster_scope.assess_candidate_roster_source`
reports aggregate cached group and own-membership counts, identity-link
ambiguities, and this limitation. It does **not** return people or mark
the station roster as complete, even if all *cached* rows are covered.
The next implementation decision requires verifying a permitted current
station-wide API source and its completeness semantics, not looping through
historical candidate IDs. Avoid unauthorized broad person/schedule requests.


### On-demand Home Assistant cache-only diagnostic (experimental)

The draft development branch exposes
`fireservicerota.inspect_fairness_roster_scope` with `station_id` and
optional `entry_id`. It checks that the station belongs to the configured
account and only analyzes data *already in memory*:
`client.groups`, `client.membership_index`, and `client.membership_duty`.
It performs no new BrandweerRooster GET or POST, does not enumerate
individual schedule endpoints, and persists nothing. Output is fixed
aggregate counts and fail-closed verification statuses; never raw names,
identifiers, time intervals or member availability.

This service is only present in PR #20 development code. It will not appear
in the existing stable Home Assistant installation unless that code is
deliberately deployed after separate approval. Do not merge or install into
production just to collect a diagnosis.


### Bounded cache-only diagnostic inputs

The development-only roster source inspector now rejects missing/invalid
`groups` structures, more than 250 discovered groups, more than 500
memberships per group, more than 5,000 membership rows in total, or over 500
own memberships/duty entries. On rejection it returns a fixed reason and
**no partial member counts** (null rather than zero). These are prototype
diagnostic safety bounds, not operational assumptions about station size.
No additional API call or persistence is involved.


### Cached memberships versus distinct user diagnostics

The cache-only service now distinguishes a **membership count** from a
**distinct linked user count**. A single user may have multiple station/team
memberships; repeated rows for the same membership across cached groups are
deduplicated. Distinct-user and multiple-membership counts are returned only
when every included active membership has one unambiguous user link, there are
no malformed related membership rows, and the station group is found.
Otherwise these numbers are `null` rather than an unsafe guess. Even fully
linked *cached* identities do not establish a current, complete, authorized
station roster, availability or staffing prediction.


### Station-group versus related-team memberships

The diagnostic now reports separate, deduplicated counts for active
memberships directly inside the station group versus memberships present
only in associated child/related teams. The latter must **never** be promoted
to verified firefighters of the station. When the direct station group is
missing, direct-station counts are `null` (unknown), not zero. In addition,
the diagnostic reports how many of the authenticated user's memberships
appear directly in the station group. These remain cached counts, not
a complete current station roster, a permission grant, or operational
staffing evidence. No personal identifiers are returned.


### Ambiguous station group responses

The cached diagnostic refuses to combine two group records with the same
requested station ID, including duplicated identical records. An ID that
is present but labeled with a non-station group type is also rejected.
Instead of unioning potentially conflicting membership lists, the result
returns a fixed rejection status with null counts and no identities.
This does not validate the freshness or completeness of a single group.


### Conflicting group membership statuses

The cache-only diagnostic now refuses to interpret a group snapshot where
the same membership has contradictory statuses in a station and related team
group. Missing or unrecognized status values also cause a fixed fail-closed
result with null counts, rather than being silently counted as inactive.
Only recognized active, inactive and pending statuses are accepted for this
prototype; provider status vocabulary must be verified before live use.
The diagnostic still makes no additional API calls, returns no identities,
and never certifies a full live candidate pool.


### Malformed group rows and bounded identifiers

The cache-only inspection rejects non-object group entries instead of
silently ignoring potentially missing station records. Numeric identifiers
are bounded to 18 ASCII digits to avoid oversized-input conversion errors.
Fixed rejection responses contain neither the malformed group content nor
partial roster counts. The authorized complete live roster is still
unverified, and no additional API requests are made.


### Distinct people, not extra memberships

A person can have one direct station membership and a *different* linked
team membership. The cache-only diagnostic now separately reports distinct
linked users belonging to the direct station group, and users appearing
**only** in related groups, if all user links are unambiguous. Related-only
memberships of people already in the station do not inflate the related-only
person count. This is an anonymous cached structural observation, not proof
of full roster coverage or task eligibility; unknown identity or missing
station group causes null person counts.
