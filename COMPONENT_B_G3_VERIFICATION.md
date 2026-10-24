# G3/15 verification — Constraint-Aware Decision & Reassignment Engine

> Delivery update, 2026-10-24: the former GitHub write denial is resolved. See
> [the final repository review](PRE_G5_REPOSITORY_REVIEW.md) for current delivery and tests.

> Historical execution record. The 2026-10-24 corrective task adds prospective
> candidate screening without changing these previously observed results. See
> [current correction and limits](COMPONENT_B_CORRECTIVE_VERIFICATION.md) and
> [authoritative package/milestone register](COMPONENT_B_PLAN.md).

Date: 2026-10-24 (Asia/Riyadh). Status: **PARTIAL**.

## Delivered scope

- `src/heatshift_ai/decision.py`: deterministic, reusable decision evaluation and
  review-only stop-work proposal representation. No transport or execution client.
- `tests/test_decision.py`: 38 focused cases using actual G2 results and existing A
  domain models, including invalid evidence and operational restrictions.
- `COMPONENT_B_DECISION_RULES.md`: interface, rules, command boundary and limitations.
- `COMPONENT_B_G3_VERIFICATION.md`: this evidence and acceptance report.

G2's `assess_worker` / `RiskAssessment` interface is used directly. Supplied results
are recomputed from their original snapshot history and assessment basis, then
checked for context and full-result equality. An actual G2 exceeds-limit result
triggers an unresolved intervention. Missing or unsupported evidence remains
`INSUFFICIENT_DATA`; it never becomes a safety clearance.

All 47 pre-existing source, test, scenario and configuration files in the recorded
pre-G3 SHA-256 baseline remained unchanged, including `risk.py`, `test_risk.py`,
`api_contracts.py` and `openapi.json`. No dependencies were added.

## Executed verification

Working directory: `/Users/abdullah/Documents/ChatGPT/heat shit 2/outputs/heatshift-ai`.

Interpreter: `/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python`
(Python 3.13.5, pytest 9.1.1).

Focused test command:

```sh
'/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m pytest -q -p no:cacheprovider tests/test_decision.py
```

Observed final focused result: **38 passed in 14.68s**.

Full regression invocation, with a 180-second subprocess bound:

```sh
'/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' - <<'PY'
import subprocess, sys
result = subprocess.run(
    [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
     'tests', '--junitxml=../../work/g3-results.xml'],
    timeout=180,
)
raise SystemExit(result.returncode)
PY
```

Observed result: **478 passed, 1 warning in 28.09s** (exit code 0).
JUnit independently confirmed 478 tests, 0 failures, 0 errors and 0 skipped tests.
The total is 369 existing A tests, 71 G2 tests and 38 G3 tests.
The warning is Starlette's existing deprecation notice about using `httpx` with
`TestClient`; no dependency change was made as part of G3.

Local audit evidence remains in `../../work/g3-results.xml` and
`../../work/g3-baseline.json`; these scratch/audit files are excluded from the
source-delivery archive.

## Required test areas and acceptance limits

| Area | Observed coverage / limit |
| --- | --- |
| 1. Intervention identification | Actual reproduced G2 excess result triggers unresolved intervention. |
| 2. Qualified, available replacement | Mechanically eligible candidates are enumerated, without thermal approval. |
| 3–6. Hard operational constraints | Unqualified, unavailable, resting and already assigned candidates are rejected. |
| 7. Destination exposure | Missing, stale and invalid observations are rejected; even cooler rest zones remain unverified without an applicable exposure assessment. |
| 8. Incomplete data | Missing evidence and unassessable G2 results produce conservative outcomes. |
| 9. No eligible replacement | Actual G2 excess with no eligible replacement yields `NO_FEASIBLE_ACTION`, unresolved intervention and supervisor review. |
| 10. Multiple feasible candidates | **Not satisfied.** Multiple mechanically eligible candidates have stable ordering, but no thermally feasible candidates can be established with current G2. No winner is fabricated. |
| 11. Determinism | Identical inputs produce identical decision content and identifiers. |
| 12. Rejection reasons | Constraint codes, statuses and reasons remain traceable per alternative. |
| 13. Command compatibility | Review-only draft uses existing `CommandRequest` / `SimulationCommand` and the OpenAPI-supported `stop_work` action. |
| 14. Context freshness | Stale version, wrong identity/task/zone and modified result fields are rejected. |
| 15. Serialization | Decision output is JSON-compatible; inputs are not mutated. |
| 16. Regression compatibility | Full A + G2 + G3 suite passed; baseline files are unchanged. |

`HEAT_ESCALATION` and `NO_ELIGIBLE_REPLACEMENT` are exercised through the existing
simulation service. Their default missing numeric metabolic rates correctly leave
G2/G3 unable to assess exposure. Separate explicit fictional fixtures supply valid
G2 history and basis for the exceeds-limit and candidate-constraint tests.

The command semantics test applies `stop_work` only to a detached in-memory A
manager and checks the resulting state: worker idle, task pending, same zone and
unchanged simulation time. This verifies command semantics; it is not evidence of
HTTP submission, live execution, cooling or safe recovery. Production decision
evaluation submits no command. Authentication, HTTP idempotency and concurrency
remain Component A's responsibilities; the G3 draft carries the current state
version and a deterministic idempotency key.

## Why the milestone remains PARTIAL

G2 currently assesses a preceding hour of continuous work in the same task and
zone. It does not provide prospective exposure assessment for a new assignment,
an idle replacement, relocation or rest. A retrospective within-limit assessment
cannot demonstrate that an intervention is safe or reduces exposure.

Consequently, this implementation emits no `ACTION_PROPOSED`, selects no replacement
and leaves `selected_proposal` null. For a verified excess, the separate
`manual_stop_work_proposal` is marked `MANUAL_REVIEW_REQUIRED`,
`thermal_safety_verified=false` and `submitted=false`. Stopping task execution alone
does not establish an acceptable environment or resolve the intervention need.

Applicable prospective exposure inputs/methodology and a separately authorized
dependency extension are required before feasible action selection, risk-reduction
claims and required test area 10 can pass. Passing the implemented tests is not
full G3 acceptance. A and G2 were preserved as instructed.

## Delivery and next boundary

The local source archive is `../heatshift-g3-delivery.zip`; it contains only the four
G3 files listed above and must be applied alongside the existing G2 deliverable.
It excludes secrets, environments, caches and scratch work.

GitHub publication is **not complete**. The preceding upload attempt returned
`403 Resource not accessible by integration` from the GitHub write connector;
the browser fallback was also denied access. No access change has been observed,
and those denied paths were not retried for G3. The repository remains the user's
configured target: https://github.com/abdullahotb133-debug/heatshift-ai.
Neither G2 nor G3 is claimed uploaded. Connected repository write access is needed
to finish publication; additional routine user consent is not needed.

At the time of this G3 report, no G4 work had started. Its next scheduled package was: **G4 — Automated Testing,
Validation & Integration Contracts**, only after explicit authorization, with the
prospective-assessment dependency remaining an explicit acceptance blocker.
