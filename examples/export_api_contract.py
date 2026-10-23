"""Export OpenAPI and executed request/response examples (test dependencies required)."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from heatshift_ai.api import create_app, APISettings
from heatshift_ai.api_service import SimulationService


def main():
    root=Path(__file__).resolve().parents[1]
    # Fixture token is not exported and is only valid for this in-process test app.
    app=create_app(APISettings(token='example-fixture-only'),service=SimulationService(instance_id='example-instance'))
    client=TestClient(app)
    records=[]
    for path in ['/health','/api/v1/simulation/state']+['/api/v1/'+p for p in ['zones','workers','tasks','observations','scenarios','events']]:
        response=client.get(path); assert response.status_code==200
        records.append(dict(method='GET',path=path,status=response.status_code,response=response.json()))
    operations=[('simulation/tick',dict(delta_seconds=10)),('simulation/pause',{}),('simulation/resume',{}),
        ('scenarios/activate',dict(scenario_id='HEAT_ESCALATION')),
        ('simulation/commands',dict(commands=[dict(action='start_rest',worker_id='W-03',zone_id='REST_ZONE',reason='explicit mock B break')])),
        ('simulation/reset',{})]
    for i,(path,extra) in enumerate(operations):
        state=client.get('/api/v1/simulation/state').json()
        body=dict(schema_version='1.0',simulation_id=state['simulation_id'],instance_id=state['instance_id'],
            expected_state_version=state['state_version'],**extra)
        key=f'example-{i}'
        response=client.post('/api/v1/'+path,json=body,headers={'Authorization':'Bearer example-fixture-only','Idempotency-Key':key})
        assert response.status_code==200,response.text
        records.append(dict(method='POST',path='/api/v1/'+path,headers={'Authorization':'Bearer <HEATSHIFT_API_TOKEN>','Idempotency-Key':key},
            request=body,status=200,response=response.json()))
    (root/'openapi.json').write_text(json.dumps(app.openapi(),indent=2,sort_keys=True)+'\n')
    (root/'examples/api/endpoint_examples.json').write_text(json.dumps(records,indent=2,sort_keys=True)+'\n')
    print(f'Exported OpenAPI and {len(records)} executed endpoint examples')

if __name__=='__main__': main()
