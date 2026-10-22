"""Deterministic demonstration scenarios; environmental integration is explicit."""
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Callable, Protocol
import logging

from .environment import EnvironmentAdapter, EnvironmentObservation
from .enums import MeasurementSource
from .serialization import to_json
from .state import SimulationState
from .task_simulator import TaskSimulator
from .time import SimulationTime
from .transitions import WorkerStateManager
from .validation import enum_value, identifier, nonempty, seconds
from .worker_simulator import InitialWorkerStatus, WorkerConfig, WorkerSimulator

logger = logging.getLogger(__name__)


class ScenarioName(StrEnum):
    NORMAL = 'NORMAL'
    HEATWAVE = 'HEATWAVE'
    RECOVERY = 'RECOVERY'


@dataclass(frozen=True, kw_only=True)
class EnvironmentScenarioRequest:
    scenario: ScenarioName
    seed: int
    elapsed_seconds: int
    zone_ids: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, 'scenario', enum_value(self.scenario, ScenarioName, 'scenario'))
        if type(self.seed) is not int:
            raise ValueError('seed must be an integer')
        seconds(self.elapsed_seconds, 'elapsed_seconds')
        if not isinstance(self.zone_ids, tuple) or not self.zone_ids:
            raise ValueError('zone_ids must be a non-empty tuple')
        for zone_id in self.zone_ids:
            identifier(zone_id, 'zone_id')
        if len(set(self.zone_ids)) != len(self.zone_ids):
            raise ValueError('zone_ids must be unique')


class ScenarioEnvironmentAdapter(EnvironmentAdapter, Protocol):
    def request_scenario(self, request: EnvironmentScenarioRequest) -> None:
        """Apply named conditions or raise NotImplementedError; never silently ignore.

        NORMAL=baseline, HEATWAVE=elevated, RECOVERY=recovery conditions.
        Mapping to actual simulator parameters belongs to the concrete adapter.
        A fresh instance from the factory must isolate each reset/replay run.
        """
        ...


class SyntheticScenarioAdapter:
    """TEST/DEMO fixture only; constant WBGT inputs, no environmental model.

    25/32/23 Celsius are arbitrary test inputs, not thresholds or forecasts.
    """
    def __init__(self):
        self.requests: tuple[EnvironmentScenarioRequest, ...] = ()

    def request_scenario(self, request: EnvironmentScenarioRequest) -> None:
        if not isinstance(request, EnvironmentScenarioRequest):
            raise ValueError('request must be EnvironmentScenarioRequest')
        self.requests += (request,)

    def observe(self, *, zone_id: str, elapsed_seconds: int) -> EnvironmentObservation:
        seconds(elapsed_seconds, 'elapsed_seconds')
        applicable = [r for r in self.requests if r.elapsed_seconds <= elapsed_seconds and zone_id in r.zone_ids]
        if not applicable:
            raise LookupError('no environmental scenario request for zone/time')
        request = applicable[-1]
        value = {ScenarioName.NORMAL: 25.0, ScenarioName.HEATWAVE: 32.0, ScenarioName.RECOVERY: 23.0}[request.scenario]
        return EnvironmentObservation(zone_id=zone_id, elapsed_seconds=elapsed_seconds,
                                      wbgt_celsius=value, source=MeasurementSource.SIMULATED,
                                      method='constant_fixture_not_wbgt_calculation',
                                      source_metadata=(('provider', 'SyntheticScenarioAdapter'),
                                                       ('profile', request.scenario.value)))


_ACTION_FIELDS = {
    'start_work': (), 'stop_work': (), 'start_rest': ('zone_id',), 'end_rest': (),
    'change_zone': ('zone_id',), 'change_task': ('task_id',),
    'mark_unavailable': (), 'mark_available': (), 'assign_task': ('task_id',),
}


