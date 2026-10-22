# Stage 8 checklist

Status: PARTIAL — verified local implementation complete; real integration BLOCKED.

- DONE: inspect existing observation contract, scenario lifecycle and serialization.
- DONE: optional environmental conditions/method/source metadata contract.
- DONE: required snapshot fields, all workers/tasks/zones/events and assignment references.
- DONE: JSON export, strict parse and model-based reference/time validation.
- DONE: CLI scenario/seed/ticks/export controls, README and four example snapshots.
- DONE: 277 tests; all three scenarios; 1000 ticks and identical replay per scenario.
- FAILED: none unexpectedly; no repair attempts.
- BLOCKED: existing Environmental/WBGT Simulator was not supplied; real integration pending.
- NOT STARTED: anything beyond simulator scope.

Created: snapshots.py, __main__.py, tests/test_snapshots.py, four examples/snapshots
JSON files, FINAL_VERIFICATION.md, STAGE8_STATUS.md.
Modified: environment.py (optional observation metadata), scenarios.py (fixture
metadata and current-time read method), __init__.py (exports), README.md.
No WBGT calculation was changed; no worker/task/clock/transition invariant was relaxed.

See FINAL_VERIFICATION.md for exact commands, actual timings, long-run results and
limitations. STOP after Stage 8.
