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
