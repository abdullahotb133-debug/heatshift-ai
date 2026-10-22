from dataclasses import replace,FrozenInstanceError
from concurrent.futures import ThreadPoolExecutor
import pytest
from heatshift_ai.integrated_engine import IntegratedSimulationEngine, EngineConfig, EngineCommand
from heatshift_ai.environmental_simulator import EnvironmentalSimulator, ZoneEnvironmentConfig
from heatshift_ai import parse_snapshot,WorkerConfig,TaskConfig,Zone


def engine(**kwargs):
    e=IntegratedSimulationEngine(**kwargs); e.initialize(); return e


def test_default_initialization_and_canonical_tick():
    e=engine()
    initial=e.get_state()
    assert len(initial.simulation.workers)==10 and len(initial.simulation.tasks)==6
    assert len(initial.simulation.assignments)==6 and len(initial.environment)==4
    assert initial.simulation.time.elapsed_seconds==0
    state=e.tick()
    assert state.simulation.time.elapsed_seconds==10
    assert all(o.elapsed_seconds==10 for o in state.environment)
    for worker in state.simulation.workers:
        assert worker.exposure_elapsed_seconds==(10 if worker.current_task_id else 0)
    assert initial.simulation.time.elapsed_seconds==0
    with pytest.raises(FrozenInstanceError): state.simulation.random_seed=3
    with pytest.raises(ValueError): e.initialize()


def test_pause_reset_and_commands():
    e=engine(); original=e.export_snapshot()
    worker=next(w for w in e.get_state().simulation.workers if w.current_task_id)
    e.tick(); e.pause(); before=e.get_state()
    assert e.tick(100) is before
    e.resume()
    e.execute(EngineCommand(action='start_rest',worker_id=worker.worker_id,zone_id='REST_ZONE',reason='explicit break'))
    state=e.tick(5)
    w=next(w for w in state.simulation.workers if w.worker_id==worker.worker_id)
    assert (w.exposure_elapsed_seconds,w.rest_elapsed_seconds)==(10,5)
    assert all(a.worker_id!=worker.worker_id for a in state.simulation.assignments)
    e.reset(); assert e.export_snapshot()==original


def test_transactional_environment_failure_and_mutable_provider_rollback():
    class Failing(EnvironmentalSimulator):
        calls=0
        def observe(self,**kwargs):
            self.calls+=1
            if kwargs['elapsed_seconds']>0 and kwargs['zone_id']=='ZONE_B': raise ValueError('injected read failure')
            return super().observe(**kwargs)
    e=engine(environment_factory=Failing)
    before=e.get_state(); calls=e._environment.calls
    with pytest.raises(ValueError,match='injected'): e.tick()
    assert e.get_state() is before and e._environment.calls==calls


def test_atomic_multi_action_tick_rollback():
    e=engine(); before=e.get_state()
    w=next(w for w in before.simulation.workers if w.current_task_id)
    commands=((5,EngineCommand(action='start_rest',worker_id=w.worker_id,zone_id='REST_ZONE',reason='break')),
              (7,EngineCommand(action='start_work',worker_id=w.worker_id,reason='invalid while resting')))
    with pytest.raises(ValueError): e.advance(10,commands)
    assert e.get_state() is before
    with pytest.raises(ValueError): e.execute(EngineCommand(action='change_zone',worker_id=w.worker_id,zone_id='UNKNOWN',reason='invalid'))
    assert e.get_state() is before


def test_read_timestamp_and_missing_readings():
    class Wrong(EnvironmentalSimulator):
        def observe(self,**kwargs):
            return replace(super().observe(**kwargs),elapsed_seconds=99)
    e=IntegratedSimulationEngine(environment_factory=Wrong)
    with pytest.raises(ValueError,match='timestamp'): e.initialize()
    with pytest.raises(ValueError,match='initialize'): e.get_state()
    config=EngineConfig()
    config=replace(config,environment_zones=tuple(replace(z,natural_wet_bulb_c=None) for z in config.environment_zones))
    e=engine(config=config)
    assert all(o.wbgt_celsius is None for o in e.tick().environment)
    parse_snapshot(e.export_snapshot())


def test_custom_population_and_zone_dimensions():
    tasks=TaskConfig()
    tasks=replace(tasks,zones=(Zone(zone_id='WORK',kind='work'),Zone(zone_id='REST',kind='rest')),
        definitions=tuple(replace(d,allowed_zone_ids=frozenset({'WORK'})) for d in tasks.definitions))
    workers=WorkerConfig(count=3,work_zone_ids=('WORK',),rest_zone_id='REST')
    config=EngineConfig(worker_config=workers,task_config=tasks,
        environment_zones=(ZoneEnvironmentConfig(zone_id='WORK'),ZoneEnvironmentConfig(zone_id='REST',solar_exposure=False)),initial_assignments=())
    e=engine(config=config)
    assert len(e.tick().simulation.workers)==3 and len(e.get_state().environment)==2
    parse_snapshot(e.export_snapshot())


def test_replay_and_concurrent_exclusive_commands():
    e=engine(); worker=next(w for w in e.get_state().simulation.workers if w.current_task_id)
    def run():
        e.tick(7)
        e.execute(EngineCommand(action='start_rest',worker_id=worker.worker_id,zone_id='REST_ZONE',reason='script'))
        e.tick(3)
        return e.export_snapshot()
    first=run(); e.reset(); assert run()==first
    e.reset()
    def attempt(_):
        try:
            e.execute(EngineCommand(action='stop_work',worker_id=worker.worker_id,reason='request'))
            return True
        except ValueError: return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt,range(2)))==[False,True]
    parse_snapshot(e.export_snapshot())


def test_bad_controls_and_config():
    with pytest.raises(ValueError): EngineConfig(seed=True)
    e=engine(); before=e.get_state()
    with pytest.raises(ValueError): e.tick(0)
    with pytest.raises(ValueError): e.execute(EngineCommand(action='start_work',reason='missing worker'))
    assert e.get_state() is before
