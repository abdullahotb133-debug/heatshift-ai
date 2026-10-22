"""Transactional in-memory integration of the existing domain controllers."""
from copy import copy, deepcopy
from dataclasses import dataclass, field, replace
from threading import RLock
from typing import Callable

from .assignment_manager import AssignmentRequest
from .environment import EnvironmentObservation
from .environmental_simulator import EnvironmentalSimulator, default_environment_zones
from .enums import WorkStatus, AvailabilityStatus
from .serialization import to_json_value
from .snapshots import export_snapshot as encode_snapshot
from .state import SimulationState
from .task_simulator import TaskConfig, TaskSimulator
from .time import SimulationTime
from .transitions import WorkerStateManager, TransitionEvent
from .validation import identifier, nonempty, seconds
from .worker_simulator import WorkerConfig, WorkerSimulator, InitialWorkerStatus


_ALLOWED = {'assign_task','unassign_task','start_task','start_work','stop_work','start_rest',
            'end_rest','change_zone','change_task','mark_unavailable','mark_available'}


@dataclass(frozen=True, kw_only=True)
class EngineCommand:
    action: str
    reason: str
    worker_id: str | None = None
    task_id: str | None = None
    zone_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.action,str) or self.action not in _ALLOWED:
            raise ValueError('unsupported engine command')
        nonempty(self.reason,'reason')
        for name in ('worker_id','task_id','zone_id'):
            if getattr(self,name) is not None:
                identifier(getattr(self,name),name)


def _worker_config():
    tasks=TaskSimulator().list_tasks()
    return WorkerConfig(qualification_profiles=tuple(t.required_qualifications for t in tasks),
        initial_statuses=(InitialWorkerStatus(work_status='idle',availability_status='available'),))


@dataclass(frozen=True, kw_only=True)
class EngineConfig:
    seed: int = 0
    simulation_id: str = 'SIM-001'
    tick_seconds: int = 10
    worker_config: WorkerConfig = field(default_factory=_worker_config)
    task_config: TaskConfig = field(default_factory=TaskConfig)
    environment_zones: tuple = field(default_factory=default_environment_zones)
    # None: explicit deterministic eligible setup; empty tuple: no assignments.
    initial_assignments: tuple[AssignmentRequest, ...] | None = None
    start_assigned_work: bool = True

    def __post_init__(self):
        if type(self.seed) is not int: raise ValueError('seed must be integer')
        identifier(self.simulation_id,'simulation_id')
        seconds(self.tick_seconds,'tick_seconds',positive=True)
        if not isinstance(self.worker_config,WorkerConfig) or not isinstance(self.task_config,TaskConfig):
            raise ValueError('worker_config/task_config must use existing configuration models')
        EnvironmentalSimulator(seed=self.seed,zones=self.environment_zones)
        if {z.zone_id for z in self.environment_zones}!={z.zone_id for z in self.task_config.zones}:
            raise ValueError('environment and domain zone sets must match')
        if self.initial_assignments is not None and (not isinstance(self.initial_assignments,tuple) or any(not isinstance(a,AssignmentRequest) for a in self.initial_assignments)):
            raise ValueError('initial_assignments must be tuple of AssignmentRequest')
        if type(self.start_assigned_work) is not bool:
            raise ValueError('start_assigned_work must be bool')


@dataclass(frozen=True, kw_only=True)
class IntegratedState:
    simulation: SimulationState
    environment: tuple[EnvironmentObservation, ...]
    events: tuple[TransitionEvent, ...]
    paused: bool = False

    def __post_init__(self):
        if not isinstance(self.simulation,SimulationState): raise ValueError('simulation must be SimulationState')
        if not isinstance(self.environment,tuple): raise ValueError('environment must be tuple')
        ids=[]
        for obs in self.environment:
            if not isinstance(obs,EnvironmentObservation): raise ValueError('invalid environment observation')
            if obs.elapsed_seconds!=self.simulation.time.elapsed_seconds:
                raise ValueError('environment timestamp must match canonical simulation clock')
            ids.append(obs.zone_id)
        if len(set(ids))!=len(ids) or set(ids)!={z.zone_id for z in self.simulation.zones}:
            raise ValueError('one environment observation per configured zone is required')


