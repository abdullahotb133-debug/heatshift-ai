from copy import deepcopy
import json
from pathlib import Path
import os
import subprocess
import sys

import pytest
from heatshift_ai import (ScenarioController, SyntheticScenarioAdapter, EnvironmentObservation,
    EnvironmentalCondition, build_snapshot, export_snapshot, parse_snapshot, validate_snapshot)


def controller(name='NORMAL', **kwargs):
    return ScenarioController(name, adapter_factory=SyntheticScenarioAdapter, **kwargs)


def test_zero_time_snapshot_and_roundtrip():
    c=controller()
    s=build_snapshot(c)
    assert s['simulated_time_seconds']==0
    assert s['source']=='synthetic_simulator'
    assert len(s['workers'])==10 and len(s['tasks'])==6 and len(s['zones'])==4
    assert len(c.requests)==1
    assert parse_snapshot(export_snapshot(s))==s
    assert validate_snapshot(s)==c.state
    c.run(1)
    assert c.state.time.elapsed_seconds==10 and len(c.requests)==1


def test_contract_condition_and_metadata_preserved():
    class ContractFixture(SyntheticScenarioAdapter):
        def observe(self, *, zone_id, elapsed_seconds):
            return EnvironmentObservation(zone_id=zone_id, elapsed_seconds=elapsed_seconds,
                wbgt_celsius=29.5, source='simulated', method='test_method',
                conditions=(EnvironmentalCondition(name='air_temperature',value=35,unit='degC'),),
                source_metadata=(('provider','contract_test'),('version','v1')))
    c=ScenarioController('HEATWAVE',adapter_factory=ContractFixture)
    c.run(1)
    env=build_snapshot(c)['zones'][0]['environment']
    assert env['conditions']==[{'name':'air_temperature','value':35,'unit':'degC'}]
    assert env['method']=='test_method'
    assert env['source_metadata']=={'provider':'contract_test','version':'v1'}
    assert env['source']=='simulated'


def test_missing_optional_environment_values_remain_missing():
    class Missing(SyntheticScenarioAdapter):
        def observe(self, **kwargs):
            return EnvironmentObservation(**kwargs,wbgt_celsius=None,source='simulated')
    c=ScenarioController('NORMAL',adapter_factory=Missing)
    env=build_snapshot(c)['zones'][0]['environment']
    assert env['wbgt_celsius'] is None and env['method'] is None
    assert env['conditions']==[] and env['source_metadata']=={}


@pytest.mark.parametrize('mutate', [
    lambda x:x['workers'][0].update(current_zone_id='MISSING'),
    lambda x:x['tasks'][0].update(assigned_worker_id='W-02'),
    lambda x:x['assignments'].clear(),
    lambda x:x['workers'][0].update(exposure_elapsed_seconds=-1),
    lambda x:x['zones'][0]['environment'].update(elapsed_seconds=999),
    lambda x:x['zones'][0]['environment'].update(source='sensor'),
    lambda x:x['zones'][0]['environment'].update(wbgt_celsius=float('nan')),
    lambda x:x['events'][0].update(elapsed_seconds=999),
    lambda x:x['events'][0].update(worker_id='MISSING'),
    lambda x:x.update(source='physical_sensor'),
    lambda x:x['zones'].append(deepcopy(x['zones'][0])),
])
def test_tampered_snapshot_rejected(mutate):
    snapshot=build_snapshot(controller())
    mutate(snapshot)
    with pytest.raises(ValueError): validate_snapshot(snapshot)


@pytest.mark.parametrize('text',['null','[]','{}','{"a":1,"a":2}','{"x":NaN}'])
def test_malformed_json_rejected(text):
    with pytest.raises(ValueError): parse_snapshot(text)


@pytest.mark.parametrize('kwargs',[
    {'conditions':[]}, {'method':''}, {'source_metadata':(('key','one'),('key','two'))},
    {'conditions':(EnvironmentalCondition(name='x',value=1,unit='u'),)*2},
])
def test_invalid_adapter_metadata(kwargs):
    with pytest.raises(ValueError):
        EnvironmentObservation(zone_id='A',elapsed_seconds=0,wbgt_celsius=None,source='simulated',**kwargs)


@pytest.mark.parametrize('name',['NORMAL','HEATWAVE','RECOVERY'])
def test_1000_ticks_every_intermediate_state_and_replay(name):
    c=controller(name,seed=42)
    for _ in range(1000):
        c.run(1)
        state=c.state
        assert len(state.assignments)==len({a.worker_id for a in state.assignments})
        assert len(state.assignments)==len({a.task_id for a in state.assignments})
        zones={z.zone_id for z in state.zones}
        assert all(w.current_zone_id in zones for w in state.workers)
        for a in state.assignments:
            worker=next(w for w in state.workers if w.worker_id==a.worker_id)
            task=next(t for t in state.tasks if t.task_id==a.task_id)
            assert worker.current_task_id==task.task_id and task.assigned_worker_id==worker.worker_id
    assert c.state.time.elapsed_seconds==10000
    worker=c.state.workers[0]
    assert worker.exposure_elapsed_seconds==(9980 if name=='RECOVERY' else 10000)
    assert worker.rest_elapsed_seconds==(20 if name=='RECOVERY' else 0)
    first=export_snapshot(build_snapshot(c))
    assert validate_snapshot(parse_snapshot(first))==c.state
    c.reset(); c.run(1000)
    assert export_snapshot(build_snapshot(c))==first


def test_cli_exports_parseable_snapshot(tmp_path):
    root=Path(__file__).resolve().parents[1]
    output=tmp_path/'snapshot.json'
    env=dict(os.environ, PYTHONPATH=str(root/'src'))
    result=subprocess.run([sys.executable,'-m','heatshift_ai','--scenario','RECOVERY','--seed','42',
        '--ticks','5','--output',str(output)],env=env,cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode==0, result.stderr
    data=parse_snapshot(output.read_text())
    assert data['simulated_time_seconds']==50
    assert data['workers'][0]['rest_elapsed_seconds']==20
    bad=subprocess.run([sys.executable,'-m','heatshift_ai','--ticks','-1','--output',str(tmp_path/'bad.json')],
        env=env,cwd=root,capture_output=True,text=True,timeout=20)
    assert bad.returncode!=0 and not (tmp_path/'bad.json').exists()
