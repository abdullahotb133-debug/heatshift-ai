# HeatShift AI — integrated engineering simulator

Deterministic Python 3.11+ synthetic environment, worker/task simulation and versioned
demonstration scenarios. Standard-library simulation core; optional FastAPI/Pydantic HTTP boundary. Existing models
and public APIs are preserved. There is no Component B/C integration, risk classifier,
exposure limit, physiological model or automatic safety reassignment.

## Component A service — completed

Run the integrated authenticated HTTP demonstration:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python examples/component_a_demo.py --output evidence.json
.venv/bin/python -m pytest -q
```

For a persistent API server, export HEATSHIFT_API_TOKEN, then:

```sh
HEATSHIFT_MODE=deployment PYTHONPATH=src .venv/bin/python -m uvicorn heatshift_ai.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Deployment requires a token of at least 32 characters. See `.env.example` and
[handover/startup](COMPONENT_A_HANDOVER.md), [API contract](COMPONENT_A_API_CONTRACT.md),
[OpenAPI](openapi.json), [all endpoint examples](examples/api/endpoint_examples.json),
and [actual verification report](COMPONENT_A_TEST_REPORT.md).
Final verification: **369 tests passed**, plus two matching real HTTP demonstration runs.
B is represented only by an explicitly scripted test client; B/C are not implemented.
Single process/worker only; state and retry cache are in memory. Dockerfile is supplied
as an optional deployment recipe and has not been built here.

## Run simulator CLI

From the repository root (the local deliverable is `outputs/heatshift-ai`):

```sh
PYTHONPATH=src python3 -m heatshift_ai.demo_cli --scenario NORMAL_OPERATION --seed 42 --ticks 12
PYTHONPATH=src python3 -m heatshift_ai.demo_cli --scenario HEAT_ESCALATION --seed 42 --ticks 12 --output heat.json
PYTHONPATH=src python3 -m heatshift_ai.demo_cli --scenario MULTI_ZONE_HEAT --seed 42 --ticks 12
PYTHONPATH=src python3 -m heatshift_ai.demo_cli --scenario RECOVERY --seed 42 --ticks 12
PYTHONPATH=src python3 -m heatshift_ai.demo_cli --scenario NO_ELIGIBLE_REPLACEMENT --seed 42 --ticks 12
PYTHONPATH=src python3 -m heatshift_ai.demo_cli --scenario SENSOR_FAILURE --seed 42 --ticks 4 --failure-mode missing
PYTHONPATH=src python3 -m heatshift_ai.demo_cli --scenario SENSOR_FAILURE --seed 42 --ticks 4 --failure-mode stale
PYTHONPATH=src python3 -m heatshift_ai.demo_cli --scenario SENSOR_FAILURE --seed 42 --ticks 4 --failure-mode invalid --output failure.json --events-output events.json
PYTHONPATH=src python3 examples/integrated_demo.py
```

