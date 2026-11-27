# Read-only BWR task and P2000 diagnostics

This development-only extension adds task context to the existing Home Assistant
`fireservicerota.get_incident_vehicle_evidence` action.

Example (use your own incident ID **locally in Home Assistant only**):

```yaml
action: fireservicerota.get_incident_vehicle_evidence
data:
  incident_id: 1234567
```

The response now includes:

- `tasks.rest`: incident task IDs, station-scoped task labels from currently cached
  BWR discovery, and whether crew requirement groups were present.
- `tasks.websocket`: equivalent inspection only when the WebSocket incident ID
  matches the requested incident.
- `p2000`: any previously correlated P2000 alerts retained by the existing
  manager, giving source names and six-digit alerted-unit identifiers.
  If the correlation has expired or was never established,
  `no_retained_correlation` is returned.

This does **not** infer a physical appliance from a task ID and does not
prove crew membership, turnout or replacement vehicle usage. It never
automatically clears or changes vehicle replacements.

Only fixed allow-listed operational fields are returned. No incident location,
raw alert messages, names, membership IDs, or responses are returned.
Repository fixtures must remain synthetic; do not paste real operational
or personal evidence into GitHub issues, commits, PRs or Actions logs.

The fairness engine must be evaluated separately against incident-specific
task requirements and historical fairness proposals. Reported attendance,
initial proposals and confirmed physical turnout are different concepts.
