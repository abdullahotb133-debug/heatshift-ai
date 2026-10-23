from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from fastapi.testclient import TestClient
from heatshift_ai.api import create_app, APISettings
from heatshift_ai.api_service import SimulationService
from heatshift_ai.api_contracts import SimulationSnapshot

TOKEN='test-only-token-not-for-deployment'
@pytest.fixture
def client():
    return TestClient(create_app(APISettings(token=TOKEN),service=SimulationService(instance_id='test-instance')))

def state(c): return c.get('/api/v1/simulation/state').json()
def body(s):
    return dict(schema_version='1.0',simulation_id=s['simulation_id'],instance_id=s['instance_id'],expected_state_version=s['state_version'])
def post(c,path,s=None,key='test',**extra):
    return c.post('/api/v1/'+path,json=body(s or state(c))|extra,
                  headers={'Authorization':'Bearer '+TOKEN,'Idempotency-Key':key})

def test_contracts_and_collections(client):
    assert client.get('/health').json()==dict(schema_version='1.0',status='ok',component='A')
    s=state(client); SimulationSnapshot.model_validate(s)
    assert [len(s[x]) for x in ('workers','tasks','zones')]==[10,6,4]
    for path,count in [('zones',4),('workers',10),('tasks',6),('observations',4),('scenarios',6)]:
        r=client.get('/api/v1/'+path); assert r.status_code==200
        assert len(r.json()['items'])==count
    assert client.get('/api/v1/events').json()['items']
    schemas=client.get('/openapi.json').json()['components']['schemas']
    assert {'SimulationSnapshot','EnvironmentalObservation','WorkerSnapshot','TaskSnapshot','ZoneSnapshot',
            'SimulationEvent','SimulationCommand','SimulationCommandResult'}<=schemas.keys()


def test_auth_and_no_secret_leaks(client):
    s=state(client)
    for headers in ({},{'Authorization':'Bearer wrong'}):
        r=client.post('/api/v1/simulation/tick',json=body(s),headers=headers)
        assert r.status_code==401 and TOKEN not in r.text
    assert state(client)==s
    locked=TestClient(create_app(APISettings()))
    assert post(locked,'simulation/tick').status_code==503
    with pytest.raises(ValueError): APISettings(mode='deployment')
    secure=TestClient(create_app(APISettings(mode='deployment',token=TOKEN)))
    assert secure.get('/api/v1/simulation/state').status_code==401
    assert secure.get('/health').status_code==200
    with pytest.raises(ValueError): APISettings(cors_origins=('*',))


def test_tick_pause_reset_state(client):
    s=state(client)
    r=post(client,'simulation/tick',s,delta_seconds=10).json()['snapshot']
    assert r['elapsed_seconds']==10 and r['state_version']==1
    assert all(w['exposure_elapsed_seconds']==(10 if w['current_task_id'] else 0) for w in r['workers'])
    post(client,'simulation/pause',key='pause')
    assert post(client,'simulation/tick',key='paused').json()['snapshot']['elapsed_seconds']==10
    post(client,'simulation/resume',key='resume')
    assert post(client,'simulation/tick',key='more').json()['snapshot']['elapsed_seconds']==20
    out=post(client,'simulation/reset',key='reset').json()['snapshot']
    assert out['elapsed_seconds']==0 and out['state_version']==6
    assert out['workers']==s['workers']


def test_idempotency_and_stale_conflicts(client):
    s=state(client); first=post(client,'simulation/tick',s,key='same')
    assert first.status_code==200
    assert post(client,'simulation/tick',s,key='same').json()==first.json()
    assert state(client)['elapsed_seconds']==10
    assert post(client,'simulation/tick',s,key='different').status_code==409
    assert post(client,'simulation/tick',s,key='same',delta_seconds=20).status_code==409
    bad=dict(s,instance_id='previous-process')
    assert post(client,'simulation/tick',bad,key='restart').status_code==409


@pytest.mark.parametrize('extra',[{'delta_seconds':-1},{'delta_seconds':True},{'delta_seconds':'10'},
    {'schema_version':'2.0'},{'workers':[]},{'delta_seconds':86401}])
def test_malformed_tick_unchanged(client,extra):
    s=state(client)
    assert post(client,'simulation/tick',s,**extra).status_code==422
    assert state(client)==s


def test_atomic_commands_and_eligibility(client):
    s=state(client); w=next(w for w in s['workers'] if w['current_task_id'])
    commands=[dict(action='stop_work',worker_id=w['worker_id'],reason='mock client'),
              dict(action='assign_task',worker_id=w['worker_id'],task_id='UNKNOWN',reason='invalid')]
    assert post(client,'simulation/commands',commands=commands).status_code==422
    assert state(client)==s
    commands=[dict(action='start_rest',worker_id=w['worker_id'],zone_id='REST_ZONE',reason='mock client')]
    out=post(client,'simulation/commands',commands=commands).json()['snapshot']
    assert next(x for x in out['workers'] if x['worker_id']==w['worker_id'])['work_status']=='resting'
    assert post(client,'simulation/commands',key='invalid',commands=[dict(action='assign_task',worker_id=w['worker_id'],
        task_id=w['current_task_id'],reason='cannot assign resting')]).status_code==422
    assert state(client)==out


def test_concurrent_requests_one_writer(client):
    s=state(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(lambda n:post(client,'simulation/tick',s,key=str(n)).status_code,range(2)))
    assert sorted(statuses)==[200,409]
    assert state(client)['elapsed_seconds']==10


