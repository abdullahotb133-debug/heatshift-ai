# HeatShift AI — Worker & Task Simulator

Python 3.11+ deterministic, offline worker/task simulation with explicit assignments,
activity transitions, time tracking, scenario scripts and validated JSON snapshots.
Runtime uses only the Python standard library; tests use pytest.

**Integration status: local simulator and synthetic adapter verified. Real
Environmental/WBGT Simulator integration is BLOCKED because its implementation was
not provided.** No real sensor data, medical predictions, risk classifications,
safety-driven reassignment or external service integrations are included.

## Run from source

From the `outputs/heatshift-ai` directory:

```sh
PYTHONPATH=src python3 -m heatshift_ai --scenario NORMAL --seed 42 --ticks 5 --output examples/snapshots/normal.json
PYTHONPATH=src python3 -m heatshift_ai --scenario HEATWAVE --seed 42 --ticks 5 --output examples/snapshots/heatwave.json
PYTHONPATH=src python3 -m heatshift_ai --scenario RECOVERY --seed 42 --ticks 5 --output examples/snapshots/recovery.json
PYTHONPATH=src python3 -m heatshift_ai --scenario NORMAL --seed 42 --ticks 0 --output examples/snapshots/initial.json
```

The CLI explicitly describes itself as an **offline synthetic** exporter and uses
SyntheticScenarioAdapter only. `--tick-seconds` defaults to 10, `--simulation-id` to
SIM-001. Omit `--output` to print JSON to stdout. Output is the final snapshot; call
the Python API between runs for intermediate snapshots. Output parent folders must
exist. Existing output files are replaced after successful snapshot validation.

## Test

In a new Python 3.11+ environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'pytest>=8,<10'
.venv/bin/python -m pytest -q
```

No package install is needed for tests: pyproject.toml configures the source path.
The actual verified environment is documented in FINAL_VERIFICATION.md. It ran
277 tests, including 1000 ticks per scenario and identical 1000-tick replays.

## Integrated API

```python
from heatshift_ai import (
    ScenarioController, SyntheticScenarioAdapter,
    build_snapshot, export_snapshot, parse_snapshot, validate_snapshot,
)

controller = ScenarioController("RECOVERY", seed=42, tick_seconds=10,
                                adapter_factory=SyntheticScenarioAdapter)
