"""JSON snapshots with round-trip model/reference validation."""
import json
from dataclasses import replace
from typing import Any

from .assignments import Assignment
from .environment import EnvironmentalCondition, EnvironmentObservation
from .scenarios import ScenarioController, ScenarioName
from .serialization import to_json_value
from .state import SimulationState
from .tasks import Task
from .time import SimulationTime
from .validation import identifier, nonempty, seconds
from .workers import Worker
from .zones import Zone


def _worker(data):
    values = dict(data)
    if not isinstance(values.get('qualifications'), list):
        raise ValueError('worker qualifications must be an array')
    values['qualifications'] = frozenset(values['qualifications'])
    return Worker(**values)


def _task(data):
    values = dict(data)
    for field in ('required_qualifications', 'allowed_zone_ids'):
        if not isinstance(values.get(field), list):
            raise ValueError(f'{field} must be an array')
        values[field] = frozenset(values[field])
    return Task(**values)


def _state(data):
    if data['data_origin'] != 'simulated':
        raise ValueError('state data_origin must be simulated')
    return SimulationState(zones=tuple(Zone(**z) for z in data['zones']),
        workers=tuple(_worker(w) for w in data['workers']), tasks=tuple(_task(t) for t in data['tasks']),
        assignments=tuple(Assignment(**a) for a in data['assignments']),
        time=SimulationTime(**data['time']), random_seed=data['random_seed'])


def validate_snapshot(data: dict[str, Any]) -> SimulationState:
    """Reject malformed counters, references, provenance and observation timing."""
    try:
        identifier(data['simulation_id'], 'simulation_id')
        if data['source'] != 'synthetic_simulator':
            raise ValueError('source must be synthetic_simulator')
        seconds(data['simulated_time_seconds'], 'simulated_time_seconds')
        supported = {s.value for s in ScenarioName} | {'NORMAL_OPERATION', 'HEAT_ESCALATION', 'MULTI_ZONE_HEAT', 'NO_ELIGIBLE_REPLACEMENT', 'SENSOR_FAILURE'}
        if data['scenario'] not in supported:
            raise ValueError('unknown scenario')
        zones = []
        for entry in data['zones']:
            zones.append(Zone(zone_id=entry['zone_id'], kind=entry['kind']))
            env = dict(entry['environment'])
            env['conditions'] = tuple(EnvironmentalCondition(**c) for c in env['conditions'])
            if not isinstance(env['source_metadata'], dict):
                raise ValueError('source_metadata must be an object')
            env['source_metadata'] = tuple(env['source_metadata'].items())
            observation = EnvironmentObservation(**env)
            if observation.zone_id != entry['zone_id'] or observation.elapsed_seconds != data['simulated_time_seconds']:
                raise ValueError('observation zone/time differs from snapshot')
        state = SimulationState(zones=tuple(zones), workers=tuple(_worker(w) for w in data['workers']),
            tasks=tuple(_task(t) for t in data['tasks']), assignments=tuple(Assignment(**a) for a in data['assignments']),
            time=SimulationTime(elapsed_seconds=data['simulated_time_seconds'], tick_seconds=data['tick_seconds']),
            random_seed=data['random_seed'])
        previous = -1
        if not isinstance(data['events'], list):
            raise ValueError('events must be an array')
        for expected_id, event in enumerate(data['events'], 1):
            if type(event['event_id']) is not int or event['event_id'] != expected_id:
                raise ValueError('event IDs must be consecutive integers')
            seconds(event['elapsed_seconds'], 'event elapsed_seconds')
            if not previous <= event['elapsed_seconds'] <= state.time.elapsed_seconds:
                raise ValueError('events must be ordered within snapshot time')
            previous = event['elapsed_seconds']
            nonempty(event['reason'], 'event reason')
            nonempty(event['action'], 'event action')
            identifier(event['worker_id'], 'event worker_id')
            if event['data_origin'] != 'simulated':
                raise ValueError('event data_origin must be simulated')
            for side in ('old_state', 'new_state'):
                history = _state(event[side])
                if history.time.elapsed_seconds != event['elapsed_seconds']:
                    raise ValueError('event snapshot timestamp mismatch')
                if event['worker_id'] not in {w.worker_id for w in history.workers}:
                    raise ValueError('event worker missing from event state')
            if event['worker_id'] not in {w.worker_id for w in state.workers}:
                raise ValueError('event worker missing from current state')
        return state
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'malformed snapshot: {exc}') from exc


def build_snapshot(controller: ScenarioController, *, simulation_id: str = 'SIM-001') -> dict:
    identifier(simulation_id, 'simulation_id')
    state = replace(controller.state)
    observations = controller.read_environment()
    zones = []
    for zone, observation in zip(state.zones, observations):
        env = to_json_value(observation)
        env['source_metadata'] = dict(observation.source_metadata)
        zones.append({'zone_id': zone.zone_id, 'kind': zone.kind.value, 'environment': env})
    snapshot = {'simulation_id': simulation_id, 'source': 'synthetic_simulator',
        'simulated_time_seconds': state.time.elapsed_seconds, 'zones': zones,
        'workers': to_json_value(state.workers), 'tasks': to_json_value(state.tasks),
        'events': to_json_value(controller.events), 'assignments': to_json_value(state.assignments),
        'scenario': controller.name.value, 'random_seed': controller.seed, 'tick_seconds': state.time.tick_seconds}
    validate_snapshot(snapshot)
    return snapshot


def export_snapshot(snapshot: dict) -> str:
    validate_snapshot(snapshot)
    return json.dumps(snapshot, sort_keys=True, allow_nan=False, indent=2)


def parse_snapshot(text: str) -> dict:
    def reject_constant(value):
        raise ValueError(f'nonfinite JSON value: {value}')
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    data = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_pairs)
    validate_snapshot(data)
    return data
