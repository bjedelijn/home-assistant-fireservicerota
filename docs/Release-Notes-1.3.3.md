# FireServiceRota Extended 1.3.3

FireServiceRota Extended 1.3.3 adds an **experimental, read-only incident fairness audit** and an incident-level station/group staffing inspection, based on the completed and tested PR #12. It builds on 1.3.2 and preserves the existing incident, availability, alerting and voice workflows.

## Added

### Read-only incident fairness analysis

A new Home Assistant action, `fireservicerota.analyze_incident_fairness`, inspects one BrandweerRooster incident on request and returns:

- Paginated JSON audit-log history, with completeness and pagination warnings.
- Timestamped *Suggestion based on fairness* records when present.
- Proposed candidates and their role-specific appearance counts (including commanders, drivers, firefighters and trainees when those roles are present in the data).
- Recorded incident responses and API skill assignments, without changing BrandweerRooster data.
- `staffing_by_group`, grouping recorded responses and skill assignments by membership and organization group, with unambiguous station resolution when available.
- `automatic_staffing` per group with `enabled`, `disabled` or `unknown` for **the incident being inspected**. A fairness proposal observed for an unambiguous single-station incident supports `enabled`; absence of a proposal does **not** prove that automatic staffing is disabled.

Example from **Developer Tools → Actions**:

```yaml
action: fireservicerota.analyze_incident_fairness
data:
  incident_id: "1234567"
  max_pages: 5
```

If an operator **already knows** the setting for a station in the incident, an optional temporary confirmation can be passed:

```yaml
action: fireservicerota.analyze_incident_fairness
data:
  incident_id: "1234567"
  max_pages: 5
  station_staffing_modes:
    "100": disabled
```

`100` is an illustrative station ID, not a configured default. This input is **not saved** and applies only to the returned analysis. Conflicts with observed proposal evidence are flagged instead of silently overridden.

### Multi-station foundations

- Membership-aware association avoids assuming that similarly named users or staff affiliated with more than one station represent one response.
- Proposals without an explicit task/station association are not arbitrarily attributed to a vehicle or to one of several responding stations.
- Regression tests cover multiple groups, ambiguous membership matches, conflicting confirmations and absent fairness suggestions.
- A design document for future historical comparisons and advisory prediction is available in `docs/incident-staffing-forecast-design.md`.

## Limitations and safety

- The audit-report endpoint works with the existing authenticated BrandweerRooster OAuth client but is not a documented public endpoint of `pyfireservicerota`. The service is **Netherlands/BrandweerRooster-only**, on demand, and **read-only**.
- Fairness suggestion appearance counts are **not fairness percentages**.
- API `dispatched` / `shown_up` status is **not independent proof** of physical vehicle attendance. A suggestion is not a confirmed crew.
- The presence/absence of proposals does not necessarily identify a post's permanent configuration: policy may differ by incident or vehicle.
- This release does **not** introduce historical fairness scoring or predictions, new dashboard popups, iPhone push actions, or CarPlay features. Those are future work.
- Do not publish private incident, staff, pager or response data in GitHub reports.

## Validation

Release preparation follows the repository checks for Python, JSON, YAML, Home Assistant imports and regression tests, security, CodeQL, HACS and Hassfest. The new analysis was also tested against real incidents in Home Assistant with automatic staffing both enabled and disabled.

## Compatibility and upgrade

- Requires `pyfireservicerota>=0.0.49`.
- No migration from 1.3.2 is required.
- Existing sensors, station availability actions, notification automations and integrations remain unchanged.
- Install **1.3.3** through HACS and restart Home Assistant when prompted.
- Home Assistant is an auxiliary information layer and must not replace the official alerting methods.