Default tick size is 10 simulated seconds; `--tick-seconds` overrides it. No sleep or
background time advancement occurs. The existing `python -m heatshift_ai` CLI and
NORMAL/HEATWAVE/RECOVERY ScenarioController remain compatible and retain their original
constant-fixture defaults. Use **demo_cli** or IntegratedSimulationEngine for the new
environmental component. This is an additional interface in the same package, not a
replacement application.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pytest -q
```

No editable install is required for tests; pyproject.toml configures the source path.
See FINAL_VERIFICATION.md for exact executed commands and limitations.

## Environmental component

`EnvironmentalSimulator(seed=..., zones=..., forcing=...)` implements the unchanged
EnvironmentAdapter.observe(zone_id, elapsed_seconds) contract and the existing named
scenario override contract. `sample()` exposes the typed input channels; `observe()`
returns the established EnvironmentObservation with conditions, method and metadata.

ZoneEnvironmentConfig explicitly configures air temperature, relative humidity,
globe temperature, air velocity, **natural** wet-bulb channel, solar load and variability.
Defaults cover ZONE_A/B/C and a shaded cooler REST_ZONE. All zones, including rest,
are configurable; unknown references are rejected.

Generation uses shared slow sinusoidal drivers, small seeded zone phases and smoothstep
thermal forcing. Increasing thermal forcing raises air/globe/natural-wet-bulb channel
values, lowers RH and slightly reduces air speed. Solar globe response differs from
shade. Readings are functions of seed, config and requested time: read order and number
of calls do not change results. No independently sampled per-tick channel noise exists.

**Model boundary:** channel trajectories are physically plausible demo inputs, not a
validated meteorological or heat-transfer model. Natural wet-bulb is its own explicit
simulated channel with a configured nominal value; it is NOT inferred from air/RH,
NOT ordinary psychrometric wet-bulb and NOT a calibrated natural-wet-bulb estimator.
A caller may set that channel to None; WBGT is then unavailable. No estimated-WBGT
method is implemented or falsely claimed validated.

Input validation enforces finite values and broad supported instrument/model ranges:
air/natural wet-bulb -80..80 °C, globe -80..150 °C, RH 0..100%, air velocity 0..100 m/s.
These are input sanity bounds, **not occupational safety limits**. Every generated
sample is validated; extreme custom configurations may be rejected rather than
silently returning invalid temperature channels. RH and velocity are bounded at
physical limits in the synthetic generator. Default/tested configurations are well
inside those limits. Natural wet-bulb is not generally constrained below air temperature
because a naturally ventilated wetted sensor can receive radiant heat.

## WBGT and provenance

WBGT calculation is a pure function in wbgt.py, separated from channel generation:

- No solar load: `0.7*Tnw + 0.3*Tg`.
- Solar load: `0.7*Tnw + 0.2*Tg + 0.1*Ta`.

Sources: [ISO 7243:2017](https://www.iso.org/standard/67188.html) and
[NIOSH 2016-106, section 9.3.2](https://www.cdc.gov/niosh/docs/2016-106/pdfs/2016-106.pdf).
Only the weighting formulas are used. Standard compliance of instruments, placement,
response times or whole-worksite exposure assessment is not asserted.

`EnvironmentalSample.source` is measured or simulated; `WBGTResult.kind` is calculated
or unavailable, independently of input provenance. The simulator always supplies
simulated inputs. A measured-input unit test checks calculation provenance; it is not
a live sensor integration. Calculated-from-simulated WBGT remains explicitly synthetic.
Missing required inputs, unknown solar status, stale or invalid quality produce null
WBGT with a reason, never a substituted estimate. No authoritative WBGT is derived
solely from temperature and humidity. `estimated` is not an emitted classification.

Observation metadata includes generator version, observation provenance, solar state,
quality/reason, original observed-at timestamp, WBGT kind/input source and the explicit
natural-wet-bulb channel method. The top-level observation timestamp always matches
the requested simulation time; stale data retain their older observed-at timestamp
in metadata. Missing/invalid sensor channels are null. Stale synthetic channels retain
the deterministic last-good-time values but have null current WBGT.

## One integrated engine

```python
from heatshift_ai import IntegratedSimulationEngine, EngineCommand

engine = IntegratedSimulationEngine()
engine.initialize()                 # no clock advancement
state = engine.get_state()          # immutable IntegratedState
worker = next(w for w in state.simulation.workers if w.current_task_id)
engine.tick(10)
engine.execute(EngineCommand(action="start_rest", worker_id=worker.worker_id,
                             zone_id="REST_ZONE", reason="explicit demo break"))
