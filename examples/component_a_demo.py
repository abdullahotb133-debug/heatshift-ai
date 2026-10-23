"""Real HTTP demo with a SCRIPTED MOCK Component B client, not a risk engine.

Starts a local single-worker server by default; no external services required.
The predetermined seed-42 example moves inspection from W-03 to W-06.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import httpx


def run_demo(client, token):
    trace=[]
    def get(path):
        r=client.get(path,headers={'Authorization':'Bearer '+token}); r.raise_for_status()
        value=r.json(); trace.append({'method':'GET','path':path,'response':value}); return value
    def post(path, key, **extra):
        s=get('/api/v1/simulation/state')
        payload=dict(schema_version='1.0',simulation_id=s['simulation_id'],instance_id=s['instance_id'],
                     expected_state_version=s['state_version'],**extra)
        r=client.post(path,json=payload,headers={'Authorization':'Bearer '+token,'Idempotency-Key':key})
        r.raise_for_status(); value=r.json()
        trace.append({'method':'POST','path':path,'idempotency_key':key,'request':payload,'response':value})
        return value['snapshot']
    initial=get('/api/v1/simulation/state')
    assert initial['elapsed_seconds']==0 and initial['random_seed']==42
    assert (len(initial['workers']),len(initial['tasks']),len(initial['zones']))==(10,6,4)
    post('/api/v1/simulation/tick','demo-tick',delta_seconds=10)
    post('/api/v1/scenarios/activate','demo-heat',scenario_id='HEAT_ESCALATION')
    before=post('/api/v1/simulation/tick','demo-heat-tick',delta_seconds=60)
    task=next(t for t in before['tasks'] if t['task_id']=='T-01')
    replacement=next(w for w in before['workers'] if w['worker_id']=='W-06')
    # Client checks eligibility for the predetermined fixture. Component A still validates it.
    assert task['assigned_worker_id']=='W-03'
    assert set(task['required_qualifications'])<=set(replacement['qualifications'])
    assert replacement['availability_status']=='available' and replacement['work_status']=='idle'
    assert replacement['current_task_id'] is None and 'ZONE_A' in task['allowed_zone_ids']
    commands=[dict(action='stop_work',worker_id='W-03',reason='scripted mock B handover'),
              dict(action='assign_task',worker_id='W-06',task_id='T-01',zone_id='ZONE_A',reason='scripted mock B handover'),
              dict(action='start_work',worker_id='W-06',reason='scripted mock B work start')]
    # Deliberately invalid mock proposal: W-04 lacks inspection qualification.
    rejected_body=dict(schema_version='1.0',simulation_id=before['simulation_id'],instance_id=before['instance_id'],
        expected_state_version=before['state_version'],commands=[commands[0],
        dict(action='assign_task',worker_id='W-04',task_id='T-01',zone_id='ZONE_A',reason='deliberately invalid test proposal')])
    rejected=client.post('/api/v1/simulation/commands',json=rejected_body,
        headers={'Authorization':'Bearer '+token,'Idempotency-Key':'demo-rejected'})
    assert rejected.status_code==422 and get('/api/v1/simulation/state')==before
    trace.append(dict(method='POST',path='/api/v1/simulation/commands',idempotency_key='demo-rejected',
        request=rejected_body,status=422,response=rejected.json()))
    after=post('/api/v1/simulation/commands','demo-reassignment',commands=commands)
    assert next(t for t in after['tasks'] if t['task_id']=='T-01')['assigned_worker_id']=='W-06'
    assert get('/api/v1/simulation/state')==after
    advanced=post('/api/v1/simulation/tick','demo-after-tick',delta_seconds=10)
    assert next(w for w in advanced['workers'] if w['worker_id']=='W-06')['exposure_elapsed_seconds']==10
    assert next(w for w in advanced['workers'] if w['worker_id']=='W-03')['exposure_elapsed_seconds']==70
    result=dict(client='scripted mock Component B; not real Decision Engine',initial=initial,before=before,
        after=after,final=advanced,changes={'task_id':'T-01','old_worker_id':'W-03','new_worker_id':'W-06'},
        events=after['events'],rejected_assignment=rejected.json(),http_trace=trace)
    # Process identity is intentionally nondeterministic and is not simulation data.
    def canonical(value):
        if isinstance(value,dict): return {k:('<service-instance>' if k=='instance_id' else canonical(v)) for k,v in value.items()}
        if isinstance(value,list): return [canonical(v) for v in value]
        return value
    return canonical(result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='component_a_evidence.json')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    token=secrets.token_urlsafe(32)
    env=dict(os.environ,PYTHONPATH=str(root/'src'),HEATSHIFT_MODE='deployment',HEATSHIFT_API_TOKEN=token,HEATSHIFT_SEED='42')
    process=subprocess.Popen([sys.executable,'-m','uvicorn','heatshift_ai.api:create_app','--factory',
        '--host','127.0.0.1','--port',str(port),'--workers','1','--log-level','error'],env=env)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=10) as client:
            for _ in range(100):
                if process.poll() is not None: raise RuntimeError('API process exited before startup')
                try:
                    if client.get('/health').status_code==200: break
                except httpx.ConnectError: pass
                time.sleep(0.05)  # Harness readiness only; simulation never sleeps.
            else: raise RuntimeError('API startup timed out')
            evidence=run_demo(client,token)
        Path(args.output).write_text(json.dumps(evidence,indent=2,sort_keys=True)+'\n')
        print('PASS: HTTP snapshot, tick, scenario, atomic reassignment, persisted state and counters; elapsed=80')
    finally:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait()

if __name__=='__main__': main()
