# Fairness roster scope: offline diagnostic test plan

This is an **optional development-only tool** on Draft PR #20. It never
connects to Home Assistant or BrandweerRooster and does not alter either
service. It runs the existing pure roster-scope inspector on a local JSON
fixture. No production HA installation is needed to test the pure logic.

## First run (safe synthetic example)

Create a temporary local JSON file, **outside the Git repository**, with
the exact three top-level keys shown below. These identifiers are invented:

```json
{
  "groups": [
    {
      "id": 194,
      "type": "station",
      "memberships": [
        {"id": 11, "user_id": 101, "status": "active"}
      ]
    }
  ],
  "own_membership_index": {"11": {}},
  "own_membership_duty": {"11": {}}
}
```

On a checkout of the development branch, run:

```sh
python scripts/run_fairness_roster_scope_offline.py --input /private/path/fixture.json --station-id 194
```

The tool prints aggregate JSON. A successful result **never proves** a
complete/current station roster, person's availability or task eligibility.
It does not fetch real data or authenticate; to inspect real data, an
explicitly authorized export or isolated test fixture still must be
provided by the operator. **Do not** upload real group payloads, member
identifiers, credentials, rosters, schedules or raw API responses to GitHub,
issues, PR comments, CI logs or this chat. Keep any sensitive input on a
controlled local system and securely dispose of it afterward.

## Guardrails

- No API calls or network use; inspect local files only.
- Maximum input size: 2 MB; strict JSON key allowlist.
- No raw payload printing; output consists only of fixed diagnostic fields.
- No writes to BrandweerRooster, Home Assistant or input files.
- The implementation is covered by synthetic regression tests.
- If true end-to-end Home Assistant service testing is later required,
  deploy only into a **separate** HA instance after explicit approval.
  Never merge PR #20 or install its branch on production HA for this test.

## Acceptance criteria before operational prediction

An authorized, fresh and complete station roster source; verified
person-to-membership association, task-specific skill/seat eligibility,
individual availability and timetable timestamps. A cached group snapshot
does not meet these requirements. 