@dataclass(frozen=True, kw_only=True)
class ScriptedAction:
    elapsed_seconds: int
    action: str
    worker_id: str
    reason: str
    task_id: str | None = None
    zone_id: str | None = None

    def __post_init__(self):
        seconds(self.elapsed_seconds, 'elapsed_seconds')
        if not isinstance(self.action, str) or self.action not in _ACTION_FIELDS:
            raise ValueError('unsupported scripted action')
        identifier(self.worker_id, 'worker_id')
        nonempty(self.reason, 'reason')
        for name in ('task_id', 'zone_id'):
            value = getattr(self, name)
            if name in _ACTION_FIELDS[self.action] and value is None:
                raise ValueError(f'{self.action} requires {name}')
            if value is not None:
                identifier(value, name)
                if name not in _ACTION_FIELDS[self.action] and not (name == 'zone_id' and self.action in ('assign_task', 'change_task')):
                    raise ValueError(f'{self.action} does not accept {name}')


def _initial(seed: int, tick_seconds: int) -> WorkerStateManager:
    catalog = TaskSimulator()
    config = WorkerConfig(initial_statuses=(InitialWorkerStatus(work_status='idle', availability_status='available'),))
    workers = list(WorkerSimulator(seed=seed, config=config).list_workers())
    # Explicit demo roster: first six workers have exactly their designated task skills.
    # This is initial scenario configuration, never a runtime qualification change.
    for i, task in enumerate(catalog.list_tasks()):
        workers[i] = replace(workers[i], qualifications=task.required_qualifications,
                             current_zone_id=sorted(task.allowed_zone_ids)[0])
    manager = WorkerStateManager(SimulationState(workers=tuple(workers), tasks=catalog.list_tasks(),
        zones=catalog.config.zones, time=SimulationTime(tick_seconds=tick_seconds), random_seed=seed))
    for worker, task in zip(workers, catalog.list_tasks()):
        manager.assign_task(worker_id=worker.worker_id, task_id=task.task_id, reason='explicit scenario setup')
        manager.start_work(worker_id=worker.worker_id, reason='explicit scenario start')
    return manager


def _recovery_script() -> tuple[ScriptedAction, ...]:
    return (
        ScriptedAction(elapsed_seconds=20, action='start_rest', worker_id='W-01', zone_id='REST_ZONE', reason='scripted recovery break'),
        ScriptedAction(elapsed_seconds=40, action='end_rest', worker_id='W-01', reason='scripted break end'),
        ScriptedAction(elapsed_seconds=40, action='assign_task', worker_id='W-01', task_id='T-01', zone_id='ZONE_A', reason='scripted return assignment'),
        ScriptedAction(elapsed_seconds=40, action='start_work', worker_id='W-01', reason='scripted return to work'),
    )


