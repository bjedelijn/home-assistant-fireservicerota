# FireServiceRota Extended 1.2.0-rc.6

rc.6 fixes the Home Assistant lifecycle handling of the continuous P2000 enrichment loop.

## Problem confirmed from live Home Assistant logs

The P2000 manager used `hass.async_create_task()` for its lifetime polling loop. Because the task was created during config-entry setup and never completes by design, Home Assistant treated it as setup work and waited for the bootstrap timeout before continuing.

Observed live symptoms:
- Home Assistant reported `P2000EnrichmentManager._run()` still running during the final-writes shutdown stage.
- On startup Home Assistant reported `Setup timed out for bootstrap waiting on ... P2000EnrichmentManager._run()`.
- Home Assistant initialized only after roughly 358 seconds.

## Fix

- Start the continuous P2000 loop with `ConfigEntry.async_create_background_task()`.
- The task is now explicitly associated with the config-entry lifecycle.
- Background polling no longer blocks Home Assistant startup completion.
- Home Assistant can automatically cancel the task during shutdown/unload.
- The existing explicit `P2000EnrichmentManager.async_stop()` remains in place as an idempotent cleanup path.

## Unchanged from rc.5

- Nationwide online query remains restricted to `diensten=["2"]`.
- The overly strict rc.4 per-record `dienst == 2` filter remains disabled.
- Compact provider-schema diagnostics remain available in `sensor.p2000_status`.
- rc.3 confirmed/unresolved vehicle filtering remains active.
- RTL-SDR, dashboards and local automations remain outside the integration.