@pytest.mark.parametrize('mode',['missing','stale','invalid'])
def test_sensor_quality_and_recovery(client,mode):
    assert post(client,'scenarios/activate',scenario_id='SENSOR_FAILURE',failure_mode=mode).status_code==200
    r=post(client,'simulation/tick',key='failure',delta_seconds=40).json()['snapshot']
    obs=r['zones'][0]['environment']
    assert obs['quality']==mode and obs['wbgt_celsius'] is None and obs['source']=='simulated'
    out=post(client,'simulation/tick',key='recovered',delta_seconds=60).json()['snapshot']
    assert out['zones'][0]['environment']['quality']=='good'


def test_activation_preserves_clock_history_and_replay(client):
    def run():
        post(client,'simulation/tick',key='initial')
        before=state(client)
        activated=post(client,'scenarios/activate',key='heat',scenario_id='HEAT_ESCALATION').json()['snapshot']
        assert activated['elapsed_seconds']==10 and activated['workers']==before['workers']
        assert activated['scenario_input']['start_seconds']==10
        return post(client,'simulation/tick',key='heat-tick',delta_seconds=120).json()
    first=run()
    client=TestClient(create_app(APISettings(token=TOKEN),service=SimulationService(instance_id='test-instance')))
    assert run()==first


def test_response_validation_failure_rolls_back(monkeypatch):
    svc=SimulationService(); c=TestClient(create_app(APISettings(token=TOKEN),service=svc),raise_server_exceptions=False)
    initial=state(c); original=svc._snapshot
    def fail(runner,version,operations):
        if version: raise RuntimeError('secret/internal failure')
        return original(runner,version,operations)
    monkeypatch.setattr(svc,'_snapshot',fail)
    r=post(c,'simulation/tick'); assert r.status_code==500 and 'secret' not in r.text
    assert state(c)==initial


def test_cors_and_capacity():
    c=TestClient(create_app(APISettings(token=TOKEN,cors_origins=('http://localhost:5173',),max_operations=1)))
    r=c.options('/api/v1/simulation/tick',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'POST'})
    assert r.headers['access-control-allow-origin']=='http://localhost:5173'
    assert post(c,'simulation/tick').status_code==200
    s=state(c)
    assert post(c,'simulation/tick',key='full').status_code==503
    assert state(c)==s


def test_reset_rebases_scenario_time_and_event_ids(client):
    post(client,'simulation/tick',key='first',delta_seconds=20)
    post(client,'scenarios/activate',key='activate',scenario_id='SENSOR_FAILURE')
    before=state(client)
    reset=post(client,'simulation/reset',key='reset').json()['snapshot']
    assert reset['elapsed_seconds']==0 and reset['scenario_input']['start_seconds']==0
    assert reset['scenario_input']['failure_start_seconds']==30
    assert not {e['event_id'] for e in before['events']} & {e['event_id'] for e in reset['events']}


def test_qualification_unavailability_and_zone_rejections(client):
    for wid,zone in [('W-04','ZONE_A'),('W-06','REST_ZONE'),('W-06','UNKNOWN')]:
        s=state(client)
        commands=[dict(action='stop_work',worker_id='W-03',reason='release'),
            dict(action='assign_task',worker_id=wid,task_id='T-01',zone_id=zone,reason='invalid proposal')]
        assert post(client,'simulation/commands',key=wid+zone,commands=commands).status_code==422
        assert state(client)==s
    post(client,'simulation/commands',key='unavailable',commands=[dict(action='mark_unavailable',worker_id='W-06',reason='fixture')])
    s=state(client)
    commands=[dict(action='stop_work',worker_id='W-03',reason='release'),
        dict(action='assign_task',worker_id='W-06',task_id='T-01',zone_id='ZONE_A',reason='unavailable proposal')]
    assert post(client,'simulation/commands',key='reject-unavailable',commands=commands).status_code==422
    assert state(client)==s


def test_mock_demo_and_replay():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('demo',Path(__file__).resolve().parents[1]/'examples/component_a_demo.py')
    demo=importlib.util.module_from_spec(spec); spec.loader.exec_module(demo)
    def run():
        c=TestClient(create_app(APISettings(token=TOKEN)))
        return demo.run_demo(c,TOKEN)
    first=run(); assert run()==first
    assert first['changes']['new_worker_id']=='W-06'


def test_concurrent_duplicates_exactly_once(client):
    s=state(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:post(client,'simulation/tick',s,key='duplicate').json(),range(2)))
    assert results[0]==results[1] and state(client)['elapsed_seconds']==10


def test_malformed_json_unknown_routes_and_command_fields(client):
    before=state(client)
    headers={'Authorization':'Bearer '+TOKEN,'Idempotency-Key':'bad-json','Content-Type':'application/json'}
    assert client.post('/api/v1/simulation/tick',content='{',headers=headers).status_code==422
    assert client.get('/api/v1/unknown').json()['error']['code']=='http_error'
    assert post(client,'simulation/commands',commands=[dict(action='assign_task',worker_id='W-06',reason='missing task')]).status_code==422
    assert state(client)==before


def test_no_eligible_scenario_and_recovery_http(client):
    no=post(client,'scenarios/activate',key='none',scenario_id='NO_ELIGIBLE_REPLACEMENT').json()['snapshot']
    task=next(t for t in no['tasks'] if t['task_id']=='T-04')
    assert task['assigned_worker_id'] is None
    assert not any(set(task['required_qualifications'])<=set(w['qualifications']) and w['availability_status']=='available' for w in no['workers'])
    fresh=TestClient(create_app(APISettings(token=TOKEN)))
    post(fresh,'scenarios/activate',scenario_id='RECOVERY')
    end=post(fresh,'simulation/tick',key='recover',delta_seconds=120).json()['snapshot']
    worker=next(w for w in end['workers'] if w['worker_id']=='W-03')
    assert (worker['exposure_elapsed_seconds'],worker['rest_elapsed_seconds'])==(80,40)
