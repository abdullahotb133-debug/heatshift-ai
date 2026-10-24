# G2 verification — 2026-10-23

> Historical execution record. The GitHub write denial recorded below was resolved
> on 2026-10-24. See [the final repository review](PRE_G5_REPOSITORY_REVIEW.md) for
> current test results, delivery reconciliation and readiness; prior results are preserved.

Implementation and local verification: PASS within the explicitly documented
simulation-only, continuous-work, one-hour scope. On 2026-10-23 the Project Owner
explicitly approved publishing these four G2 files to the existing public GitHub
repository. The final commit and remote verification are reported in the delivery
message after publication. This approval does not authorize another work package.

Publication attempt after approval: BLOCKED. GitHub `create_tree` returned HTTP 403
`Resource not accessible by integration`. The alternative browser upload could not
open github.com because its origin-access permission was denied. Neither route
uploaded any G2 files; no commit or branch update was created. Publication remains
authorized, pending working GitHub write access or browser access.

## Files delivered

- `src/heatshift_ai/risk.py`: deterministic assessment and evidence/output models.
- `tests/test_risk.py`: 71 focused parameterized cases.
- `COMPONENT_B_RISK_METHOD.md`: methodology, applicability, API and limitations.
- `COMPONENT_B_G2_VERIFICATION.md`: this execution record.

No existing Component A source, API contract, dependency or test file was modified.
No HTTP endpoint, database, orchestration, reassignment or deployment was added.

## Environment and executed commands

Working directory: `outputs/heatshift-ai` within this workspace.
Python 3.13.5; existing environment, no installation. Observed versions:
pytest 9.1.1, pydantic 2.14.1, fastapi 0.160.0, httpx 0.28.1, uvicorn 0.54.0.

The exact interpreter used was:
`/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python`

The following commands were executed (the final focused and full runs were wrapped
in `subprocess.run` with 90- and 180-second timeouts respectively):

```sh
"/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python" -m pytest -q -p no:cacheprovider tests/test_risk.py
# Initial focused implementation: 68 passed in 9.49s.
# After adding provenance/sampling checks and three relevant tests:
# 71 passed in 9.81s.

"/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python" -m pytest -q -p no:cacheprovider tests --junitxml=../../work/g2-results.xml
# 440 passed, 1 warning in 13.16s: 369 existing A cases + 71 G2 cases.
```

No failing test or repair loop occurred. The warning is the existing upstream
Starlette TestClient/httpx deprecation; no dependency migration was attempted.
The full run includes the existing API, atomicity, authentication, concurrency,
replay, scenario, OpenAPI and demo tests. This is freshly observed local execution,
not a repetition of the earlier handover's reported results.

## Independent calculation checks

- Both published NIOSH equations checked at 116, 200, 300, 348.9, 400 and 580 W
  against 50-digit Decimal calculations using natural logarithms, independent of
  the production `math.log10` implementation.
- Analytic linear temperature profile 26→30°C: one-hour integral average 28°C.
- Unrounded comparison boundary and values 0.0000001°C above/below it.
- Table 3-2 implemented subset: clothing corrections 0, 0 and +3°C.
- Separate unacclimatized/acclimatized outcomes; unknown/partial status fails closed.

Negative cases cover missing channels/WBGT/workload/evidence, bad units/times,
stale/invalid observations at current and historical samples, unsupported provenance,
duplicate channels, inconsistent calculated WBGT, nonfinite and mistyped values,
incomplete/gapped/reordered/reset/mixed-instance histories, counters, transitions,
coarse sampling and actual Component A start-rest semantics. JSON, repeatability,
input immutability and saved/typed Component A snapshots are covered.

These tests verify implementation arithmetic and stated contracts. They do not
validate field performance, clinical safety, synthetic scenario assumptions or
the representativeness of a supplied metabolic rate. See the method document for
the difference between the publication's graphical example and exact equations.

## Remote baseline and remaining dependencies

GitHub access became available during G2. Read-only inspection identified main at
`31c2b3b146324888a6581558f739a23ab26025bd`. Git blob hashes matched all 47 compared
baseline files: existing Python source/tests, scenario JSON, OpenAPI, dependency
configuration, README and API contract. None of the four new deliverable paths
existed at that commit. This is a baseline comparison, not proof of upload.

C1/C2 remain uncompleted work packages: a fresh reproducible Codespaces environment
has not been verified. Default A data lacks numeric task rates and validated
clothing/population evidence; it intentionally returns insufficient/unsupported
outcomes. Real sensors, mixed work/rest evaluation, cloud hosting, databases and
multi-process coordination are outside G2.

Next proposed package: G3, only after explicit authorization and acceptance of
these prerequisites and scope restrictions. No further package was started.
