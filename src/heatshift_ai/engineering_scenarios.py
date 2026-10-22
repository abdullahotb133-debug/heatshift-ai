"""Versioned scenario inputs; no worker risk decisions or alternate clock."""
from dataclasses import dataclass, replace
from enum import StrEnum
from importlib.resources import files
import json

from .environmental_simulator import EnvironmentalSimulator, EnvironmentalForcing
from .integrated_engine import EngineConfig, EngineCommand, IntegratedSimulationEngine
from .serialization import to_json_value
from .snapshots import export_snapshot as encode_snapshot
from .validation import seconds, identifier, enum_value


class EngineeringScenarioName(StrEnum):
    NORMAL_OPERATION='NORMAL_OPERATION'
    HEAT_ESCALATION='HEAT_ESCALATION'
    MULTI_ZONE_HEAT='MULTI_ZONE_HEAT'
    RECOVERY='RECOVERY'
    NO_ELIGIBLE_REPLACEMENT='NO_ELIGIBLE_REPLACEMENT'
    SENSOR_FAILURE='SENSOR_FAILURE'


@dataclass(frozen=True, kw_only=True)
class ScenarioDefinition:
    scenario_id: EngineeringScenarioName
    seed: int = 42
    version: int = 1
    start_seconds: int = 0
    duration_seconds: int = 120
    zone_heat: tuple[tuple[str,float,float],...] = ()
    operation: str = 'none'
    target_task_id: str | None = None
    rest_zone_id: str | None = None
    failure_zone_id: str | None = None
    failure_start_seconds: int = 30
    failure_duration_seconds: int = 60
    failure_mode: str = 'missing'

    def __post_init__(self):
        object.__setattr__(self,'scenario_id',enum_value(self.scenario_id,EngineeringScenarioName,'scenario_id'))
        if type(self.version) is not int or self.version!=1: raise ValueError('unsupported scenario version')
        if type(self.seed) is not int: raise ValueError('seed must be integer')
        self.forcing()
        if self.operation not in ('none','rest_cycle','unavailable_for_task'):
            raise ValueError('unsupported scenario operation')
        if self.operation!='none': identifier(self.target_task_id,'target_task_id')
        if self.operation=='rest_cycle':
            identifier(self.rest_zone_id,'rest_zone_id')
            if self.duration_seconds<3: raise ValueError('rest_cycle requires at least 3 seconds')
        if self.failure_zone_id is not None:
            if not self.start_seconds <= self.failure_start_seconds < self.failure_start_seconds+self.failure_duration_seconds <= self.start_seconds+self.duration_seconds:
                raise ValueError('sensor failure interval must be inside scenario duration')

    def forcing(self):
        return EnvironmentalForcing(start_seconds=self.start_seconds,duration_seconds=self.duration_seconds,
            zone_heat=self.zone_heat,failure_zone_id=self.failure_zone_id,
            failure_start_seconds=self.failure_start_seconds,failure_duration_seconds=self.failure_duration_seconds,
            failure_mode=self.failure_mode)


def load_scenario(name: str, *, seed: int | None = None) -> ScenarioDefinition:
    name=enum_value(name,EngineeringScenarioName,'scenario_id')
    data=json.loads(files('heatshift_ai').joinpath('scenario_configs/demo_v1.json').read_text())
    for row in data['scenarios']:
        if row['scenario_id']==name:
            values=dict(row,version=data['version'])
            values['zone_heat']=tuple(tuple(r) for r in values['zone_heat'])
            if seed is not None: values['seed']=seed
            return ScenarioDefinition(**values)
    raise ValueError(f'no scenario definition for {name}')


@dataclass(frozen=True, kw_only=True)
class ScenarioLifecycleEvent:
    event_id: int
    elapsed_seconds: int
    action: str
    scenario_id: str
    source: str = 'scripted_scenario_input'


