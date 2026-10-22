from dataclasses import replace
from pathlib import Path
import subprocess,sys,os,json
import pytest
from heatshift_ai import (EngineeringScenarioName,EngineeringScenarioRunner,load_scenario,
    EngineConfig,EngineCommand,parse_snapshot,EnvironmentalForcing)


def run(name,**changes):
    d=replace(load_scenario(name),**changes)
    r=EngineeringScenarioRunner(d); r.start(); return r


@pytest.mark.parametrize('name',list(EngineeringScenarioName))
def test_each_scenario_replay_and_snapshot(name):
    r=run(name); r.run(12)
    data=parse_snapshot(r.export_snapshot())
    assert data['simulated_time_seconds']==120
    assert len(data['workers'])==10 and len(data['tasks'])==6
    first=r.export_snapshot()
    r.reset(); r.run(5); r.run(7)
    assert r.export_snapshot()==first
    assert data['scenario_input']['version']==1
    assert data['scenario_events'][0]['elapsed_seconds']==0


def temperature(frame,zone):
    obs=next(o for o in frame.environment if o.zone_id==zone)
    return next(c.value for c in obs.conditions if c.name=='air_temperature_c')


def test_heat_and_recovery_smooth_correlated_trends():
    for name in ('HEAT_ESCALATION','MULTI_ZONE_HEAT','RECOVERY'):
        r=run(name)
        start=r.engine.get_state()
        previous=temperature(start,'ZONE_A')
        for _ in range(120):
            frame=r.step(1); now=temperature(frame,'ZONE_A')
            assert abs(now-previous)<0.11
            previous=now
        delta=temperature(frame,'ZONE_A')-temperature(start,'ZONE_A')
        assert delta< -5 if name=='RECOVERY' else delta>5
        if name=='MULTI_ZONE_HEAT':
            assert temperature(frame,'ZONE_C')>temperature(frame,'ZONE_B')
        assert temperature(frame,'REST_ZONE')<temperature(frame,'ZONE_A')


def test_no_eligible_replacement_is_real_and_no_reassignment():
    r=run('NO_ELIGIBLE_REPLACEMENT')
    s=r.engine.get_state().simulation
    task=next(t for t in s.tasks if t.task_id=='T-04')
    assert task.assigned_worker_id is None and task.task_status=='pending'
    assert not any(task.required_qualifications<=w.qualifications and w.availability_status=='available'
        and w.current_task_id is None and w.work_status=='idle' for w in s.workers)
    before=s.assignments
    r.run(12)
    assert r.engine.get_state().simulation.assignments==before
    assert next(t for t in r.engine.get_state().simulation.tasks if t.task_id=='T-04').assigned_worker_id is None


@pytest.mark.parametrize('mode',['missing','stale','invalid'])
def test_failure_and_recovery_no_substitution(mode):
    r=run('SENSOR_FAILURE',failure_mode=mode)
    r.run(3)
    obs=next(o for o in r.engine.get_state().environment if o.zone_id=='ZONE_A')
    assert dict(obs.source_metadata)['quality']==mode and obs.wbgt_celsius is None
    parse_snapshot(r.export_snapshot())
    if mode!='stale': assert all(c.value is None for c in obs.conditions)
    r.run(6)
    obs=next(o for o in r.engine.get_state().environment if o.zone_id=='ZONE_A')
    assert dict(obs.source_metadata)['quality']=='good' and obs.wbgt_celsius is not None


def test_recovery_script_counters_order_and_pause():
    r=run('RECOVERY')
    initial=r.engine.get_state().simulation
    target=next(t.assigned_worker_id for t in initial.tasks if t.task_id=='T-01')
    r.run(4); r.engine.pause()
    before=r.engine.get_state()
    assert r.step() is before
    r.engine.resume(); r.run(8)
    worker=next(w for w in r.engine.get_state().simulation.workers if w.worker_id==target)
    assert (worker.exposure_elapsed_seconds,worker.rest_elapsed_seconds,worker.current_work_period_seconds)==(80,40,40)
    events=r.engine.get_state().events[12:]
    assert [(e.action,e.elapsed_seconds) for e in events]==[
        ('start_rest',40),('end_rest',80),('assign_task',80),('start_work',80)]


def test_scenario_tick_failure_rolls_back_script_cursor_and_all_state():
    r=run('RECOVERY'); r.run(3)
    target=next(t.assigned_worker_id for t in r.engine.get_state().simulation.tasks if t.task_id=='T-01')
    r.engine.execute(EngineCommand(action='start_rest',worker_id=target,zone_id='REST_ZONE',reason='explicit earlier break'))
    before=r.engine.get_state(); cursor=r._cursor
    with pytest.raises(ValueError,match='already resting'): r.step()
    assert r.engine.get_state() is before and r._cursor==cursor


def test_start_stop_reset_freezes_trend_and_retains_history():
    r=run('HEAT_ESCALATION'); r.run(5)
    before=r.engine.get_state()
    r.stop()
    after=r.engine.get_state()
    assert before.simulation==after.simulation and before.events==after.events
    assert before.environment==after.environment
    assert r.events[-1].action=='stopped' and r.events[-1].elapsed_seconds==50
    with pytest.raises(ValueError): r.step()
    r.reset(); assert r.engine.get_state().simulation.time.elapsed_seconds==0
    assert len(r.events)==1


def test_delayed_start_and_invalid_definitions():
    r=run('HEAT_ESCALATION',start_seconds=20)
    r.run(1)
    assert r.snapshot()['scenario_phase']=='scheduled'
    r.run(2); assert r.snapshot()['scenario_phase']=='active'
    with pytest.raises(ValueError): replace(load_scenario('NORMAL_OPERATION'),version=2)
    with pytest.raises(ValueError): replace(load_scenario('SENSOR_FAILURE'),failure_start_seconds=119)
    with pytest.raises(ValueError): EnvironmentalForcing(zone_heat=(('ZONE_A',0,100),))
    with pytest.raises(ValueError): load_scenario('UNKNOWN')


def test_cli_snapshot_events_and_reproducibility(tmp_path):
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONPATH=str(root/'src'))
    output=tmp_path/'snapshot.json'; events=tmp_path/'events.json'
    args=[sys.executable,'-m','heatshift_ai.demo_cli','--scenario','SENSOR_FAILURE','--ticks','4',
          '--failure-mode','stale','--output',str(output),'--events-output',str(events)]
    subprocess.run(args,cwd=root,env=env,check=True,timeout=20,capture_output=True)
    first=output.read_text(); data=parse_snapshot(first)
    assert data['simulated_time_seconds']==40
    assert json.loads(events.read_text())['scenario_events'][0]['action']=='started'
    subprocess.run(args,cwd=root,env=env,check=True,timeout=20,capture_output=True)
    assert output.read_text()==first
