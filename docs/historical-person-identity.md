# Historical identity and optional name display

Status: agreed design requirements; implementation pending.

- Scope provider user IDs to the API connection; preserve membership and station IDs separately. Never use a name as a primary key. Do not infer identity from matching names.
- Store historical observations with incident, membership, station and user references where verified; preserve unknown references and original observations separately from later corrections.
- Resolve display names locally from authorized provider data. Default to anonymous display. Future options: first name, first name plus surname initial, full name. Allow station-specific display preferences.
- Historical name snapshots are separately opt-in, subject to retention and deletion controls. Disabling name retention removes stored snapshots without deleting statistical history. Missing historical names remain unknown; do not promise recovery for departed members.
- Names and personal identifiers must not enter diagnostic outputs, logs, telemetry or repository fixtures. Use synthetic test data. Anonymous presentation is pseudonymization, not a guarantee of anonymity.
- Expose named data only through explicitly enabled local surfaces; review HA entity visibility, recorder history and backups before enabling. Changing display mode must not require historical incident reimport.
- No hardcoded station IDs. Historical processing must remain independent of operational alerts and use the shared historical request budget.
- The future unified archive updater must handle identity enrichment and revisions automatically within authorized scope.
- Verify provider identity semantics, permissions, retention behavior and migration tests before release. These are design decisions, not claims about provider API guarantees.