class EngineeringScenarioRunner:
    def __init__(self, definition: ScenarioDefinition, *, config: EngineConfig | None = None):
        if not isinstance(definition,ScenarioDefinition): raise ValueError('definition must be ScenarioDefinition')
        self.definition=definition
        self.config=EngineConfig(seed=definition.seed) if config is None else config
        if self.config.seed!=definition.seed: raise ValueError('scenario and engine seed must match')
        self.engine=None
        self._script=()
        self._cursor=0
        self._running=False
        self._events=()

    @property
    def events(self): return self._events

    def _script_for(self, engine):
        d=self.definition
        state=engine.get_state().simulation
        if d.operation=='none': return ()
        task=next((t for t in state.tasks if t.task_id==d.target_task_id),None)
        if task is None: raise ValueError('scenario target task not found')
        if d.operation=='unavailable_for_task':
            return tuple((d.start_seconds,EngineCommand(action='mark_unavailable',worker_id=w.worker_id,
                          reason='scripted absence of qualified workers; not a risk decision'))
                         for w in state.workers if task.required_qualifications<=w.qualifications and w.availability_status=='available')
        if task.assigned_worker_id is None: raise ValueError('rest_cycle requires assigned target task')
        worker=next(w for w in state.workers if w.worker_id==task.assigned_worker_id)
        rest=d.start_seconds+d.duration_seconds//3
        back=d.start_seconds+2*d.duration_seconds//3
        return (
            (rest,EngineCommand(action='start_rest',worker_id=worker.worker_id,zone_id=d.rest_zone_id,reason='scripted rest')),
            (back,EngineCommand(action='end_rest',worker_id=worker.worker_id,reason='scripted rest end')),
            (back,EngineCommand(action='assign_task',worker_id=worker.worker_id,task_id=task.task_id,zone_id=worker.current_zone_id,reason='scripted return assignment')),
            (back,EngineCommand(action='start_work',worker_id=worker.worker_id,reason='scripted work return')),
        )

    def _new(self):
        definition=self.definition; config=self.config
        factory=lambda:EnvironmentalSimulator(seed=config.seed,zones=config.environment_zones,forcing=definition.forcing())
        engine=IntegratedSimulationEngine(config,environment_factory=factory)
        engine.initialize()
        script=self._script_for(engine)
        return engine,script

    def start(self):
        if self.engine is not None: raise ValueError('scenario already started; use reset for replay')
        engine,script=self._new()
        due=tuple(command for at,command in script if at==0)
        if due: engine.execute_batch(due)
        self.engine,self._script,self._cursor=engine,script,len(due)
        self._running=True
        self._events=(ScenarioLifecycleEvent(event_id=1,elapsed_seconds=0,action='started',scenario_id=self.definition.scenario_id.value),)
        return engine.get_state()

    def fork(self):
        """Detached scenario cursor and engine for service-level transactions."""
        candidate=EngineeringScenarioRunner(self.definition,config=self.config)
        candidate.engine=self.engine.fork()
        candidate._script,candidate._cursor=self._script,self._cursor
        candidate._running,candidate._events=self._running,self._events
        return candidate

    def activate_on(self, engine):
        """Activate explicit inputs at current simulated time, preserving history."""
        if self.engine is not None: raise ValueError('scenario already started')
        now=engine.get_state().simulation.time.elapsed_seconds
        if self.definition.start_seconds!=now: raise ValueError('scenario start must match current time')
        if engine.config!=self.config: raise ValueError('scenario engine configuration mismatch')
        candidate=engine.fork()
        candidate.replace_environment(EnvironmentalSimulator(seed=self.config.seed,
            zones=self.config.environment_zones,forcing=self.definition.forcing()))
        script=self._script_for(candidate)
        due=tuple(command for at,command in script if at==now)
        if due: candidate.execute_batch(due)
        self.engine,self._script,self._cursor=candidate,script,len(due)
        self._running=True
        self._events=(ScenarioLifecycleEvent(event_id=1,elapsed_seconds=now,action='started',
            scenario_id=self.definition.scenario_id.value),)
        return candidate.get_state()

    def reset(self):
        # Build in a temporary runner first; failure leaves current run untouched.
        candidate=EngineeringScenarioRunner(self.definition,config=self.config)
        candidate.start()
        self.engine,self._script,self._cursor=candidate.engine,candidate._script,candidate._cursor
        self._running,self._events=candidate._running,candidate._events
        return self.engine.get_state()

    def stop(self):
        if not self._running: raise ValueError('scenario is not running')
        now=self.engine.get_state().simulation.time.elapsed_seconds
        forcing=replace(self.definition.forcing(),stopped_at_seconds=now)
        adapter=EnvironmentalSimulator(seed=self.config.seed,zones=self.config.environment_zones,forcing=forcing)
        state=self.engine.replace_environment(adapter)
        self._running=False
        self._events+=(ScenarioLifecycleEvent(event_id=len(self._events)+1,elapsed_seconds=now,action='stopped',scenario_id=self.definition.scenario_id.value),)
        return state

    def step(self, delta_seconds=None):
        if not self._running: raise ValueError('start/reset scenario before stepping')
        frame=self.engine.get_state()
        if frame.paused: return frame
        delta=self.config.tick_seconds if delta_seconds is None else delta_seconds
        seconds(delta,'delta_seconds',positive=True)
        target=frame.simulation.time.elapsed_seconds+delta
        stop=self._cursor
        while stop<len(self._script) and self._script[stop][0]<=target: stop+=1
        candidate=self.engine.advance(delta,self._script[self._cursor:stop])
        self._cursor=stop
        return candidate

    def run(self,ticks):
        seconds(ticks,'ticks')
        if not self._running: raise ValueError('scenario not running')
        for _ in range(ticks): self.step()
        return self.engine.get_state()

    def snapshot(self):
        if self.engine is None: raise ValueError('start scenario before export')
        result=self.engine.snapshot(scenario=self.definition.scenario_id.value,scenario_input=self.definition)
        result['scenario_events']=to_json_value(self.events)
        result['scenario_running']=self._running
        result['scenario_phase']=('scheduled' if result['simulated_time_seconds']<self.definition.start_seconds else
            'complete' if result['simulated_time_seconds']>=self.definition.start_seconds+self.definition.duration_seconds else 'active')
        if not self._running: result['scenario_phase']='stopped'
        return result

    def export_snapshot(self): return encode_snapshot(self.snapshot())
