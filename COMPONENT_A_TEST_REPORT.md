# Component A verification report — 2026-10-22

Status: **PASS for the implemented local HTTP Component A**. Components B/C, live sensor
integration, container/cloud deployment and production load validation are not claimed.

## Actual execution

Working directory: `/Users/abdullah/Documents/ChatGPT/heat shit 2`.
Interpreter used (abbreviated `$PY` below):
`/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python`.
Python 3.13.5, pytest 9.1.1; all installed package versions are in requirements.lock.

```sh
"$PY" -m pytest -q outputs/heatshift-ai/tests
# Before changes: 333 passed in 1.58s
"$PY" -m pytest -q outputs/heatshift-ai/tests/test_api.py -x
# First focused API execution: 18 passed in 1.41s
"$PY" -m pytest -q outputs/heatshift-ai/tests/test_api.py
# Expanded API checks: 21 passed in 1.23s
"$PY" -m pytest -q outputs/heatshift-ai/tests --junitxml=work/component-a-results.xml
# Final regression: 357 passed, 1 warning in 2.64s (24 new API/demo tests)
PYTHONPATH=outputs/heatshift-ai/src "$PY" outputs/heatshift-ai/examples/export_api_contract.py
# Exported OpenAPI and 14 executed endpoint examples
"$PY" outputs/heatshift-ai/examples/component_a_demo.py --output outputs/heatshift-ai/examples/api/component_a_evidence.json
"$PY" outputs/heatshift-ai/examples/component_a_demo.py --output work/component_a_replay.json
# Both real HTTP runs: PASS: HTTP snapshot, tick, scenario, atomic reassignment,
# persisted state and counters; elapsed=80
cmp outputs/heatshift-ai/examples/api/component_a_evidence.json work/component_a_replay.json
# exit 0: byte-identical canonical evidence from two fresh servers
```

The committed JSON evidence contains actual responses, before/after snapshots and event
sequence, not fixed success strings. Assertions check synchronized observations, valid
assignments, clock/counters, eligibility, new assignee and read-after-write state. Random
service instance IDs are normalized only in exported evidence so independent runs compare.

## Tested coverage

All previous worker/task/assignment/transition, WBGT, environment adapter and scenario tests
continue to pass. New HTTP tests cover all routes, named OpenAPI schemas, response parsing,
bearer auth, fail-closed writes, deployment startup/read protection, CORS allowlist,
request field/type/version validation, malformed JSON, unknown routes, atomic batches,
qualification/availability/zone rejection, counter updates, reset/epoch handling, pause,
activation preserving time/history, no eligible replacement, scripted recovery, missing/
stale/invalid sensor channels, 409 conflicts, duplicate replay, simultaneous competing
requests, simultaneous identical keys, operation capacity, serialization-failure rollback,
and deterministic mock-client replay. The existing suite includes long scenario runs;
Stage 8 also independently verified 1000 ticks + replay for every engineering scenario.

## Failures, corrections and limits

- Initial package installation could not reach PyPI inside the network sandbox. A permitted
  network-enabled install succeeded; no dependencies remain blocked.
- First real HTTP demo could not bind a local socket in the sandbox. A permitted local
  execution succeeded twice. This was an execution permission issue, not a model defect.
- During inspection, HTTP reset needed to rebase a scenario activated at nonzero time;
  this was implemented explicitly with regression coverage. Event IDs now include the
  reset epoch. No existing test assertions were relaxed.
- No automated test failures occurred in the implementation runs above.
- One upstream Starlette deprecation warning: its TestClient currently accepts httpx but
  recommends httpx2. The pinned tested stack passes; no unsupported migration was attempted.
- No branch/line coverage percentage, wheel installation, Docker build, cloud deployment,
  Python 3.11/3.12 runtime, throughput benchmark, durable persistence or distributed
  transaction test was performed. Do not treat this report as validation of those areas.

The core engine remains framework-independent. APIService uses Pydantic only to validate
HTTP projections before commit; FastAPI is confined to api.py. No risk thresholds,
physiological predictions, n8n workflow, Supabase database or React dashboard was added.
