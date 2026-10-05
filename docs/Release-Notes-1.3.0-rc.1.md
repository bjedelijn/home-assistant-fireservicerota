# FireServiceRota Extended 1.3.0-rc.1

## Release candidate

1.3.0-rc.1 is the first release candidate for the 1.3.0 line. It is based on the field-tested 1.3.0-beta.5 code and is intended for final validation before promoting the same feature set to 1.3.0 stable.

## Highlights

### P2000 via ether (RTL-SDR / MQTT)

- Adds a local P2000 provider using the Cyberjunky P2000 RTL-SDR Home Assistant add-on.
- Receives Brandweer P2000 alerts from MQTT without internet polling delay.
- Keeps provider ids stable as `online` and `rtl`.
- Uses human-readable labels:
  - `P2000 online`
  - `P2000 via ether`
- Supports online only, ether only, or both providers.

### Online + ether practical-event grouping

- Groups equivalent online and ether observations into one practical P2000 event for diagnostics and dashboards.
- Keeps the original raw provider events available separately.
- Exposes:
  - `last_practical_event`
  - `recent_practical_events`
  - per-source timestamps and external ids
- Shows arrival differences between:
  - P2000 via ether
  - P2000 online
  - BrandweerRooster

### Source timing

- Uses Home Assistant observation time as the comparison basis.
- BrandweerRooster may arrive through WebSocket or REST.
- P2000 online is polling based.
- P2000 via ether is locally received and passed through MQTT.
- The online P2000 source timestamp can be minute-resolution and is therefore not treated as a precise latency measurement.

### Vehicle extraction and Brandbase resolution

- Corrects RTL-SDR six-digit unit parsing.
- Supports multiple unit numbers in one P2000 alert.
- Resolves confirmed units through the Brandbase vehicle cache where possible.
- Retains station/type/callsign metadata for dashboards and automations.

### Safer P2000 to BrandweerRooster correlation

- Tightens matching when P2000 coordinates are unavailable.
- A matching six-digit appliance number remains strong evidence.
- Explicit city/postcode/location information must agree with the BrandweerRooster incident.
- Generic incident wording alone can no longer create a match.
- Previously attached enrichment is revalidated automatically.
- False-positive P2000 enrichment and overlapping persistent matches are cleaned up without changing BrandweerRooster lifecycle data.

An anonymized field regression case during beta testing showed later RTL-SDR alerts from unrelated locations being attached to a target incident because they shared generic wording. The beta.5 matcher fix rejected those mismatched locations and automatically removed the stale units while retaining the correct online/ether observations.

## Field validation completed before RC.1

The beta line has been validated with live BrandweerRooster / P2000 traffic, including:

- identical online and ether alerts grouped correctly;
- single and multiple unit extraction;
- Brandbase vehicle resolution;
- BrandweerRooster WebSocket timing compared with P2000 arrival timing;
- local ether reception consistently arriving before or independently of the online polling source in observed cases;
- automatic cleanup of a confirmed false-positive cross-location match;
- correct retention of genuine anonymized matches after stricter matching.

## Compatibility

- Stable branch `extended` remains on 1.2.0 until 1.3.0 is promoted.
- Python dependency remains `pyfireservicerota==0.0.49`.
- Existing 1.2.0 P2000 online behavior remains supported.
- RTL-SDR functionality is optional and only used when selected in the integration options.

## RC validation focus

Before promoting to 1.3.0 stable, continue watching for:

- legitimate P2000 matches being rejected by the stricter location matcher;
- multi-vehicle and escalation scenarios;
- RTL alerts with incomplete location parsing;
- online/ether practical-event grouping across more incident types;
- any regression in persistent enrichment or incident lifecycle behavior.