initial = build_snapshot(controller)  # adapter read at t=0; no time advancement
controller.run(5)
snapshot = build_snapshot(controller, simulation_id="SIM-001")
encoded = export_snapshot(snapshot)
parsed = parse_snapshot(encoded)
validated_state = validate_snapshot(parsed)
controller.reset()
controller.run(5)
assert export_snapshot(build_snapshot(controller)) == encoded
```

The controller requires an explicit adapter factory. The factory must return a
fresh, isolated adapter on reset. Scenario execution is single-threaded; do not
mutate configuration or call run/reset concurrently. Identical config, seed, scripts,
Python runtime and deterministic adapter yield identical snapshots.

## Snapshot contract

Required top-level fields are `simulation_id`, `source: "synthetic_simulator"`,
`simulated_time_seconds`, `zones`, `workers`, `tasks`, and `events`. Additional fields
are `assignments`, `scenario`, `random_seed`, and `tick_seconds`, allowing references
and timing to be reconstructed and checked. All configured workers/tasks are included.

Each zone contains its ID/kind and an `environment` observation with:

- matching zone ID and integer elapsed seconds;
- nullable `wbgt_celsius` and explicit `source` (`simulated` or `measured`);
- `conditions`: supplied name/value/unit records, e.g. air_temperature/35/degC;
- nullable `method` and a `source_metadata` string-key/string-value object.

Conditions and metadata are taken from the adapter, never inferred from WBGT.
Missing conditions are an empty array, missing method/WBGT are null, missing metadata
is an empty object. SyntheticScenarioAdapter supplies constant WBGT fixtures only,
so sample conditions are empty; this does not imply real atmospheric data was read.
The typed adapter representation uses immutable tuples for conditions and metadata;
the snapshot maps metadata to a JSON object without changing its values.

The top-level source labels the simulation. Each environment observation retains
its own provenance: synthetic values are never labeled physical measurements.
A real adapter could supply measured observations without relabeling them, but no
actual measured integration has been exercised. Metadata describes the provider's
method; it is not independently validated scientific evidence.

`build_snapshot` reads every zone at the current simulated time and validates the
result. `validate_snapshot` reconstructs the existing typed models to check IDs,
enums, durations, qualifications, assignment exclusivity, worker/task links and
zone references. It also checks observation timestamps and event references/order.
`parse_snapshot` rejects malformed JSON, duplicate keys and nonfinite constants.
This is consistency validation, not proof that a historical event was authorized
or that a supplied environmental algorithm is scientifically valid.

## Environment adapter boundary

EnvironmentAdapter defines `observe(zone_id=..., elapsed_seconds=...)` returning an
EnvironmentObservation. Stage 8 adds optional conditions/method/source metadata;
old adapters returning only the original fields remain compatible.

ScenarioEnvironmentAdapter additionally defines
`request_scenario(EnvironmentScenarioRequest(...))` with scenario name, seed,
request time and zone IDs. NORMAL requests baseline, HEATWAVE elevated, RECOVERY
recovery conditions. Unsupported overrides must raise, not silently succeed.
Concrete parameter mapping and upstream reset behavior require the missing real
simulator. Existing WBGT calculations have not been modified or reimplemented.

The selected profile is requested once before running/reading. Reads validate zone
and timestamp. The local synthetic adapter has arbitrary constant fixture WBGT
values NORMAL=25, HEATWAVE=32, RECOVERY=23 °C, method
`constant_fixture_not_wbgt_calculation`. These are not forecasts, sensor readings,
occupational limits or physiological estimates. Test adapters additionally exercise
condition/metadata transport and missing values; they do not establish real integration.

A run or read failure stops the controller and requires explicit reset. No retry,
external rollback or automatic synthetic fallback is attempted. Prior successful
steps remain inspectable. A failed read may follow already advanced simulation time.

## Workers, tasks, assignments and activity

WorkerSimulator defaults to 10 fictional workers W-01 through W-10. WorkerConfig
centralizes immutable qualification pools, clothing, acclimatization, zones and
initial status pairs. A local seeded RNG provides variation without modifying the
global RNG. Names and IDs are stable. No clinical measurements are generated.

TaskSimulator contains six configurable reusable TaskDefinitions: Site Inspection,
Material Handling, Equipment Operation, Reinforcement Installation, Concrete
Placement and Surveying. Qualitative workload labels are illustrative; metabolic
rates default to null. Tasks begin pending/unassigned. TaskConfig validates known
qualification and work-zone references. Definitions do not contain execution state;
new_task() makes a separate Task snapshot. Specialized task skills are absent from
the default Stage 2 population unless explicitly configured.

AssignmentManager validates eligibility, exclusive assignment and zones before one
atomic state replacement. Assignment reserves work as ASSIGNED/IDLE. Explicit
unassignment releases the task to PENDING, clears reciprocal references and preserves
cumulative history. Resting/unavailable workers cannot receive assignments.

WorkerStateManager adds the following explicit worker commands, each requiring a
nonblank reason. Successful commands append one immutable event containing action,
worker ID, old/new complete states, reason and simulated timestamp. Rejected commands
leave both state and events unchanged.

| Command | Preconditions and effect |
| --- | --- |
| start_work | Idle/available, valid qualified reservation; task becomes in progress |
| stop_work | Working; release task and become idle |
| start_rest | Idle/working, valid rest zone; release any task, become resting/unavailable |
| end_rest | Resting; become idle/available, retain current location |
| change_zone | Known different zone; assignment must allow it; resting stays in rest zone |
| change_task | Existing assignment, eligible different pending task; replace atomically |
| mark_unavailable | Available; release task and stop work if needed |
| mark_available | Unavailable and not resting; does not assign/start a task |

Use the same controller for state changes and ticks. Assignment APIs remain available
and emit events on WorkerStateManager. No command is triggered by environmental risk.
End-rest availability is an explicit setup choice, not a medical clearance.

## Time and history

`tick(delta_seconds)` advances positive integer seconds, defaulting to the configured
10-second interval. Construction never advances time. No real-time sleeping occurs.
Work/exposure grows only while WORKING in a WORK zone; rest grows only while RESTING.
Exposure is environmental exposure time, **not clinical heat dose**. The read-only
`work_elapsed_seconds` alias uses the canonical serialized `exposure_elapsed_seconds`.

Current work/rest periods are separate from cumulative counters. Stopping or resting
ends the work period; end_rest ends the rest period. Work-to-work task/zone changes
preserve uninterrupted duration. Pause/resume does not advance or catch up time.
Clock reset restores its exact configured initial snapshot and resumes it;
WorkerStateManager also clears its transition log. Export before reset to retain
history externally. There is no automatic task completion or safety scheduler.

## Scenarios and scripts

Scenario setup explicitly gives the first six demo workers their designated task's
skills, assigns W-01/T-01 through W-06/T-06 and starts them in allowed zones. This
happens once as configuration before time advances, not during ordinary ticks.
The remaining four workers stay idle. All scenarios share this setup and retain
seeded clothing/acclimatization variation. Twelve setup events occur at second zero.

NORMAL continues work. HEATWAVE only changes the environment request; it makes no
worker decisions. RECOVERY scripts W-01 to rest at second 20, then end rest, assign
T-01 in ZONE_A and start work at second 40. These demo times are not safety advice.
After 50 seconds W-01 has 30 seconds work, 20 rest and 10 consecutive work.

Pass a tuple of ScriptedAction objects to replace default actions. They specify an
integer timestamp, worker command, worker ID, reason and required task/zone arguments.
Stable input order resolves equal timestamps. Ticks split at off-grid action times;
endpoint actions execute before observations. `run(0)` is a no-op. Repeated run calls
continue without duplicating events. Reset recreates the seeded setup, fresh adapter,
initial setup events and script cursor, clearing observations/failure state.

## Deliverables and limitations

- Source: src/heatshift_ai; tests: tests; CLI: python -m heatshift_ai.
- Examples: examples/snapshots/{initial,normal,heatwave,recovery}.json.
- Final results and exact verified commands: FINAL_VERIFICATION.md.
- Historical stage decisions: STAGE1_STATUS.md through STAGE8_STATUS.md.

Snapshots retain complete event states and scenarios retain observation history in
memory; streaming persistence and production-scale retention are not implemented.
The exercised runtime was Python 3.13.5. Python 3.11, installed-wheel packaging and
real environmental integration were not tested. No numerical coverage percentage
was collected. No n8n, Supabase, dashboard or external service dependency exists.
