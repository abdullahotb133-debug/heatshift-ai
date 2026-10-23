import asyncio
import json
from dataclasses import replace
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from heatshift_ai.api import create_app, APISettings
from heatshift_ai.api_service import SimulationService
from heatshift_ai.api_contracts import SimulationCommand
from heatshift_ai.task_simulator import TaskConfig, TaskSimulator, default_task_definitions
from heatshift_ai.integrated_engine import IntegratedSimulationEngine, EngineConfig
from heatshift_ai.http_limits import BodyLimitMiddleware


def client(): return TestClient(create_app(APISettings(token='review-fixture-only')))
def state(c): return c.get('/api/v1/simulation/state').json()
def post(c,path,key,**extra):
    s=state(c)
    return c.post('/api/v1/'+path,json=dict(schema_version='1.0',simulation_id=s['simulation_id'],
        instance_id=s['instance_id'],expected_state_version=s['state_version'],**extra),
        headers={'Authorization':'Bearer review-fixture-only','Idempotency-Key':key})

@pytest.mark.parametrize('count',[1,3,8])
def test_configurable_tasks_reuse_domain_and_preserve_skills(count):
    definitions=default_task_definitions()
    definitions=tuple(replace(definitions[i%6],task_id=f'T-{i+1:02}') for i in range(count))
    config=TaskConfig(count=count,definitions=definitions)
    engine=IntegratedSimulationEngine(EngineConfig(task_config=config))
    initial=engine.initialize().simulation
    assert len(initial.tasks)==count
    skills={w.worker_id:w.qualifications for w in initial.workers}
    for _ in range(5): engine.tick()
    assert {w.worker_id:w.qualifications for w in engine.get_state().simulation.workers}==skills
    assert len(TaskSimulator().list_tasks())==6

@pytest.mark.parametrize('count',[0,-1,True,'3'])
def test_bad_task_counts(count):
    with pytest.raises(ValueError): TaskConfig(count=count)


def test_timestamp_version_order_and_stale_observation():
    c=client(); initial=state(c)
    assert initial['simulated_at']=='2026-01-01T00:00:00Z'
    pause=post(c,'simulation/pause','pause').json()
    r=post(c,'simulation/commands','rest',commands=[dict(action='start_rest',worker_id='W-03',zone_id='REST_ZONE',reason='explicit')]).json()
    assert (r['before_state_version'],r['after_state_version'])==(1,2)
    events=r['snapshot']['events']
    assert events[-3]['action']=='pause' and events[-2]['action']=='start_rest' and events[-1]['action']=='commands'
    assert all(e['occurred_at']=='2026-01-01T00:00:00Z' for e in events)
    assert [e['after_state_version'] for e in events]==sorted(e['after_state_version'] for e in events)
    post(c,'simulation/resume','resume')
    post(c,'scenarios/activate','failure',scenario_id='SENSOR_FAILURE',failure_mode='stale')
    after=post(c,'simulation/tick','tick',delta_seconds=40).json()['snapshot']
    assert after['simulated_at']=='2026-01-01T00:00:40Z'
    obs=after['zones'][0]['environment']
    assert obs['observed_at']=='2026-01-01T00:00:29Z' and obs['wbgt_celsius'] is None
    assert c.get('/api/v1/observations').json()['simulated_at']==after['simulated_at']


def test_body_limit_and_id_pattern_leave_state_unchanged():
    c=client(); before=state(c)
    r=c.post('/api/v1/simulation/commands',content=b' ' * 65537)
    assert r.status_code==413 and r.json()['error']['code']=='request_too_large'
    assert state(c)==before
    with pytest.raises(ValueError): SimulationCommand(action='stop_work',worker_id='1BAD',reason='bad id')


def test_chunked_limit_does_not_trust_content_length():
    called=[]; sent=[]
    async def downstream(scope,receive,send): called.append(True)
    async def run():
        chunks=iter([{'type':'http.request','body':b'a'*700,'more_body':True},
                     {'type':'http.request','body':b'b'*700,'more_body':False}])
        async def receive(): return next(chunks)
        async def send(message): sent.append(message)
        await BodyLimitMiddleware(downstream,1024)({'type':'http','headers':[(b'content-length',b'1')]},receive,send)
    asyncio.run(run())
    assert not called and sent[0]['status']==413


def test_request_size_configuration():
    with pytest.raises(ValueError): APISettings(max_body_bytes=True)
    with pytest.raises(ValueError): APISettings(max_body_bytes=0)


def test_openapi_is_current_and_examples_cover_every_endpoint():
    root=Path(__file__).resolve().parents[1]
    spec=create_app(APISettings()).openapi()
    assert spec==json.loads((root/'openapi.json').read_text())
    examples=json.loads((root/'examples/api/endpoint_examples.json').read_text())
    assert {(r['path'],r['method'].lower()) for r in examples}=={(p,m) for p,methods in spec['paths'].items() for m in methods}
    for route in spec['paths'].values():
        for operation in route.values(): assert '413' in operation['responses']
