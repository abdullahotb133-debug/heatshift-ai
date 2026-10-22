# Stage 1 handoff

Status: PARTIAL — local foundation acceptance tests passed; existing environmental
interface discovery/compatibility is BLOCKED because no source was supplied.

## Latest verified checklist

- DONE: inspect supplied workspace once; no pre-existing code or environmental interface found.
- DONE: immutable typed Worker, Task, Assignment, Zone, SimulationTime and SimulationState models.
- DONE: shared enums, field validation, cross-entity consistency, deterministic JSON export.
- DONE: proposed read-only environment Protocol with explicit reading provenance.
- DONE: 79 focused pytest cases passed on Python 3.13.5 with pytest 9.1.1.
- BLOCKED: identify/verify the actual environmental simulator interface; no upstream source available.
- FAILED: none outstanding in model tests.
- NOT STARTED: generation, ticking, concrete environment integration, subsequent stages.

## Files created

- `pyproject.toml`, `README.md`, `STAGE1_STATUS.md`, `.gitignore`
- `src/heatshift_ai/__init__.py`, `enums.py`, `validation.py`, `serialization.py`
- `src/heatshift_ai/workers.py`, `tasks.py`, `zones.py`, `assignments.py`
- `src/heatshift_ai/time.py`, `state.py`, `environment.py`
- `tests/test_models.py`

No existing code was modified. The test virtual environment and build scratch
script are in the workspace `work/` directory, outside the deliverable.

## Observed verification

Run from `/Users/abdullah/Documents/Codex/2026-10-22/files-pasted-by-the-user-heatshift`:

```sh
work/venv/bin/python -m pytest -q outputs/heatshift-ai/tests
```

Observed exit 0: `79 passed in 0.05s`.
All listed local acceptance cases ran. No actual environmental integration test
ran. Python 3.11 itself and installed-wheel packaging were not tested; tests ran
against source on Python 3.13.5.

## Bounded failure record

1. Tooling check: `python3 -m pytest --version` reported
   `No module named pytest`. The bundled Python check
   `/Users/abdullah/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m pytest --version`
   confirmed no existing pytest there either. No source files affected.
   Hypothesis: test dependency is missing.
   First repair: `python3 -m venv work/venv && work/venv/bin/python -m pip install --disable-pip-version-check --retries 0 --timeout 20 pytest`.
   Result: `No matching distribution found for pytest` from the configured index.
   Second distinct repair: explicit public index and approved network access:
   `work/venv/bin/python -m pip install --index-url https://pypi.org/simple --no-cache-dir --disable-pip-version-check --retries 0 --timeout 20 'pytest>=8,<10'`.
   Result: pytest 9.1.1 and dependencies installed successfully.
2. Test-launch path: `../../work/venv/bin/python -m pytest -q outputs/heatshift-ai/tests`
   failed with `no such file or directory: ../../work/venv/bin/python`.
   No source file affected. Hypothesis: command used a project-relative path from
   the workspace root. One repair changed it to `work/venv/bin/python`, as in the
   passing command above. No model-validation failures occurred.

Next: supply the actual environmental simulator repository to verify the proposed
adapter boundary. Stop here; no Stage 2 work without an explicit user prompt.
