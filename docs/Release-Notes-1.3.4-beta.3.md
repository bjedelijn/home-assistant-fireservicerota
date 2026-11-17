# FireServiceRota Extended 1.3.4-beta.3

**Prerelease candidate, 17 November 2026. Stable v1.3.3 is unchanged.**

## What's new since beta.2

- Manual Home Assistant incident closures are journalled in private per-entry
  `.storage` and survive integration reloads, restarts, and historic rolling
  history loss. A local reopen removes the protected closure. No provider-side
  incident closure is sent.
- Old restored incidents with explicit open lifecycle are no longer treated
  as active solely because of stale state.
- CarPlay availability returns `next_scheduled_unavailable_at` when the
  future non-paraat boundary is confirmed by complete roster evidence.
  This is separate from the end time of the temporary availability override.
- Documented guarded per-post incident response scripts for two stations
  and corresponding Assist prompt / spoken-feedback automations.
  **Scripts, Assist and CarPlay configuration are examples only**, not bundled
  executable user automations; they must be deliberately configured.
- Synthetic tests for persistence and schedule safety; GitHub CI verifies
  code, security, HACS and Home Assistant metadata.

## Upgrade / testing

- Back up Home Assistant before updating; on a one-instance setup, keep a
  rollback copy of the previous integration version and YAML packages.
- Home Assistant package files are maintained by the user, **not updated
  automatically** with the integration.
- Test CarPlay's no-incident blocking first; real response switches submit
  actual responses to BrandweerRooster and remain guarded/disabled by default.
- Do not describe a response as accepted server-side without read-back;
  verify official BrandweerRooster status where appropriate.

## Related documentation

- [Incident automations](Incident-Automations.md)
- [CarPlay / Siri](CarPlay-Siri-Availability.md)
- [Per-station guarded response example](examples/CarPlay-Per-Station-Incident-Response.yaml)
- [Station availability example](examples/Station-Availability-CarPlay-Package.yaml)
- [Incident lifecycle](Incident-Lifecycle-and-History.md)
