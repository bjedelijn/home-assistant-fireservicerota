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

## Mobile-device privacy

For BrandweerRooster Netherlands, 1.2.0-rc.1 exposes only a selected, dashboard-safe subset of mobile-device diagnostics.

Useful fields can include platform/model, OS/app version, enabled state, `alert_notifications_enabled`, network type, battery level when supplied and `last_heartbeat_at`.

The integration deliberately does **not** expose mobile push tokens, UUIDs, IMEI, serial identifiers or live-update tokens through the Home Assistant sensor. The mobile-device request also avoids the normal upstream raw-response debug path so those credentials are not copied into normal integration debug logging.

Do not confuse per-device `alert_notifications_enabled` with the optional legacy user-level `do_not_disturb` field. They are modeled separately.

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

## Write-capable controls

Some integration features can write to BrandweerRooster / FireServiceRota:

- incident-response switches can submit acknowledged/rejected responses;
- pager-message services can send a pager message.

Incident-response switches are disabled by default for newly created entity-registry entries in 1.2.0-rc.1. Existing Home Assistant registry choices are not forcibly changed.

Duty/availability remains read-only in 1.2.0-rc.1. Extended does not create paraat/niet-paraat planning exceptions.

The local incident lifecycle services `fireservicerota.mark_incident_closed` and `fireservicerota.reopen_incident` change only Extended's local operational view; they do not close/reopen an incident in BrandweerRooster.

Shared/public dashboard examples intentionally omit response buttons. If you deliberately add write controls to a dashboard, use confirmation and appropriate dashboard access controls.

## Notification examples

The public documentation contains generic iPhone examples. Replace placeholder notifier IDs locally.

Telegram/location-map examples are intentionally not included in the public documentation because real-world implementations often combine incident text, live coordinates, routes and installation-specific identifiers in one payload.

## Home Assistant is not the primary alert channel

Do not rely on Home Assistant, Wi-Fi, a dashboard, push notification or TTS as the only emergency alerting path. Official pager/app/P2000 or other approved alerting channels remain leading.
