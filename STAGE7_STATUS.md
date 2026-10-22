# Stage 7 handoff

Status: PASS for applicable scenario acceptance tests, using the explicitly permitted
synthetic environment adapter. Real environmental integration remains PENDING and
was not claimed or tested.

## Latest verified checklist

- DONE: inspect environment observation contract and existing worker/task/controller APIs.
- DONE: NORMAL, HEATWAVE, RECOVERY selection; seeded explicit valid demo setup.
- DONE: fixed-order timestamp scripts, off-grid tick splitting and configurable tick counts.
- DONE: named environment override contract and explicitly selected synthetic adapter.
- DONE: reset/replay, deterministic JSON and stop-on-failure without retries.
- DONE: 22 focused tests and 250 full-suite tests passed.
- DONE: executable synthetic recovery demonstration verified.
- FAILED: none; no repairs needed.
- BLOCKED/PENDING: concrete external override mapping and real environment integration;
  existing source provides only a read-only Protocol, not an actual simulator.
- NOT STARTED: Stage 8, risk classification, automatic safety reassignment or optimization.

## Files

Created:
- `src/heatshift_ai/scenarios.py`
- `tests/test_scenarios.py`
- `examples/run_synthetic_scenario.py`
- `STAGE7_STATUS.md`

Modified:
- `src/heatshift_ai/__init__.py`: public exports.
- `README.md`: scenario configuration, scripts, adapter contract and limitations.

Earlier implementation modules, tests and environmental calculations were not edited.

## Observed verification

From `/Users/abdullah/Documents/ChatGPT/heat shit 2`:

```sh
'/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m pytest -q outputs/heatshift-ai/tests/test_scenarios.py
# 22 passed in 0.09s; exit 0
'/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' -m pytest -q outputs/heatshift-ai/tests
# 250 passed in 0.16s; exit 0
PYTHONPATH=outputs/heatshift-ai/src '/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift/work/venv/bin/python' outputs/heatshift-ai/examples/run_synthetic_scenario.py RECOVERY --seed 42 --ticks 5 > work/stage7/recovery.json
```

The resulting JSON was parsed and asserted: elapsed=50 seconds, W-01 cumulative
work=30/rest=20 seconds, 16 events. Output identifies SyntheticScenarioAdapter.

Tests verify valid starts for every scenario, reset and continuation equivalence,
seed variation, exact timestamps/tie order, off-grid actions, work/rest counters,
no conflicting assignments, unchanged worker behavior between NORMAL/HEATWAVE,
request delivery, provenance preservation, invalid config/scripts, unsupported
adapters, wrong observation timestamps and bounded failure behavior.

Runtime: Python 3.13.5; pytest 9.1.1. Not run: real environment integration or a
Python 3.11-specific execution. Synthetic fixture values do not validate any heat
model, threshold or forecast. Real adapters must provide fresh per-run instances.

Next: await the user's explicit Stage 8 prompt. STOP after Stage 7.
