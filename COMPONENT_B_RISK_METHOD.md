# Component B G2: scientific method and Python contract

## Scientific basis

NIOSH, *Criteria for a Recommended Standard: Occupational Exposure to Heat and Hot
Environments*, DHHS 2016-106, February 2016:
https://www.cdc.gov/niosh/docs/2016-106/pdfs/2016-106.pdf

Selected basis: section 1.1 (printed pp.2–4), section 8.1 (p.93), figures 8-1/8-2
(pp.94–95), and Table 3-2 (p.19, **2006** column). Both environmental and metabolic
heat use a one-hour time-weighted basis. For M in whole-body watts:

- Acclimatized REL = 56.7 − 11.5 log10(M), in °C WBGT.
- Unacclimatized RAL = 59.9 − 14.1 log10(M), in °C WBGT.
- Implemented clothing subset: conventional one-layer work clothing 0°C, cloth
  coveralls 0°C, double-layer cloth +3°C added to WBGT.

These criteria concern healthy, fit workers and reference-person assumptions.
They do not guarantee individual safety. The implementation does not extrapolate
beyond the plotted 116–580 W span or interpolate partial acclimatization.

NIOSH was selected because its equations, applicability and cited clothing subset
are publicly inspectable. ISO 7243 remains the existing A WBGT calculation basis;
no claim of implementing its complete proprietary assessment standard is made.
No current proprietary ACGIH tables were acquired or reconstructed.

## Implemented scope and evidence boundary

Version `1.0.0` is **simulation-only continuous-work screening**, not a complete
occupational heat-management program. It supports one worker, one task and one
zone over exactly 3600 seconds, with a constant evidenced numeric metabolic rate,
clothing ensemble and acclimatization state. Unknown acclimatization is insufficient;
partial acclimatization and work/rest or task/zone changes are unsupported. This
restriction is an implementation boundary, not a claim that NIOSH cannot assess
mixed activities. There is no rest-duration prescription or reassignment logic.

The caller supplies prior snapshots plus the current snapshot. Samples must advance
in time/version, share one instance/configuration, and have no gap greater than the
configured tick (limited to 1–10 seconds in this implementation). The 10-second
ceiling is an implementation sampling requirement, not a NIOSH exposure threshold.
All worker counters and relevant transition events are checked.
Trapezoidal integration computes the sampled WBGT TWA. This numerical convention
assumes linear interpolation; it cannot recover unobserved between-sample peaks.
The metabolic TWA equals the constant input rate. Cumulative work time never
substitutes for environmental history. These are retrospective windows, not forecasts.

`AssessmentBasis` binds evidence to worker/task/clothing-profile IDs. It requires
workload, clothing and population source descriptions and an explicit reference-
person applicability assertion. These are **caller-supplied synthetic scenario
assumptions**, not measurements, medical clearance or independently verified facts.
Generic `standard_workwear`, `long_sleeve_workwear` and `coveralls` are not mapped
automatically. No workload label is converted into watts. The default A tasks have
null rates, so default snapshots intentionally produce non-assessable outcomes.

Every snapshot is revalidated through A's existing API and domain models. The engine
checks simulation time, identity, units, quality, provenance, required WBGT channels
and the supplied calculated value against A's existing WBGT function. Measured or
estimated-WBGT inputs are outside this version. No A source or contract is changed.

## Python interface

```python
from heatshift_ai.risk import assess_worker

result = assess_worker(current_snapshot, worker_id,
                       history=prior_snapshots, basis=assessment_basis)
payload = result.model_dump(mode="json")
```

Inputs accept existing `SimulationSnapshot` objects or their JSON mappings. History
excludes current and must start exactly an hour earlier; no sorting, trimming,
gap-filling or measurement substitution is performed. No history is retained by the
function. HTTP, database access, n8n, and scheduling are deliberately absent.

The immutable output contains a deterministic content-derived assessment ID, A's
instance/state identifiers, simulated timestamp, current and averaged WBGT, rate,
clothing adjustment, reference limit, evidence, outcome, explanation and limitations.
Malformed input has null unavailable context, not fabricated IDs or timestamps.
An issue names the first failed prerequisite; null limit means no supported comparison.
`WITHIN_APPLICABLE_LIMIT` means effective sampled TWA <= the unrounded applicable
reference limit only; `EXCEEDS_APPLICABLE_LIMIT` means >. Neither authorizes work.
Invalid/missing inputs return `INSUFFICIENT_DATA`; unsupported scope returns
`NOT_ASSESSABLE`. Outputs must retain their provenance and limitations downstream.

## Scientific verification design

Tests derive reference limits independently using 50-digit Decimal natural logarithms,
then compare production `math.log10` results for six rates and both populations.
The 200 W REL case gives 30.23815504986422°C; equality and ±0.0000001°C are tested.
An analytic linear WBGT profile from 26 to 30°C has an hourly average of 28°C.
Clothing tests independently use the cited table values, including a changed outcome.

The publication's p.4 graphical 348.9 W example (~27.8°C REL/~25°C RAL) does not
numerically equal its p.93 equations. This implementation explicitly selects the
published equations; it does **not** claim to reproduce that graphical approximation.
Equation arithmetic and sampled integration verification are not field validation,
medical validation, or verification of a caller's workload/clothing assumptions.

## Prerequisites and delivery status

G1 previously ended PARTIAL because remote access was unavailable. During G2,
47 baseline source/test/configuration/contract files were matched by Git blob hash
to GitHub commit `31c2b3b146324888a6581558f739a23ab26025bd`.
C1/C2 have not been completed. G2 uses the pre-existing Python environment; execution
results and exact commands are recorded separately in COMPONENT_B_G2_VERIFICATION.md.
No cloud availability, physical measurements or multi-process state support is claimed.

## Corrective extension — 2026-10-24

`heatshift_ai.prospective.assess_proposed_assignment` adds explicit simulated one-hour
future-assignment screening. It reuses G2's observation validation, trapezoidal
TWA, clothing adjustments and reference-limit calculation. The retrospective
interface and restrictions above are preserved. Required forecasts, exact-state
binding, candidate factors and prior-exposure assumptions are documented in
[the corrective report](COMPONENT_B_CORRECTIVE_VERIFICATION.md). A future forecast
is never presented as observed work history or a guarantee of future safety.
