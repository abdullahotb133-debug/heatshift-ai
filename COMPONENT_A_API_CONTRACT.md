# Component A HTTP contract — schema 1.0

The authoritative machine-readable contract is [openapi.json](openapi.json), also
served at `/openapi.json`. Interactive documentation: `/docs`. The HTTP boundary uses
FastAPI/Pydantic projections of existing immutable domain objects. Domain, environment,
clock and scenario modules have no FastAPI/Pydantic imports.

## Routes

| Method | Path | Request | Successful response |
|---|---|---|---|
| GET | /health | none | Health |
| GET | /api/v1/simulation/state | none | SimulationSnapshot |
| POST | /api/v1/simulation/tick | TickRequest | SimulationCommandResult |
| POST | /api/v1/simulation/reset | MutationRequest | SimulationCommandResult |
| POST | /api/v1/simulation/pause | MutationRequest | SimulationCommandResult |
| POST | /api/v1/simulation/resume | MutationRequest | SimulationCommandResult |
| GET | /api/v1/zones | none | Collection[ZoneSnapshot] |
| GET | /api/v1/workers | none | Collection[WorkerSnapshot] |
| GET | /api/v1/tasks | none | Collection[TaskSnapshot] |
| GET | /api/v1/observations | none | Collection[EnvironmentalObservation] |
| GET | /api/v1/scenarios | none | Collection[ScenarioInfo] |
| POST | /api/v1/scenarios/activate | ActivateRequest | SimulationCommandResult |
| GET | /api/v1/events | none | Collection[SimulationEvent] |
| POST | /api/v1/simulation/commands | CommandRequest | SimulationCommandResult |

[Executed examples for all 14 endpoints](examples/api/endpoint_examples.json) contain
request bodies, headers, actual responses and status codes. Replace example instance
IDs and versions with those from your own GET. No secret is included in those examples.

## Context, units and provenance

Every state/collection/result envelope has `schema_version: "1.0"`, `simulation_id`,
`instance_id`, integer `state_version`, integer `elapsed_seconds`, `time_unit: "s"`,
`source: "synthetic_simulator"`. Entity projections inherit envelope context rather
than repeating it per row. Worker durations use `_seconds`; estimated task metabolic
rate uses `_watts` and is an illustrative optional value, not a validated measurement.
Environmental channels carry their own `unit`; WBGT has `wbgt_unit: "degC"`.

EnvironmentalObservation preserves zone ID, requested `elapsed_seconds`, actual
`observed_at_seconds`, source, quality, conditions, WBGT method, kind and full metadata.
`source=simulated` means simulated sensor observations, never physical measurements.
`wbgt_kind=calculated` describes arithmetic using explicit simulated natural wet-bulb
and globe channels (and dry-bulb under solar load). It does not change provenance to
measured. `quality=missing|stale|invalid` produces null WBGT, never fabricated replacement
measurements. The schema reserves `estimated` for future validated methods; this
implementation produces no WBGT estimates. No air/RH psychrometric substitution exists.

Worker events project the original canonical transition into old/new worker snapshots,
reason, timestamp and ID; the domain retains its complete old/new states internally.
API control events mark tick, activation, pause, resume, reset and command batches.
`valid=true` confirms domain invariants, **not** occupational safety or data calibration.

## Mutations, optimistic concurrency and retries

All POSTs require `Authorization: Bearer <token>` and `Idempotency-Key` (1–128 ASCII
letters/digits/underscore/dot/colon/hyphen). All bodies require:

```json
{"schema_version":"1.0","simulation_id":"SIM-001","instance_id":"<from GET>","expected_state_version":0}
```

Tick adds `delta_seconds` (integer 1–86400, default 10). Activation adds a scenario ID
and optional `failure_mode` (`missing`, `stale`, `invalid`). It starts the selected
versioned profile at current simulated time and retains worker history. Switching
presets may change the starting environmental baseline immediately; within-profile
ramps are smooth. Activation replaces pending scenario scripts explicitly.

Commands add `commands`, a list of 1–32 SimulationCommand objects, applied atomically
in order. Allowed actions: assign_task, unassign_task, start_work, stop_work, start_rest,
end_rest, change_zone, change_task, mark_unavailable, mark_available. Exact required
arguments are validated; unknown keys/actions and direct state patches are rejected.
Reasons are required. Existing domain eligibility and transition rules remain binding.

A single process lock protects reads and writes. Requests operate on a detached engine
and scenario cursor. Output validation and JSON encoding occur before publication.
Each successful distinct POST increments state_version, including paused ticks and
repeated pause controls. Failed requests change neither state, version, events nor cache.

Identical key + normalized validated body + route returns the **original result** without
execution, even after subsequent state changes/reset. Read a fresh snapshot if current
state is needed. A reused key with different content returns 409. A fresh key with an
old version or wrong simulation/instance returns 409. Cache is process-local, retained
across reset and bounded by HEATSHIFT_MAX_OPERATIONS; capacity returns 503, without
silently evicting keys. Restart loses state/cache and changes instance_id. Never retry
an old command against a new instance without first reading and reconsidering it.

Reset rebuilds the active scenario at time zero using the same seed, clears run history,
resumes, rebases scenario/failure timing, and keeps the monotonic API state version.
Worker event IDs have a reset-epoch prefix. Consumers should key records by instance_id
and event_id; snapshots by instance_id and state_version. Reset is an explicit new run.

## Errors and security

Consistent error envelope:

```json
{"schema_version":"1.0","error":{"code":"stale_version","message":"State changed; read a fresh snapshot"}}
```

401: missing/invalid bearer. 409: version/instance/idempotency conflict. 422: malformed
JSON, schema mismatch, bad arguments or domain rejection. 503: authentication not
configured or operation capacity reached. 500: unexpected internal failure, sanitized.
404/405 also use this envelope. Request validation errors do not echo payload values.

Deployment mode refuses startup without a token of at least 32 characters and protects
all data GETs as well as POSTs. Health/OpenAPI/docs remain public. Development mode permits
reads but still requires a configured token for writes; no implicit default secret.
CORS is an explicit origin allowlist, defaults empty, no wildcard or cookie credentials.
Terminate HTTPS at the deployment edge. Keep the write token server-side in Component B;
do not embed it in a browser bundle. For Component C in deployment, use a trusted backend
proxy with suitable user authorization. This service does not implement users, OAuth,
per-client roles, durable audit storage, pagination or distributed coordination.

## Scripted Component B example

Read state; verify T-01 qualification `inspection`, W-06 availability/idle/unassigned,
and allowed ZONE_A. For the documented seed-42 fixture, submit one batch:

```json
{"commands":[
  {"action":"stop_work","worker_id":"W-03","reason":"scripted mock B handover"},
  {"action":"assign_task","worker_id":"W-06","task_id":"T-01","zone_id":"ZONE_A","reason":"scripted mock B handover"},
  {"action":"start_work","worker_id":"W-06","reason":"scripted mock B work start"}
]}
```

Merge the context fields above into the body. The service independently validates every
step and rejects the whole batch if any step fails. This fixture is an explicitly
scripted test client, not a risk assessment algorithm. See `examples/component_a_demo.py`.

Framework references: [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/),
[FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/).
