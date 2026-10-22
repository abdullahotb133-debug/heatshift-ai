from dataclasses import replace
import json
import pytest
from heatshift_ai import (ScenarioController, ScenarioName, ScriptedAction,
                         SyntheticScenarioAdapter, EnvironmentObservation)


def controller(name='NORMAL', **kwargs):
    return ScenarioController(name, adapter_factory=SyntheticScenarioAdapter, **kwargs)


@pytest.mark.parametrize('name', list(ScenarioName))
def test_valid_start_replay_and_request(name):
    c=controller(name,seed=42)
    assert c.state.time.elapsed_seconds==0
    assert len(c.state.assignments)==6
    assert len({a.worker_id for a in c.state.assignments})==6
    replace(c.state)
    c.run(5)
    first=c.export_json()
    assert c.requests[0].scenario==name and c.requests[0].seed==42
    assert c.requests[0].elapsed_seconds==0
    assert len(c.observations)==20
    assert all(o.source=='simulated' for o in c.observations)
    c.reset()
    assert not c.requests and not c.observations
    c.run(5)
    assert c.export_json()==first
    d=controller(name,seed=42)
    d.run(2); d.run(3)
    assert d.export_json()==first


def test_heatwave_only_changes_environment_not_workers():
    normal,heat=controller(),controller('HEATWAVE')
    normal.run(5); heat.run(5)
    assert normal.state==heat.state and normal.events==heat.events
    assert heat.observations[0].wbgt_celsius>normal.observations[0].wbgt_celsius
    assert all(w.exposure_elapsed_seconds==50 for w in heat.state.workers[:6])
    assert all(w.exposure_elapsed_seconds==0 for w in heat.state.workers[6:])


def test_recovery_exact_history_and_order():
    c=controller('RECOVERY'); c.run(5)
    w=c.state.workers[0]
    assert (w.exposure_elapsed_seconds,w.rest_elapsed_seconds,w.current_work_period_seconds)==(30,20,10)
    assert [(e.action,e.elapsed_seconds) for e in c.events[12:]]==[
        ('start_rest',20),('end_rest',40),('assign_task',40),('start_work',40)]
    assert c.state.time.elapsed_seconds==50
    assert c.state.workers[1].exposure_elapsed_seconds==50
    assert len(c.state.assignments)==6


def test_off_grid_actions_and_zero_timestamp_once():
    actions=(ScriptedAction(elapsed_seconds=7,action='start_rest',worker_id='W-01',zone_id='REST_ZONE',reason='test'),
             ScriptedAction(elapsed_seconds=0,action='change_zone',worker_id='W-01',zone_id='ZONE_B',reason='setup'),
             ScriptedAction(elapsed_seconds=13,action='end_rest',worker_id='W-01',reason='end'))
    c=controller(actions=actions,tick_seconds=10)
    c.run(0); assert len(c.events)==12
    c.run(2)
    assert [e.elapsed_seconds for e in c.events[12:]]==[0,7,13]
    w=c.state.workers[0]
    assert (w.exposure_elapsed_seconds,w.rest_elapsed_seconds)==(7,6)
    assert c.state.time.elapsed_seconds==20


def test_seed_variation_and_custom_ticks():
    a,b=controller(seed=1,tick_seconds=3),controller(seed=2,tick_seconds=3)
    assert a.state.workers!=b.state.workers
    a.run(5)
    assert a.state.time.elapsed_seconds==15
    assert a.state.workers[0].exposure_elapsed_seconds==15


@pytest.mark.parametrize('kwargs', [{'name':'BAD'},{'seed':True},{'tick_seconds':0},{'actions':[]}])
def test_bad_configuration(kwargs):
    with pytest.raises(ValueError):
        controller(**kwargs)


@pytest.mark.parametrize('kwargs', [{'elapsed_seconds':-1},{'action':'reset'}, {'worker_id':''},
                                   {'reason':''},{'action':'start_rest'}, {'zone_id':'ZONE_A'}])
def test_bad_script_schema(kwargs):
    with pytest.raises(ValueError):
        ScriptedAction(**({'elapsed_seconds':0,'action':'stop_work','worker_id':'W-01','reason':'test'}|kwargs))


def test_failed_action_stops_without_partial_transition_or_retry():
    action=ScriptedAction(elapsed_seconds=5,action='change_task',worker_id='W-01',task_id='T-02',reason='invalid occupied task')
    c=controller(actions=(action,))
    before=c.state.assignments
    with pytest.raises(ValueError): c.run(1)
    assert c.state.time.elapsed_seconds==5
    assert c.state.assignments==before and len(c.events)==12
    with pytest.raises(RuntimeError,match='reset'): c.run(1)
    c.reset(); assert c.state.time.elapsed_seconds==0


def test_unsupported_override_fails_once():
    class Unsupported(SyntheticScenarioAdapter):
        calls=0
        def request_scenario(self, request):
            self.calls+=1
            raise NotImplementedError('overrides unavailable')
    instance=Unsupported()
    c=ScenarioController('HEATWAVE',adapter_factory=lambda:instance)
    with pytest.raises(NotImplementedError): c.run(1)
    with pytest.raises(RuntimeError): c.run(1)
    assert instance.calls==1 and c.state.time.elapsed_seconds==0
    with pytest.raises(ValueError,match='fresh'): c.reset()


def test_read_only_adapter_rejected():
    class ReadOnly:
        def observe(self, **kwargs): pass
    with pytest.raises(ValueError,match='request_scenario'):
        ScenarioController('RECOVERY',adapter_factory=ReadOnly)


def test_bad_observation_rejected_and_no_batch_published():
    class WrongTime(SyntheticScenarioAdapter):
        def observe(self, *, zone_id, elapsed_seconds):
            return EnvironmentObservation(zone_id=zone_id,elapsed_seconds=0,wbgt_celsius=None,source='simulated')
    c=ScenarioController('NORMAL',adapter_factory=WrongTime)
    with pytest.raises(ValueError,match='zone/time'): c.run(1)
    assert c.observations==()
    assert json.loads(c.export_json())['failed'] is True


def test_measured_provenance_retained_without_relabeling():
    class ContractFixture(SyntheticScenarioAdapter):
        def observe(self, **kwargs):
            return EnvironmentObservation(**kwargs,wbgt_celsius=None,source='measured')
    c=ScenarioController('NORMAL',adapter_factory=ContractFixture)
    c.run(1)
    assert all(o.source=='measured' and o.wbgt_celsius is None for o in c.observations)
