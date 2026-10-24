# G4/15 — Backend integration validation and contracts

> Delivery update, 2026-10-24: the former GitHub write denial is resolved. See
> [the final repository review](PRE_G5_REPOSITORY_REVIEW.md) for current delivery and tests.

> Historical execution record. The 2026-10-24 corrective task adds prospective
> candidate screening without changing these previously observed results. See
> [current correction and limits](COMPONENT_B_CORRECTIVE_VERIFICATION.md) and
> [authoritative package/milestone register](COMPONENT_B_PLAN.md).

Date: 2026-10-24 (Asia/Riyadh). **Status: PARTIAL. Readiness: BLOCKED for automated
safety intervention/orchestration.** The supported simulation-only processing chain
works; the prospective-exposure dependency identified in G3 remains unresolved.
This report consolidates integration results, regression evidence, contracts and
the gap register. G4 does not rebuild either engine or begin G5.

## Inspected implementation and revision

Remote `main`, freshly inspected through the GitHub read connector:
[`31c2b3b146324888a6581558f739a23ab26025bd`](https://github.com/abdullahotb133-debug/heatshift-ai/commit/31c2b3b146324888a6581558f739a23ab26025bd).
This is the Component A baseline, **not a commit containing G2–G4**.
The workspace Git repository has no commits and no configured remote;
`git rev-parse --verify HEAD` returned `fatal: Needed a single revision`.
All execution evidence below concerns the local source tree, not remote CI.

Reviewed existing A contract/source and available G1 findings, plus
`COMPONENT_B_G2_VERIFICATION.md`, `COMPONENT_B_G3_VERIFICATION.md` and their actual
implementations/tests. G2 is present with a verified, restricted retrospective
method. G3 is present but explicitly PARTIAL: it cannot select a thermally verified
replacement. No separate saved G1 completion report was found in the project;
current interface findings were checked against A's code and canonical OpenAPI.

Application factory: `heatshift_ai.api:create_app`; local launch entry point:
`python -m uvicorn heatshift_ai.api:create_app --factory --workers 1`.
This launch command documents the interface; G4 used an in-process FastAPI TestClient,
not a deployed server. Existing Python 3.13.5 environment was reused without installs.

## Integration evidence and scenario results

Added `tests/test_backend_integration.py`. It supplies explicit fictional inputs
through existing A configuration models: three inspection-qualified acclimatized
workers, one initial T-01 assignment in ZONE_A, 200 W task rates, one-layer clothing
evidence and 28°C baseline thermal channels. These are scenario assumptions, not
measured personnel inputs or independent scientific validation.

A's HTTP service does not accept a custom EngineConfig constructor argument. The
test temporarily substitutes its runner constructor with the **real**
`EngineeringScenarioRunner(..., config=...)` before initialization. The substitution
does not replace any validator, assessment, decision, clock or observation method.
The real A service generates 360 ten-second steps per hour. HTTP GET independently
reproduces the final service snapshot. Spare-worker unavailability and activation
of the unchanged HEAT_ESCALATION preset use authenticated A HTTP requests.
No snapshot temperature, risk outcome or winner is patched after generation.

| Required scenario | Verified behavior |
| --- | --- |
| Normal operation | One complete generated hour, actual G2 `WITHIN_APPLICABLE_LIMIT`, G3 `NO_INTERVENTION_REQUIRED` relative to that historical assessment. Identity, version, time, rate, evidence and limitations are retained. |
| Heat escalation | The actual A heat-ramp preset generates a hotter second-hour TWA; G2 returns `EXCEEDS_APPLICABLE_LIMIT`; G3 evaluates alternatives and reports unresolved `NO_FEASIBLE_ACTION`. |
| No eligible replacement | Spare workers made unavailable through A are rejected by G3; no safe replacement or selected action is invented. The separate unmodified NO_ELIGIBLE_REPLACEMENT preset is also exercised and correctly remains scientifically incomplete. |
| Missing scientific inputs | Unmodified NORMAL_OPERATION, HEAT_ESCALATION and NO_ELIGIBLE_REPLACEMENT HTTP scenarios remain insufficient. Missing history/basis, missing/stale/invalid observations and invalid channel units fail conservatively through G2 and G3. |
| State conflict | A real G3 draft is rejected with HTTP 409 / `stale_version` after a tick. State remains unchanged by rejection; G3 also rejects the old assessment context. A new assessment/proposal uses the fresh version. |
| Repeated requests | JSON round-trips preserve full models; repeated calculations/decisions agree. A repeated command key/body returns the original response even after a later pause, without changing current state. A changed body with the same key returns 409 / `idempotency_conflict`. |

Additional checks verify authentication rejection, atomic rollback of a batch whose
replacement violates eligibility, and stop-work result/event versions. A fresh
review-only G3 draft is explicitly submitted **by the test harness only**. The test
confirms `status=applied` through the response and independent GET: task pending,
worker idle in the same zone. This is verified simulated HTTP execution, not safe
reassignment, cooling, live deployment or real-world personnel action. The G3 object
remains `submitted=false`; execution outcomes are separate A records.

The test does not introduce approval bypasses into production. A accepts mechanically
valid commands without enforcing B's thermal or review flags; a future caller must
not mistake `manual_stop_work_proposal` for an approved `selected_proposal`.

## Executed commands and regression report

Working directory: `/Users/abdullah/Documents/ChatGPT/heat shit 2/outputs/heatshift-ai`.
Exact interpreter: `/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python`.
Both pytest invocations run under `subprocess.run(..., timeout=180)` and propagate
the subprocess exit code.

```sh
'/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m pytest -q -p no:cacheprovider tests/test_backend_integration.py --junitxml=../../work/g4-focused.xml

'/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m pytest -q -p no:cacheprovider tests --junitxml=../../work/g4-results.xml
```

Focused result: **14 passed, 1 warning in 33.52s**, exit code 0.
Full regression result: **492 passed, 1 warning in 79.72s**, exit code 0.
JUnit confirms 492 tests, zero failures, zero errors and zero skipped tests:
369 existing A cases, 71 G2 cases, 38 G3 cases and 14 G4 integration cases.
No failed test, targeted production repair or repeated failing command occurred.

SHA-256 comparison confirms that all 83 recorded pre-G4 source, test, configuration,
example and documentation files are unchanged. Local audit evidence is retained in
`../../work/g4-baseline.json`, `../../work/g4-focused.xml` and
`../../work/g4-results.xml`; scratch/audit files are excluded from the source archive.
Integration test SHA-256:
`10ad3a01ae064a8f96ed042c786bf9f6db1b7c53acb75813610cfdac4a00fb5e`.

The warning is the existing Starlette TestClient/httpx deprecation. G4 does not
migrate dependencies. No failed focused test or repair attempt occurred.

The full suite includes A initialization, assignments, observations, activation,
time advancement, validation, atomicity, version and idempotency tests; existing G2
independent Decimal equation checks, analytic TWA, boundary and clothing cases;
and G3 candidate/assessment integrity tests. Independent arithmetic checks remain
separate from integration acceptance and do not establish field or clinical validity.

Schema checks compare generated OpenAPI with the canonical `openapi.json`, resolve
all local references, verify mutation authentication/header/request/response schemas,
generate the existing B Pydantic JSON schemas and exercise round-trip validation.
No external OpenAPI validator or cloud CI run is claimed.

## Integration contracts for future callers

Canonical A schemas: `openapi.json` and `src/heatshift_ai/api_contracts.py`.
Canonical B schemas: the models in `risk.py` and `decision.py`, obtainable via
`model_json_schema()`. B has **Python interfaces only**, with no risk or decision
HTTP endpoint. No adapter is necessary for this in-process chain. Adding a transport
adapter would not resolve the scientific dependency and was not justified in G4.

### A HTTP routes

| Interface | Request and required inputs | Response |
| --- | --- | --- |
| GET `/health` | None; public | `Health`: schema version, status, component. |
| GET `/api/v1/simulation/state` | No body | `SimulationSnapshot`; full context and arrays below. |
| GET `/api/v1/workers`, `/tasks`, `/zones`, `/observations`, `/events` | No body | Typed `Collection` with context and required `items`; entity rows inherit envelope identity/version/time. |
| GET `/api/v1/scenarios` | No body | `Collection[ScenarioInfo]`; each row requires scenario ID, version, parameters. |
| POST `/api/v1/simulation/tick` | Common mutation fields; optional `delta_seconds`, default 10, strict integer 1–86400 | `SimulationCommandResult`. |
| POST `/api/v1/simulation/reset`, `/pause`, `/resume` | Common mutation fields | `SimulationCommandResult`. |
| POST `/api/v1/scenarios/activate` | Common fields plus required scenario ID; optional failure mode `missing`, `stale`, `invalid` | `SimulationCommandResult`. |
| POST `/api/v1/simulation/commands` | Common fields plus 1–32 validated `SimulationCommand` objects | `SimulationCommandResult`; whole batch commits or none does. |

All mutation bodies require `schema_version="1.0"`, `simulation_id`, `instance_id`,
and nonnegative strict integer `expected_state_version`. All POSTs require bearer
authentication and `Idempotency-Key` (1–128 characters matching
`[A-Za-z0-9_.:-]+`). Data GETs require bearer authentication in deployment mode;
development reads are public. Health/OpenAPI/docs remain public. Deployment startup
requires a configured token of at least 32 characters. No secret is stored in G4.

The command action enum is: `assign_task`, `unassign_task`, `start_work`, `stop_work`,
`start_rest`, `end_rest`, `change_zone`, `change_task`, `mark_unavailable`,
`mark_available`. Each requires a nonblank reason of at most 500 characters.
`assign_task`/`change_task` require worker + task and optionally zone; `unassign_task`
requires task; `start_rest`/`change_zone` require worker + zone; the remaining actions
require worker. Other argument combinations/unknown fields fail validation.
Domain validators also enforce assignment reciprocity, qualifications, availability,
work/rest state and permitted zone semantics.

Errors use `ErrorResponse`: `schema_version`, required `error.code` and `error.message`.
Relevant codes/statuses: 401 `unauthorized`; 409 `simulation_conflict`, `stale_version`,
`idempotency_conflict`; 422 `invalid_request` or `domain_rejection`; 413
`request_too_large`; 503 `authentication_unconfigured` or `operation_capacity`;
500 sanitized `internal_error`; 404/405 `http_error`. OpenAPI also declares 403,
but no specific normal application 403 branch was identified in the inspected code.

Every successful distinct mutation increments the API version, including a paused
tick. Replay is checked before stale-version rejection: same route/key/validated
body returns its original response, **not the latest state**. Read GET for current
state. Keys/ledger/state are process-local; reset preserves the ledger and monotonic
API version but clears run history/time. Restart loses state/ledger and creates a
new instance. Wrong instance is not repaired by replaying an old command with new IDs.

### A data models and mapping into B

Required context: `simulation_id`, `instance_id`, `state_version`, `elapsed_seconds`,
`simulated_at`. Default literal metadata: schema 1.0, source `synthetic_simulator`,
time unit `s`, simulation epoch 2026-01-01 UTC and `time_basis=simulation_epoch`.
Times are simulation-time projections, not wall-clock sensor timestamps.

| Model | Required data and validation/mapping |
| --- | --- |
| `SimulationSnapshot` | Context; zones, workers, tasks, assignments, events, random_seed, tick_seconds, scenario, scenario_input, scenario_phase, paused. B reparses projections and existing domain invariants; `valid=true` means domain validity, not thermal safety. |
| `WorkerSnapshot` | ID, display_name, current_zone_id, qualifications, acclimatization_status, clothing_profile, nullable current_task_id, work_status, availability_status, exposure/rest/current-work/current-rest durations in seconds. B uses exact worker/task/zone identity, statuses and elapsed counters. |
| `TaskSnapshot` | ID, task_name, workload_category, allowed_zone_ids, nullable estimated_metabolic_rate_watts, required_qualifications, task_status, nullable assigned_worker_id. G2 requires an explicit finite numeric whole-body rate in its supported range; it never derives watts from the category. |
| `ZoneSnapshot` / assignments | Zone ID, kind, environmental observation. Assignment requires worker ID, task ID, zone ID and started_at_elapsed_seconds; domain reciprocity must hold. |
| `EnvironmentalObservation` | zone_id, elapsed_seconds, observed_at_seconds, observed_at, source, quality, nullable wbgt_celsius, wbgt_kind, nullable method, source_metadata and conditions. Conditions require name/value/unit. G2 checks simulated provenance, current good quality, matching metadata/time and consistent calculated degC WBGT from explicit channels. No fabricated substitute for missing WBGT. |
| `SimulationEvent` | event_id, elapsed_seconds, occurred_at, before/after state versions, action, reason, source; worker ID/old/new snapshots optional by event type. Consumers retain instance + event ID and event order. |
| `SimulationCommandResult` | Context; before/after state versions, idempotency_key, event_ids, snapshot; literal status `applied`. This is execution evidence; a decision/draft alone is not. |

IDs use A's leading-letter alphanumeric/underscore/hyphen rule. Extra schema fields
are rejected; nonfinite numeric values are forbidden. Durations/versions are strict
nonnegative integers. Preserve original snapshots/observations/history alongside
B results when future persistence is implemented: B summarizes provenance and
references evidence rather than copying every raw environmental field into a result.

### B Python interfaces

`assess_worker(snapshot, worker_id, *, history=(), basis=None) -> RiskAssessment`
accepts an A snapshot or mapping. A valid comparison requires the preceding full
3600-second history with supported 1–10 second sampling, unchanged continuous
task/zone/clothing/acclimatization, current observations and explicit evidence.
`AssessmentBasis` requires worker ID, task ID, clothing profile/ensemble and
clothing/metabolic/population basis text; `reference_person_applicable` defaults
false and must be explicitly supported. Supported rate range: 116–580 W.
The configured clothing subset and equation applicability remain as documented
in `COMPONENT_B_RISK_METHOD.md`; G4 does not change them.

`RiskAssessment` requires assessment_id, outcome and explanation. Context,
timestamp/provenance, method/version/source, window, sample count, WBGT/TWA,
effective TWA, rate, clothing adjustment, acclimatization, reference limit,
evidence, issues and limitations are retained when available. Outcomes are
`WITHIN_APPLICABLE_LIMIT`, `EXCEEDS_APPLICABLE_LIMIT`, `INSUFFICIENT_DATA`,
`NOT_ASSESSABLE`. Assessment failures are structured outcomes, not HTTP errors;
explicit construction of invalid Pydantic models can itself raise ValidationError.
No authentication, execution or server-side idempotency store exists in this function.

`decide(snapshot, worker_id, *, evidence, candidate_evidence=None) -> Decision`
requires the evidence keyword (it may be None to obtain a conservative result).
`AssessmentEvidence` requires the actual assessment, with original history/basis
needed for reproduction. Candidate evidence is indexed by worker ID. G3 verifies
identity/version/time and recomputes G2 before trusting the supplied result.
Missing, stale, malformed or nonreproducible evidence yields `INSUFFICIENT_DATA`.

`Decision` requires decision_id, outcome and explanation; it includes input context,
assessment reference, affected worker/assignment, constraints, alternatives with
statuses/reasons, diagnostic mechanically eligible IDs, unresolved intervention,
review flag, ruleset version, timestamp and limitations. Identical inputs produce
identical outputs. `ACTION_PROPOSED` is reserved and never emitted by current G3.
Historical within-limit results are not future-work clearance. An excess yields
unresolved `NO_FEASIBLE_ACTION` with `selected_proposal=null`.

The optional `CommandProposal` requires A's `CommandRequest` body, idempotency key
and expected_effect; flags are fixed to `MANUAL_REVIEW_REQUIRED`,
`thermal_safety_verified=false`, `submitted=false`. Credentials are not included.
The current manual draft is `stop_work`, leaving the worker in the same zone.
Reassessment after any state change is required before new submission. Persistence
must distinguish a deterministic decision ID, a request idempotency key and A's
confirmed command result; none is a substitute for the other.

## Gap register and readiness verdict

| ID | Confirmed gap | Consequence / required follow-up |
| --- | --- | --- |
| G4-01 — blocking | G2 lacks prospective/new-assignment/rest assessment; G3 cannot select verified-safe actions or compare multiple thermally feasible candidates. | G3 acceptance remains incomplete. Requires a separately authorized scientific/development task; G4 must not replace G2 or redesign G3. |
| G4-02 — blocking for meaningful default assessments | Default A tasks have no numeric rates and no validated clothing/population basis or retained one-hour B input history. | Default scenarios must remain insufficient. Future input provisioning and history collection need explicit contracts/applicability; the test fixture does not fix production inputs. |
| G4-03 — workflow boundary | B is Python-only; no orchestration, review enforcement, durable audit or command-confirmation workflow exists. | Future orchestration must preserve uncertainty, enforce review and current state, submit only authorized commands, then confirm A results. No extra endpoint was added in G4. |
| G4-04 — persistence boundary | A state, replay ledger and event history are in one process; reset/restart have documented semantics. | Future persistence must retain original input evidence and separate decision/proposal/execution records. Multi-process/durable operation is not verified here. |
| G4-05 — delivery blocker | Connected GitHub write attempt previously returned 403 `Resource not accessible by integration`; browser fallback was denied. Remote main is still the A baseline. | G2–G4 remain local. No changed write access has been established; denied writes were not repeated. Publication is already authorized, but requires working repository write access. |
| G4-06 — environment limit | Existing local environment passed; no fresh Codespaces/C1/C2 setup or hosted deployment was verified. | Results establish local compatibility, not clean-environment/cloud readiness. |

No production integration defect requiring a targeted repair was reproduced in the
supported scope. Only the integration test file and this report were added. Neither
the scientific methodology nor operational constraints were relaxed to pass tests.
Readiness remains **BLOCKED for automated safety decisions/commands**; the existing
interfaces support local simulation analysis and supervised integration development
within the documented limitations. No real-world safety acceptance is claimed.

Local delivery: `../heatshift-g4-delivery.zip`, containing the two new G4 files.
It depends on the existing A, G2 and G3 files and is not a standalone application.
Corrected next-package reference: C1 is next in the original register; it has not started. G5 is UNDEFINED — REQUIRES PROJECT OWNER CONFIRMATION. Original milestone M4 remains Persistence; the later G4 label does not renumber the master plan.
