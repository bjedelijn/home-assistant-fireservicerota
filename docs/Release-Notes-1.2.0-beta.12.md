# Release notes - 1.2.0-beta.12

## Discipline-aware P2000 incident scaling

`1.2.0-beta.12` separates Dutch P2000 incident scales by discipline instead
of treating every "Middel" or "Groot" label as a fire escalation.

### Independent scales

The enrichment now exposes:

- `highest_fire_scale`
- `highest_hv_scale`
- `highest_ibgs_scale`
- `highest_grip`

The existing `highest_fire_scale` and `highest_grip` keys remain unchanged
for backwards compatibility.

### Fire

Explicit forms such as Kleine/Middel/Grote/Zeer grote BR or brand are
normalized to:

- `small_fire`
- `medium_fire`
- `large_fire`
- `very_large_fire`

### Hulpverlening (HV)

Explicit forms such as Kleine/Middel/Grote/Zeer grote HV or hulpverlening are
normalized independently to:

- `small_hv`
- `medium_hv`
- `large_hv`
- `very_large_hv`

A message containing `Middel HV` therefore no longer has any relationship to
`highest_fire_scale`.

### Gevaarlijke stoffen

Explicit IBGS scaling is normalized independently. The historical/alternate
abbreviations OGS and IGS are accepted as aliases, but the normalized output
uses IBGS:

- `small_ibgs`
- `medium_ibgs`
- `large_ibgs`
- `very_large_ibgs`

Incident descriptions such as gas leaks or hazardous-material wording without
an explicit scale are not guessed into an IBGS level.

### GRIP

GRIP 1 through 4 remain a separate escalation axis. A practical incident can
therefore have, for example, both `highest_hv_scale: large_hv` and
`highest_grip: grip_1`.

### Generic "Middel incident"

Generic labels or capcode descriptions such as `Infocode Middel incident`
are deliberately not mapped to fire, HV or IBGS. The discipline must be
explicitly present in the P2000 message text.

### Escalation detection

Explicit "small" classifications are retained in the timeline and highest-scale
fields, but do not by themselves set `escalation_detected: true`. Middel or
higher, or any GRIP level, does.
