# FireServiceRota Extended 1.2.0-rc.8

rc.8 re-enables strict Brandweer-only filtering for the online P2000 provider using the live-verified AlarmeringDroid schema.

## Live schema confirmation

Provider diagnostics from rc.5 through rc.7 confirmed that both top-level alerts and grouped subitems expose:

- `dienstid = "2"`
- `dienst = "Brandweer"`

This also confirmed why rc.4 failed: it compared `dienst` directly with `"2"`, while the numeric discipline id is supplied separately in `dienstid`.

## Filter behavior

rc.8 now:

- prefers `dienstid == "2"` as the authoritative Brandweer check;
- falls back to `dienst == "Brandweer"` only when `dienstid` is absent;
- applies the same check independently to the main alert and every grouped subitem;
- rejects items that explicitly belong to a different discipline;
- keeps the provider-level query restriction `diensten=["2"]`;
- keeps compact provider-schema diagnostics in `sensor.p2000_status` and records the active discipline-filter fields there for validation.

## Unchanged

- rc.7 Home Assistant lifecycle and persistent-match storage fixes remain unchanged.
- rc.3 confirmed/unresolved six-digit vehicle filtering remains active.
- Brandbase vehicle resolution remains unchanged.
- RTL-SDR, dashboards and local automations remain outside the integration.
