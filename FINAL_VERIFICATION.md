# Final verification — Stage 8

Overall status: **PARTIAL**. All local simulator/contract tests PASS.
**Real Environmental/WBGT Simulator integration: BLOCKED — source and concrete adapter
were not supplied.** Synthetic and contract-fixture results below are not real integration.

## Observed execution

Working directory: `/Users/abdullah/Documents/ChatGPT/heat shit 2`.
Runtime: Python 3.13.5, pytest 9.1.1. Existing test environment reused; no new dependency
or network installation was required in Stage 8.

```sh
'/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m pytest -q outputs/heatshift-ai/tests/test_snapshots.py
# 27 passed in 0.75s; exit 0
'/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m pytest -q outputs/heatshift-ai/tests --junitxml=work/stage8-tests.xml
# 277 passed in 0.86s; exit 0
```

The full suite includes workers, tasks, state validation, assignments, transitions,
clock, scenario scripts and snapshot/adapter contracts. Previous tests were not edited.

### 1000-tick verification

A parametrized integration test ran every scenario for 1000 individual 10-second
ticks, checking worker zone existence and both sides of every active assignment at
each step. Every state update also passed SimulationState validation. It then reset
and replayed each scenario for 1000 ticks, comparing exported snapshots byte-for-byte.
Total exercised in this check: 6000 ticks across three first runs and three replays.

| Scenario | Final simulated seconds | W-01 cumulative work | W-01 cumulative rest | Replay |
| --- | ---: | ---: | ---: | --- |
| NORMAL | 10000 | 10000 | 0 | Identical |
| HEATWAVE | 10000 | 10000 | 0 | Identical |
| RECOVERY | 10000 | 9980 | 20 | Identical |

No invalid transitions or conflicting assignments occurred. HEATWAVE and NORMAL
have identical worker states/events under the same seed; only environment data differ.
No risk-driven action exists in these runs.

### CLI and sample JSON

The CLI was executed for NORMAL, HEATWAVE and RECOVERY, seed 42, five ticks each,
and NORMAL at zero ticks. Exact command form from the workspace root:

```sh
PYTHONPATH=outputs/heatshift-ai/src '/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m heatshift_ai --scenario NORMAL --seed 42 --ticks 5 --output outputs/heatshift-ai/examples/snapshots/normal.json
PYTHONPATH=outputs/heatshift-ai/src '/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m heatshift_ai --scenario HEATWAVE --seed 42 --ticks 5 --output outputs/heatshift-ai/examples/snapshots/heatwave.json
PYTHONPATH=outputs/heatshift-ai/src '/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m heatshift_ai --scenario RECOVERY --seed 42 --ticks 5 --output outputs/heatshift-ai/examples/snapshots/recovery.json
PYTHONPATH=outputs/heatshift-ai/src '/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m heatshift_ai --scenario NORMAL --seed 42 --ticks 0 --output outputs/heatshift-ai/examples/snapshots/initial.json
```

All four commands exited 0. Each file was independently parsed using parse_snapshot
and reconstructed using validate_snapshot. Each contains 10 workers, 6 tasks and
4 zones. Initial snapshot time/work/rest = 0/0/0; NORMAL and HEATWAVE = 50/50/0;
RECOVERY = 50/30/20 (time/W-01 work/rest, in seconds).

## Adapter compatibility and limitations

PASS: read-only observation fields remain backwards compatible; optional conditions,
method and source metadata transport through JSON unchanged. Tests exercise supplied
condition data, missing values, wrong timestamps, invalid provenance, malformed
metadata, unsupported override APIs and failure-without-retry behavior.

PASS: samples explicitly identify simulated WBGT and the constant fixture method.
No physical sensor measurement, upstream parameter mapping, real weather or heat
model validation is claimed. Sample conditions are empty because the synthetic
adapter supplies no atmospheric inputs. Contract-fixture tests verify that supplied
conditions are retained, rather than invented for missing data.

BLOCKED: real WBGT implementation, method/metadata mapping, scenario overrides and
real adapter lifecycle. These require the actual simulator repository/API.

Not tested: Python 3.11-specific execution, installed wheel, production load/streaming,
external services or clinical validity. No line/branch coverage percentage measured;
test counts must not be interpreted as complete numerical coverage.

## Failures and repair protocol

No unexpected test/command failures occurred during Stage 8; no repair loop was
needed. Expected rejection tests intentionally verify malformed snapshots and invalid
operations. Missing real simulator was handled once by testing the explicit contract
and synthetic adapter, with no attempts to call unsupported external APIs.

## Handoff

Source, tests, README, four sample snapshots and this report are in outputs/heatshift-ai.
Stage 8 is the stopping point. Next action, if requested: supply the real environment
simulator source/API to implement and verify its concrete adapter.