engine.tick(10)
engine.pause()
engine.tick(100)                    # no time advancement
engine.resume()
text = engine.export_snapshot()
engine.reset()                     # exact seeded initialization, cleared run history
```

IntegratedState holds the existing canonical SimulationState, matching-zone/time
environment observations and existing TransitionEvents. There is one committed
WorkerStateManager (a SimulationClock/AssignmentManager subtype). A tick prepares a
private transaction copy of that controller and a deepcopy of the in-memory adapter;
only after all commands, observations and validation succeed is the full frame
published. These copies are speculative state, not separately running clocks.
Failures leave the original clock, counters, assignments, events and adapter state
unchanged. No remote-service transactional guarantees are claimed. Custom adapters
must support deepcopy and have no external side effects.

`initialize`, `tick`, `pause`, `resume`, `reset`, `get_state`, `execute`, `execute_batch`
and `export_snapshot` are explicit. Commands are allowlisted and validated by the
existing controllers; consumers cannot mutate frozen SimulationState through the API.
Concurrent engine calls are serialized with a lock. Ordered command replay is
deterministic; simultaneous thread scheduling order is not promised.

EngineConfig accepts existing WorkerConfig and TaskConfig, custom environmental zone
configs and explicit initial assignments. Default population is 10, catalog size 6,
work zones 3 and rest zones 1. Generic models impose no fixed worker/zone counts;
a three-worker/two-zone test verifies custom dimensions. The existing six-definition
catalog contract is retained. Engine worker qualification pools are explicitly
configured from task requirements at generation, never changed during ticks.
Default setup chooses eligible idle/available workers in a stable order, using no
environmental/risk input. Use initial_assignments=() to disable setup assignments or
supply exact AssignmentRequests. Missing eligibility is preserved, not fabricated.

Exposure is simulated active-work environmental exposure **time**, not clinical dose.
It advances even when environment data are missing, because elapsed activity is known;
missing conditions remain missing. Rest/work cumulative and uninterrupted counters
use the existing rules. All established worker commands remain available through
EngineCommand, including explicit rest, task change and availability operations.

## Six versioned scenarios

Definitions live in `src/heatshift_ai/scenario_configs/demo_v1.json`: version, scenario
ID, seed, start time, duration, zone-specific initial/final thermal forcing and
operational/failure parameters. No scenario-specific rule is added to worker/task models.

| Scenario | Reproducible inputs and expected behavior |
| --- | --- |
| NORMAL_OPERATION | Baseline correlated trajectories; stable valid work setup |
| HEAT_ESCALATION | ZONE_A increases smoothly by a configured 6 °C thermal driver over 120 s |
| MULTI_ZONE_HEAT | A/B/C receive distinct 6/3/8 °C drivers; rest stays at its baseline |
| RECOVERY | Work zones start with explicit elevated offsets and trend back to baseline; target inspection worker rests at 40 s and returns at 80 s |
| NO_ELIGIBLE_REPLACEMENT | Explicit script marks all workers qualified for T-04 unavailable and releases its assignment; it stays pending with no eligible available replacement |
| SENSOR_FAILURE | ZONE_A has missing/stale/invalid data during [30,90) s, quality-marked with null WBGT; valid synthetic readings return at 90 s |

These durations and increments are demonstration parameters, not safety advice.
At 120 s, recovery target work/rest totals are 80/40 s. In NO_ELIGIBLE_REPLACEMENT,
qualifications are unchanged and no replacement is assigned automatically.

```python
from heatshift_ai import EngineeringScenarioRunner, load_scenario
runner = EngineeringScenarioRunner(load_scenario("HEAT_ESCALATION", seed=42))
runner.start()
runner.run(12)
first = runner.export_snapshot()
runner.reset()
runner.run(12)
assert runner.export_snapshot() == first
runner.stop()
```

Start initializes explicitly. Step uses only the engine clock; actions split a tick
at exact timestamps, in stable tuple order, and the whole outer tick is atomic.
Start/stop events use simulation timestamps; worker commands have their existing
old/new-state events. Input definitions are separately labeled `scenario_input`, never
sensor observations. Stop cancels queued commands and freezes the current thermal
forcing level while retaining worker history; it does not force workers into a
supposedly safe state. Reset creates a new run with identical inputs and clears the
old run log. Export before reset to retain external history. At configured duration
end, thermal trends hold their endpoint, scripts are exhausted and phase is complete;
explicit ticking may continue. Stopping a sensor-failure scenario ends its injected
fault; no sensor recovery is inferred from risk.

## Snapshots, examples, compatibility and limits

Snapshot top-level fields remain simulation_id, source, simulated_time_seconds, zones,
workers, tasks and events, with assignments/seed/tick size/scenario metadata. Existing
parse_snapshot/validate_snapshot are reused and now recognize the new scenario names.
Environment source/method/quality survive serialization. JSON snapshots are detached
copies; returned domain objects are immutable.

Examples:
- `examples/environmental_payload.json`: complete single-zone environmental payload.
- `examples/engineering_scenarios.json`: all six scenarios at 0,40,80,120 s, including
  complete snapshots and event logs; sensor faults are visible at 40/80 s.
- `examples/integrated_demo.py`: executable work/rest integration demonstration.
- Earlier examples/snapshots remain historical constant-fixture examples.

FINAL_VERIFICATION.md records actual tests and limits. No live sensors, calibrated
weather model, B/C integration, field validation, n8n, Supabase, frontend or network
service was added. In-memory event/observation retention is for demonstrations, not
unbounded production streaming. Python 3.13.5 was exercised; Python 3.11 runtime and
wheel installation remain untested. No line/branch coverage percentage was measured.

## Final engineering review

See [audit](COMPONENT_A_AUDIT.md), [external reference review](COMPONENT_A_REFERENCE_REVIEW.md)
and [improvement plan](COMPONENT_A_IMPROVEMENT_PLAN.md). Current API metadata includes
ISO 8601 simulation-time projections, explicit before/after commit versions and correctly
ordered same-time events. Requests have a configurable 64 KiB body limit. TaskConfig
supports an explicit count with matching definitions; default remains six. The HTTP demo
also proves an unqualified assignment is rejected without changing state.
