# Component A audit — 2026-10-23

Baseline: 357 automated tests pass before this review's changes. Inspected source,
tests, README, pyproject and Stage 1–10 records; PASS statements were not used as proof.

| Stage | Executable implementation and status at baseline |
|---|---|
| 1 | workers/tasks/zones/assignments/time/state, strict dataclass invariants and JSON: working |
| 2 | WorkerSimulator/WorkerConfig, stable fictional IDs and seeded pools: working |
| 3 | TaskSimulator/TaskDefinition: working six-task default; configurable count incomplete |
| 4 | AssignmentManager: eligibility, zone, exclusive atomic assignment: working |
| 5 | SimulationClock/WorkerStateManager: work/rest/exposure, pause/reset: working |
| 6 | EnvironmentalSimulator + separate wbgt.py: synthetic correlated inputs, missing/stale handling: working |
| 7 | IntegratedSimulationEngine: canonical state/time and detached transaction copies: working |
| 8 | EngineeringScenarioRunner: six profiles and explicit scripts: working |
| 9 | FastAPI, schemas, service lock/version/idempotency: working, integration gaps below |
| 10 | Real HTTP mock-client demo, reproducible evidence and handover: working local service |

Confirmed gaps against the latest request:
- TaskConfig enforces six definitions even for custom populations.
- HTTP snapshots/events/observations expose elapsed seconds but no ISO 8601 projection.
- Command results lack explicit before_state_version; after is implicit state_version.
- No aggregate HTTP body-size limit before JSON decoding.
- HTTP ID pattern accepts a leading digit unlike domain validation.
- Same-time API and worker events are reconstructed in groups, losing commit ordering.

Existing default worker skills are explicit seeded configuration, never granted during
assignment or ticks. The legacy ScenarioController/CLI is retained for compatibility;
the API uses only the integrated engine/engineering scenarios. HTTP models are boundary
projections, not independent mutable domain state.

Missing external integrations: physical sensor transport/calibration, real B/C, durable
storage and distributed coordination; these are not claimed. Docker/cloud load tests and
Python-version matrix remain UNVERIFIED. No blocker to local improvements; no production
readiness claim. See improvement plan, reference review and final test report.
