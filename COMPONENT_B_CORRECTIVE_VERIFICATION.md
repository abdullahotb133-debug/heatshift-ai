# Pre-G5 corrective action — implementation and verification

> Subsequent repository review, 2026-10-24: the former GitHub write denial is resolved;
> all 529 tests passed again. See [the final review](PRE_G5_REPOSITORY_REVIEW.md) for
> current delivery, evidence and readiness. The historical execution and safety limits
> below are preserved; this update does not upgrade the corrective task to PASS.

Date: 2026-10-24. Status: **PARTIAL**.
Readiness: **CONDITIONALLY READY for controlled simulated proposal review;
BLOCKED for unattended safety-command orchestration**.

The prospective candidate-assessment and planning conflicts are repaired within
the documented scope. A fully resolved safe intervention is still not established:
the affected worker's residual exposure/recovery and enforcement of the forecast
horizon require separately verified controls. This distinction prevents software
test success from becoming a claim of personnel safety.

## Baseline and confirmed root causes

Freshly inspected remote main:
[31c2b3b146324888a6581558f739a23ab26025bd](https://github.com/abdullahotb133-debug/heatshift-ai/commit/31c2b3b146324888a6581558f739a23ab26025bd).
It contains the A baseline, not the local corrective work. Local Git has no HEAD
commit or remote; git rev-parse --verify HEAD reported “Needed a single revision”.

Root causes were recorded before code edits in the local audit workspace:
1. G2 required a complete preceding hour of continuous assigned work. Idle
   replacement candidates and future task/zone exposure could never satisfy it.
2. G3 correctly kept prospective criteria UNKNOWN and therefore never selected a
   replacement. It did not equate qualifications or cooler conditions with safety.
3. Default A tasks omit numeric metabolic rates; generic clothing, unsupported
   acclimatization, missing basis and missing history are not valid substitutes.
   These are input/method-scope gaps, not justification to manufacture safety data.
4. The original register has G1–G4 then C1–C3. G5 has no defined original scope.
   The later G4 milestone heading also conflicts with original M4 Persistence.

## Implemented repairs

- risk.py: factor the existing environmental validation and hourly comparison into
  shared private helpers. No NIOSH equation, coefficient, adjustment, range,
  retrospective result contract or applicability rule is replaced.
- prospective.py: new G2 interface assess_proposed_assignment. It evaluates an
  explicit one-hour simulated forecast using the proposed task's numeric watts,
  destination conditions and the candidate's actual clothing/acclimatization.
- decision.py: optional prospective_plans input; every worker/zone alternative
  retains hard constraints and a full computed prospective assessment. Only
  eligible, within-limit candidates can become FEASIBLE_FOR_REVIEW.
- tests/test_prospective.py: actual A-generated histories/forecasts, independent
  arithmetic, conservative failures, deterministic selection and controlled HTTP
  command execution/confirmation.
- Method/rule and historical G3/G4 documentation receive dated amendments. The
  new COMPONENT_B_PLAN.md restores the original package and milestone register.
  No C1/G5, A rewrite, dependency, API endpoint or external integration was added.

## Scientific basis and applicability

NIOSH 2016-106, sections 1.1 and 8.1, expresses environmental/metabolic exposure
on an hourly TWA basis and supplies the RAL/REL equations already used in G2.
The primary PDF was retrieved again; subsequent line-range requests timed out,
but the relevant equations/hourly basis had already been returned by source search:
[NIOSH reference](https://www.cdc.gov/niosh/docs/2016-106/pdfs/2016-106.pdf).

This extension applies that same comparison to an explicit planned continuous hour.
Using a supplied forecast is an engineering scenario assumption, not a NIOSH
weather model or evidence that future conditions are known. It does not estimate
a permissible short exposure time, mixed work/rest schedule or recovery period.
No new threshold, clothing correction, arbitrary score or rate-by-label mapping
was introduced. The original 116–580 W and documented clothing subset remain.

Independent checks use 50-digit Decimal natural logarithms and independently
integrate the supplied samples with Decimal arithmetic. Existing G2 equation,
boundary, clothing and analytic TWA tests remain. Arithmetic agreement does not
validate forecast accuracy, individual fitness or occupational field safety.

## Prospective contract and safety boundary

ProspectivePlan requires:
- exact origin snapshot fingerprint; candidate, proposed task and destination IDs;
- duration_seconds=3600 for supported comparison;
- explicit_simulation_scenario provenance and a nonblank forecast_basis;
- complete destination observations from now through now+3600, initially equal to
  the actual destination observation, with no missing interval beyond A's 1–10s tick;
- AssessmentBasis bound to actual candidate clothing and proposed task;
- prior_exposure_basis and explicit prior_heat_strain_excluded=true.

The prior-strain assertion is a documented synthetic/reference-person assumption,
not a medical determination inferred from idle status or counters. If it cannot be
justified, the caller must leave it false and assessment remains insufficient.
The same applies to reference-person and clothing evidence. All channels, units,
WBGT calculations, quality, metadata and timestamps use G2's shared validation.
Paused origins, wrong state fingerprint, missing/invalid inputs and unsupported
durations/acclimatization cannot produce a within-limit result.

The output is explicitly prospective_simulation. Its assessment timestamp and state
version remain the decision's current origin; its window ends in the future.
Future observations are never relabelled as the worker's observed work history.
The complete result, issues, basis and source/forecast limitations remain attached
to each G3 alternative.

G3 prioritizes hard constraints and within-limit screening, then chooses the largest
distance below the applicable reference limit, then worker ID and zone ID. That
ordering is a screening comparison, not a physiological benefit estimate. Conflicting
supplied current assessment evidence blocks approval even if a forecast is acceptable.
Missing forecasts for possible candidates yield explicit insufficient data; fully
evaluated unacceptable candidates or no mechanical candidates yield no feasible action.
The legacy omitted-plan call remains conservative and compatible.

A selected proposal contains stop_work for the affected worker, mark_unavailable,
assign_task for the replacement at the assessed destination, then start_work.
It uses A's current context/version and deterministic idempotency key. It remains
MANUAL_REVIEW_REQUIRED, submitted=false and thermal_safety_verified=false.
prospectively_acceptable_replacement_ids is distinct from the still-empty
verified_safe_replacement_ids.

**The affected worker remains in the original zone.** No cooling, recovery, safe
return or acceptable ongoing environmental exposure is inferred from stopping.
unresolved_intervention and requires_supervisor_review remain true even when
ACTION_PROPOSED is returned. The planned duration is recorded, but A does not
automatically stop work after it. Human supervision must resolve the affected
worker's protection and limit/monitor the planned exposure; this patch does not
supply an unattended executor. These are outstanding acceptance limits, not hidden
by the successful candidate-selection scenario.

## Demonstration inputs and end-to-end cases

The tests reuse the documented G4 source simulation: three explicitly fictional,
acclimatized inspection workers, 200 W tasks, one-layer clothing evidence, 28 C
baseline thermal channels and the real HEAT_ESCALATION scenario. A generates two
hours of snapshots; candidate availability is changed through its validated API.
Future observations come from A's EnvironmentalSimulator with the same documented
configuration and continuing forcing. Decisions and expected winners are not mocked.

| Scenario | Required result checked |
| --- | --- |
| A — valid candidate | Affected actual G2 excess; eligible acclimatized candidate at ZONE_B passes the planned-hour comparison; G3 selects a traceable proposal for human review. Equal scientific margins use stable IDs. |
| B — unsafe candidate | Unacclimatized candidates fail the applicable RAL even in a cooler destination. All allowed destinations are evaluated; no selected proposal. |
| C — insufficient data | Missing plans, workload, clothing/population/prior-exposure basis, invalid/stale observations, unsupported duration or stale origin cannot authorize a replacement; known intervention remains unresolved. |
| D — no eligible candidate | Unqualified, unavailable, resting or already assigned candidates remain rejected despite acceptable forecast data. |

Controlled test execution submits the selected proposal to A's TestClient HTTP
interface and independently reads state. It checks the replacement's task/zone/
working state, affected worker's idle/unavailable state in the original zone,
incremented version and identical response to a repeated key/body. No real-world
reassignment, hosted service or physiological recovery is claimed.

Default A inputs are deliberately unchanged. These explicit demonstration assumptions
do not silently populate missing operational data. They are reproducible software
fixtures, not validated physical measurements.

## Commands, failure record and observed results

Working directory: outputs/heatshift-ai in this workspace.
Interpreter: /Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python

Commands below used that exact interpreter with -m pytest, bounded by subprocess.run:
180 seconds for focused runs; 240 seconds for the complete regression run.

    -m pytest -q -p no:cacheprovider tests/test_risk.py tests/test_decision.py --junitxml=../../work/corrective-compat.xml
    -m pytest -q -p no:cacheprovider tests/test_prospective.py --junitxml=../../work/corrective-focused.xml
    -m pytest -q -p no:cacheprovider tests/test_prospective.py -k 'complete_prospective_reference or valid_replacement_and_stable or unsafe_even_cooler' --maxfail=1 --tb=short --junitxml=../../work/corrective-repair.xml
    -m pytest -q -p no:cacheprovider tests --tb=short --junitxml=../../work/corrective-results.xml

Observed compatibility result: 109 passed in 24.13s.
Initial new-test result: 33 failed, 1 passed in 9.92s, all 33 failures caused by one
fixture mapping error: raw dataclass source_metadata serialized as pairs, while
the API projection requires an object. Corrected the fixture to use A's existing
dict conversion. One repair attempt for that root cause; no thresholds relaxed.
The narrow repair check passed: 3 passed, 31 deselected, 1 warning in 19.11s.
An earlier patch-format rejection changed no file and ran no tests.

Full regression result: **529 passed, 1 warning in 130.68s**, exit code 0.
JUnit independently confirms zero failures, errors or skipped tests. Breakdown:
369 A + 71 G2 + 38 G3 + 14 G4 + 37 corrective cases. All 37 new cases passed
in this complete run. SHA-256 comparison against the 85-file pre-edit baseline
confirms exactly six existing files changed (the two B modules and four B docs);
the other 79, including every Component A file and all existing test files, are
unchanged. Four new files were added. No scientific equation or safety constraint
was relaxed to repair the fixture mapping error.
The existing Starlette TestClient/httpx deprecation is not a scientific failure.
Local XML/baseline/failure audit records remain under work/ and are excluded from
the source delivery bundle. No cloud execution is claimed.

## Plan correction, remaining issues and next step

COMPONENT_B_PLAN.md preserves original M1–M7. C1 is the next listed package;
G5 is UNDEFINED — REQUIRES PROJECT OWNER CONFIRMATION. Historical G4 remains
PARTIAL within its original scope, not retroactively FAILED. No future package
has started.

Remaining: supervised affected-worker protection, horizon/review enforcement,
defensible operational inputs and forecasts, fresh C1/C2 environment, external
orchestration/persistence, and remote publication. B remains Python-only.
The known GitHub write blocker is unchanged: 403 Resource not accessible by
integration, with browser fallback also denied. Publication is authorized but not
completed; the freshly read remote remains A's baseline. Denied writes were not
repeated without an access change.

Delivery file list: src/heatshift_ai/risk.py, src/heatshift_ai/prospective.py,
src/heatshift_ai/decision.py, tests/test_prospective.py,
COMPONENT_B_RISK_METHOD.md, COMPONENT_B_DECISION_RULES.md,
COMPONENT_B_G3_VERIFICATION.md, COMPONENT_B_G4_VALIDATION.md,
COMPONENT_B_PLAN.md, COMPONENT_B_CORRECTIVE_VERIFICATION.md.
The consolidated archive `../heatshift-pre-g5-corrective-delivery.zip` includes all
14 current G2–G4/corrective source, test and documentation files for application
over the existing Component A baseline. It excludes secrets, caches, environments
and scratch evidence. Earlier phase archives remain historical snapshots.

Next listed package is C1, only after explicit authorization. Full unattended
intervention acceptance remains blocked by the stated safety controls; this task
does not invent a G5 scope or begin another milestone.