class IntegratedSimulationEngine:
    """One committed WorkerStateManager/SimulationClock; staged copies are transactions.

    Environment adapters must be deepcopy-able in-memory adapters. External service
    side effects are outside this transaction contract and are not supported here.
    """
    def __init__(self, config: EngineConfig | None = None, *, environment_factory: Callable | None = None):
        self.config=EngineConfig() if config is None else config
        if not isinstance(self.config,EngineConfig): raise ValueError('config must be EngineConfig')
        self._factory=environment_factory or (lambda:EnvironmentalSimulator(seed=self.config.seed,zones=self.config.environment_zones))
        if not callable(self._factory): raise ValueError('environment_factory must be callable')
        self._lock=RLock()
        self._frame=None
        self._manager=None
        self._environment=None

    def _require(self):
        if self._frame is None: raise ValueError('initialize engine before use')

    @staticmethod
    def _read(adapter,state):
        result=[]
        for zone in state.zones:
            observation=adapter.observe(zone_id=zone.zone_id,elapsed_seconds=state.time.elapsed_seconds)
            if not isinstance(observation,EnvironmentObservation) or observation.zone_id!=zone.zone_id:
                raise ValueError('adapter returned wrong zone or invalid observation')
            result.append(observation)
        return tuple(result)

    def _create(self):
        config=self.config
        workers=WorkerSimulator(config=config.worker_config,seed=config.seed).list_workers()
        tasks=TaskSimulator(config=config.task_config).list_tasks()
        state=SimulationState(zones=config.task_config.zones,workers=workers,tasks=tasks,
                              time=SimulationTime(tick_seconds=config.tick_seconds),random_seed=config.seed)
        manager=WorkerStateManager(state)
        requests=config.initial_assignments
        if requests is None:
            chosen=[]; used=set()
            # Stable setup only; no environmental data or risk-based eligibility.
            for task in sorted(tasks,key=lambda t:(-len(t.required_qualifications),t.task_id)):
                candidates=[w for w in workers if w.worker_id not in used and w.work_status==WorkStatus.IDLE
                    and w.availability_status==AvailabilityStatus.AVAILABLE and task.required_qualifications<=w.qualifications]
                candidates.sort(key=lambda w:(len(w.qualifications-task.required_qualifications),w.worker_id))
                if candidates:
                    w=candidates[0]; used.add(w.worker_id)
                    chosen.append(AssignmentRequest(worker_id=w.worker_id,task_id=task.task_id,zone_id=sorted(task.allowed_zone_ids)[0]))
            requests=tuple(chosen)
        for request in requests:
            manager.assign_task(worker_id=request.worker_id,task_id=request.task_id,zone_id=request.zone_id,reason='explicit deterministic engine setup')
            if config.start_assigned_work:
                manager.start_work(worker_id=request.worker_id,reason='explicit engine work start')
        adapter=deepcopy(self._factory())
        observations=self._read(adapter,manager.state)
        frame=IntegratedState(simulation=manager.state,environment=observations,events=manager.events)
        return manager,adapter,frame

    def initialize(self):
        with self._lock:
            if self._frame is not None: raise ValueError('already initialized; use reset')
            self._manager,self._environment,self._frame=self._create()
            return self._frame

    def reset(self):
        with self._lock:
            candidate=self._create()
            self._manager,self._environment,self._frame=candidate
            return self._frame

    def get_state(self):
        with self._lock:
            self._require()
            return self._frame

    def pause(self):
        with self._lock:
            self._require(); self._manager.pause()
            self._frame=replace(self._frame,paused=True)
            return self._frame

    def resume(self):
        with self._lock:
            self._require(); self._manager.resume()
            self._frame=replace(self._frame,paused=False)
            return self._frame

    def _fork_manager(self):
        manager=copy(self._manager)
        manager._lock=RLock()
        return manager

    @staticmethod
    def _command(manager, command):
        if not isinstance(command,EngineCommand): raise ValueError('command must be EngineCommand')
        args={k:getattr(command,k) for k in ('reason','worker_id','task_id','zone_id') if getattr(command,k) is not None}
        try:
            getattr(manager,command.action)(**args)
        except TypeError as exc:
            raise ValueError(f'invalid arguments for {command.action}: {exc}') from exc

    def execute(self, command: EngineCommand):
        return self.execute_batch((command,))

    def execute_batch(self, commands: tuple[EngineCommand,...]):
        with self._lock:
            self._require()
            if not isinstance(commands,tuple): raise ValueError('commands must be tuple')
            candidate=self._fork_manager()
            for command in commands: self._command(candidate,command)
            frame=IntegratedState(simulation=candidate.state,environment=self._frame.environment,
                                  events=candidate.events,paused=self._frame.paused)
            self._manager,self._frame=candidate,frame
            return frame

    def tick(self, delta_seconds=None):
        return self.advance(delta_seconds,())

    def advance(self, delta_seconds, scheduled: tuple[tuple[int,EngineCommand],...]):
        """Atomic outer tick including any timestamped scripted commands."""
        with self._lock:
            self._require()
            delta=self.config.tick_seconds if delta_seconds is None else delta_seconds
            seconds(delta,'delta_seconds',positive=True)
            if self._frame.paused: return self._frame
            if not isinstance(scheduled,tuple): raise ValueError('scheduled must be tuple')
            start=self._frame.simulation.time.elapsed_seconds; end=start+delta
            last=start
            for at,command in scheduled:
                seconds(at,'action time')
                if not last<=at<=end: raise ValueError('scheduled commands must be ordered within this tick')
                if not isinstance(command,EngineCommand): raise ValueError('scheduled command must be EngineCommand')
                last=at
            candidate=self._fork_manager()
            adapter=deepcopy(self._environment)
            for at,command in scheduled:
                now=candidate.state.time.elapsed_seconds
                if at>now: candidate.tick(at-now)
                self._command(candidate,command)
            now=candidate.state.time.elapsed_seconds
            if now<end: candidate.tick(end-now)
            frame=IntegratedState(simulation=candidate.state,environment=self._read(adapter,candidate.state),events=candidate.events)
            self._manager,self._environment,self._frame=candidate,adapter,frame
            return frame

    def replace_environment(self, adapter):
        """Explicit provider/profile change; current time and worker state preserved."""
        with self._lock:
            self._require()
            candidate=deepcopy(adapter)
            frame=replace(self._frame,environment=self._read(candidate,self._frame.simulation))
            self._environment,self._frame=candidate,frame
            return frame

    def snapshot(self, *, scenario='NORMAL', scenario_input=None):
        with self._lock:
            frame=self.get_state(); state=frame.simulation
            zones=[]
            env={o.zone_id:o for o in frame.environment}
            for zone in state.zones:
                obs=env[zone.zone_id]; row=to_json_value(obs); row['source_metadata']=dict(obs.source_metadata)
                zones.append({'zone_id':zone.zone_id,'kind':zone.kind.value,'environment':row})
            result={'simulation_id':self.config.simulation_id,'source':'synthetic_simulator',
                'simulated_time_seconds':state.time.elapsed_seconds,'zones':zones,
                'workers':to_json_value(state.workers),'tasks':to_json_value(state.tasks),
                'assignments':to_json_value(state.assignments),'events':to_json_value(frame.events),
                'random_seed':self.config.seed,'tick_seconds':state.time.tick_seconds,'scenario':scenario,
                'paused':frame.paused}
            if scenario_input is not None: result['scenario_input']=to_json_value(scenario_input)
            return result

    def export_snapshot(self):
        return encode_snapshot(self.snapshot())