class ScenarioController:
    def __init__(self, name: ScenarioName | str, *, seed: int = 0, tick_seconds: int = 10,
                 adapter_factory: Callable[[], ScenarioEnvironmentAdapter],
                 actions: tuple[ScriptedAction, ...] | None = None):
        self.name = enum_value(name, ScenarioName, 'scenario')
        if type(seed) is not int:
            raise ValueError('seed must be an integer')
        seconds(tick_seconds, 'tick_seconds', positive=True)
        if not callable(adapter_factory):
            raise ValueError('adapter_factory must be callable')
        if actions is None:
            actions = _recovery_script() if self.name == ScenarioName.RECOVERY else ()
        if not isinstance(actions, tuple) or any(not isinstance(a, ScriptedAction) for a in actions):
            raise ValueError('actions must be a tuple of ScriptedAction models')
        self.seed, self.tick_seconds = seed, tick_seconds
        self.actions = tuple(sorted(actions, key=lambda a: a.elapsed_seconds))  # stable tie order
        self._factory = adapter_factory
        self._adapter = None
        self.reset()

    @property
    def state(self):
        return self._manager.state

    @property
    def events(self):
        return self._manager.events

    def reset(self):
        adapter = self._factory()
        if adapter is self._adapter:
            raise ValueError('adapter_factory must return a fresh instance for reset')
        if not callable(getattr(adapter, 'request_scenario', None)) or not callable(getattr(adapter, 'observe', None)):
            raise ValueError('adapter requires request_scenario and observe; real override integration pending')
        manager = _initial(self.seed, self.tick_seconds)
        self._adapter, self._manager = adapter, manager
        self._cursor = 0
        self._requested = False
        self._failed = False
        self.requests = ()
        self.observations = ()
        return self.state

    def _due(self):
        now = self.state.time.elapsed_seconds
        while self._cursor < len(self.actions) and self.actions[self._cursor].elapsed_seconds == now:
            action = self.actions[self._cursor]
            args = {'worker_id': action.worker_id, 'reason': action.reason}
            for field in ('task_id', 'zone_id'):
                if getattr(action, field) is not None:
                    args[field] = getattr(action, field)
            getattr(self._manager, action.action)(**args)
            self._cursor += 1

    def run(self, ticks: int):
        seconds(ticks, 'ticks')
        if self._failed:
            raise RuntimeError('scenario failed; reset before replay; no automatic retries')
        if ticks == 0:
            return self.state
        try:
            if not self._requested:
                request = EnvironmentScenarioRequest(scenario=self.name, seed=self.seed,
                    elapsed_seconds=self.state.time.elapsed_seconds, zone_ids=tuple(z.zone_id for z in self.state.zones))
                self._adapter.request_scenario(request)
                self.requests = (request,)
                self._requested = True
            for _ in range(ticks):
                target = self.state.time.elapsed_seconds + self.tick_seconds
                self._due()
                while self._cursor < len(self.actions) and self.actions[self._cursor].elapsed_seconds <= target:
                    at = self.actions[self._cursor].elapsed_seconds
                    if at > self.state.time.elapsed_seconds:
                        self._manager.tick(at - self.state.time.elapsed_seconds)
                    self._due()
                if self.state.time.elapsed_seconds < target:
                    self._manager.tick(target - self.state.time.elapsed_seconds)
                batch = []
                for zone in self.state.zones:
                    observation = self._adapter.observe(zone_id=zone.zone_id, elapsed_seconds=target)
                    if not isinstance(observation, EnvironmentObservation) or observation.zone_id != zone.zone_id or observation.elapsed_seconds != target:
                        raise ValueError('adapter observation must match requested zone/time')
                    batch.append(observation)
                self.observations += tuple(batch)
        except Exception:
            self._failed = True
            logger.exception('scenario stopped without retry; reset required')
            raise
        return self.state

    def read_environment(self) -> tuple[EnvironmentObservation, ...]:
        """Read all current zones, including at time zero, without advancing time.

        Applies the selected profile once if needed. Does not execute queued scripts.
        """
        if self._failed:
            raise RuntimeError('scenario failed; reset before reading environment')
        try:
            if not self._requested:
                request = EnvironmentScenarioRequest(scenario=self.name, seed=self.seed,
                    elapsed_seconds=self.state.time.elapsed_seconds,
                    zone_ids=tuple(z.zone_id for z in self.state.zones))
                self._adapter.request_scenario(request)
                self.requests = (request,)
                self._requested = True
            observations = tuple(self._adapter.observe(zone_id=z.zone_id,
                elapsed_seconds=self.state.time.elapsed_seconds) for z in self.state.zones)
            for zone, observation in zip(self.state.zones, observations):
                if not isinstance(observation, EnvironmentObservation) or observation.zone_id != zone.zone_id or observation.elapsed_seconds != self.state.time.elapsed_seconds:
                    raise ValueError('adapter observation must match requested zone/time')
            return observations
        except Exception:
            self._failed = True
            logger.exception('environment read failed; reset required')
            raise

    def export_json(self):
        return to_json({'scenario': self.name, 'seed': self.seed, 'state': self.state,
            'events': self.events, 'actions': self.actions, 'requests': self.requests,
            'observations': self.observations, 'failed': self._failed,
            'environment_adapter': type(self._adapter).__name__, 'data_origin': 'simulated'})
