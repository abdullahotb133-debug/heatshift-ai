# G3 decision rules — v0.2.0

Corrective update, 2026-10-24: optional `prospective_plans` now invokes the G2
prospective interface for each candidate/destination. All hard constraints remain.
Eligible candidates within the explicitly forecast hourly limit may produce
`ACTION_PROPOSED` / `FEASIBLE_FOR_REVIEW`, ranked by distance below the applicable
limit, then stable worker/zone IDs. Missing inputs never clear a candidate.

Selected proposals remain manual-review-only and keep `unresolved_intervention=true`: 
the affected worker is stopped and made unavailable, but remains in the original
zone. No rest/recovery or blanket thermal-safety claim is made. A does not enforce
the one-hour forecast horizon automatically. Full current contract, tests and
remaining controls: [corrective report](COMPONENT_B_CORRECTIVE_VERIFICATION.md).

## Historical v0.1.0 rules / compatibility path without prospective plans

The remaining sections record the original G3 limitation and the preserved
no-plan behavior. Their statements about absent prospective support describe
v0.1.0, before the authorized correction, not the optional v0.2.0 path.

## Verified dependency and material limitation

The existing G2 `assess_worker` returns `RiskAssessment`. It evaluates a preceding
hour of continuous work in one task/zone. It explicitly rejects idle/resting workers
and changes of task/zone within the window. Consequently, it cannot establish the
prospective exposure of an otherwise eligible idle replacement, or establish safe
rest/relocation for the affected worker. A historical within-limit result cannot be
relabelled as destination clearance. Component A qualification checks cannot supply
that missing scientific evidence either.

G3 is therefore **PARTIAL**, not a completed reassignment optimizer. This version
implements reproducible evidence verification, real candidate constraints, explicit
alternative rejection and review-only command drafting. No `ACTION_PROPOSED` or
verified-safe replacement is emitted. That enum value is reserved for a future,
separately authorized implementation with an applicable prospective method.

## Python contract

```python
from heatshift_ai.decision import AssessmentEvidence, decide

evidence = AssessmentEvidence(assessment=g2_result, history=original_prior_snapshots,
                              basis=original_assessment_basis)
decision = decide(current_snapshot, affected_worker_id, evidence=evidence,
                  candidate_evidence=candidate_evidence_by_worker_id)
payload = decision.model_dump(mode="json")
```

The existing A snapshot and domain models are revalidated. G2 results are bound to
simulation, instance, version, worker, task, zone and simulated timestamp, then
recomputed from their original inputs. Modified outcomes, identifiers or explanations
are rejected. Typed models are reparsed because Pydantic model-copy operations can
bypass validation. No code changes to A or G2 are required.

## Deterministic rules

1. Missing, malformed, stale or non-reproducible evidence yields `INSUFFICIENT_DATA`.
2. A reproduced within-limit result yields `NO_INTERVENTION_REQUIRED` **relative to
   that historical assessment only**. It does not authorize future work or establish
   general safety. G2 insufficient/unsupported results stay uncertain.
3. A reproduced exceeds-limit result identifies an unresolved intervention need.
4. For every other worker and every existing zone, check required qualifications,
   availability, idle/non-resting state, absence of another assignment, work-zone
   kind and the task's allowed zones. Do not release other workers' assignments or
   alter qualifications/availability to make a candidate eligible.
5. Separately record current/destination observation availability and candidate G2
   evidence. Availability checks are not comprehensive scientific validation.
   Prospective exposure and the affected worker's protection remain `UNKNOWN`.
6. Consider rest, relocation and stopping the current assignment as distinct
   alternatives. A cooler zone does not resolve their missing exposure evidence.
7. No alternative passes all required constraints in this version. Return
   `NO_FEASIBLE_ACTION`, `unresolved_intervention=true`, supervisor escalation and
   `selected_proposal=null`. Missing replacements never justify hazardous continuation.

Candidate and destination IDs are sorted lexicographically. Mechanically eligible
IDs are a diagnostic list, **not an approved shortlist**. There are no scores,
optimization weights or predetermined winners. Selection among multiple thermally
feasible candidates cannot be validated until the prospective dependency is resolved;
the tests do not pretend otherwise.

Each alternative includes all constraint statuses (`PASS`/`FAIL`/`UNKNOWN`) and reasons.
Any failed constraint makes it `REJECTED`; unresolved checks make it `UNVERIFIED`.
Output includes state/assessment references, simulated timestamp, content-derived
decision ID, unresolved needs, proposal status, provenance and limitations.

## Command boundary and supervised stop-work draft

For an excess assessment on an active assignment, a separate
`manual_stop_work_proposal` describes the existing A `stop_work` action. It is
explicitly `MANUAL_REVIEW_REQUIRED`, `thermal_safety_verified=false`, `submitted=false`.
It is **not** the selected feasible action and must not be automatically submitted.
Stopping releases the task to pending and leaves the worker idle in the same zone;
it neither proves cooling nor resolves environmental exposure. A supervisor must
resolve the intervention; this draft offers a contract-correct task-stop option.

The draft reuses `CommandRequest`/`SimulationCommand`, current identity/version and
a deterministic `g3-<hash>` idempotency key. The future submitter must supply bearer
credentials server-side and use `/api/v1/simulation/commands`. State conflicts require
a new snapshot and decision; retries of the same approved request retain key/body.
No execution client, credential, persistence or orchestration is implemented here.

## Acceptance boundary

Tests use the real G2 equations and evidence verification, A's domain constraints,
and explicit fictional fixture candidates. No risk outcome or winner is fabricated.
Existing HEAT_ESCALATION and NO_ELIGIBLE_REPLACEMENT scenarios are exercised; their
default missing numeric rates correctly remain insufficient for G2/G3 assessment.
A no-replacement case with actual G2 excess evidence is separately tested.

Outstanding: scientifically applicable prospective/current assessment for idle
replacements, destination/rest applicability, full feasible selection and end-to-end
accepted reassignment. These require a separately authorized dependency change;
G3 does not silently rebuild G2. C1/C2 and external hosting remain outside this work.
See COMPONENT_B_G3_VERIFICATION.md for executed checks and delivery status.
