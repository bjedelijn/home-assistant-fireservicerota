# Privacy and safety

FireServiceRota / BrandweerRooster incident data can contain operational or location-related information. Treat dashboards, logs, screenshots, notification payloads and issue reports accordingly.

## Do not publish private incident data in issues

Before posting a GitHub issue, remove or replace data such as:

- private/home addresses;
- exact incident coordinates when not needed to reproduce a bug;
- names of private persons;
- personal mobile notifier/entity names;
- account, membership and device identifiers that are not required for diagnosis;
- authentication information, tokens and passwords;
- full historic incident exports;
- screenshots that expose unrelated Home Assistant household information.

## Station and organization data

Some station/task/function names are part of normal BrandweerRooster organization configuration. When reporting a generic integration bug, prefer replacing these with placeholders unless the exact API relationship is relevant to the bug.

For example:

```text
Example Station
Example Task
Example Skill
membership_id: 12345
```

## Logs

Debug logs can be useful, but inspect them before publishing. The integration can expose incident IDs, task IDs, station metadata, response data and staffing information in debug output.

## Notification examples

The public documentation contains generic iPhone examples. Replace placeholder notifier IDs locally.

Telegram/location-map examples are intentionally not included in the public documentation because real-world implementations often combine incident text, live coordinates, routes and installation-specific identifiers in one payload.

## Home Assistant is not the primary alert channel

Do not rely on Home Assistant, Wi-Fi, a dashboard, push notification or TTS as the only emergency alerting path. Official pager/app/P2000 or other approved alerting channels remain leading.
