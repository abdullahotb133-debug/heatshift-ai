"""FastAPI boundary; instantiate with `uvicorn heatshift_ai.api:create_app --factory`."""
from dataclasses import dataclass, field
import hmac
import os
from typing import Annotated
from fastapi import FastAPI, Depends, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from .api_contracts import (Health, SimulationSnapshot, SimulationCommandResult, MutationRequest,
    TickRequest, ActivateRequest, CommandRequest, Collection, WorkerSnapshot, TaskSnapshot,
    ZoneSnapshot, EnvironmentalObservation, SimulationEvent, ScenarioInfo, ErrorResponse)
from .api_service import SimulationService, ServiceError
from .http_limits import BodyLimitMiddleware
from .engineering_scenarios import EngineeringScenarioName, load_scenario
from .serialization import to_json_value

@dataclass(frozen=True)
class APISettings:
    mode: str = 'development'
    token: str | None = field(default=None,repr=False)
    cors_origins: tuple[str,...] = ()
    seed: int = 42
    max_operations: int = 10000
    max_body_bytes: int = 65536

    def __post_init__(self):
        if type(self.max_body_bytes) is not int or not 1024 <= self.max_body_bytes <= 1048576:
            raise ValueError('max_body_bytes must be integer 1024..1048576')
        if self.mode not in ('development','deployment'): raise ValueError('invalid HEATSHIFT_MODE')
        if self.mode=='deployment' and (not self.token or len(self.token)<32):
            raise ValueError('deployment requires HEATSHIFT_API_TOKEN of at least 32 characters')
        if self.token is not None and not self.token.strip(): raise ValueError('token must not be blank')
        if any(o=='*' or not o.startswith(('https://','http://')) for o in self.cors_origins):
            raise ValueError('CORS requires explicit http(s) origins')
        if type(self.seed) is not int: raise ValueError('seed must be integer')
        if type(self.max_operations) is not int or self.max_operations<1: raise ValueError('invalid operation capacity')

    @classmethod
    def from_env(cls):
        return cls(mode=os.getenv('HEATSHIFT_MODE','development'),token=os.getenv('HEATSHIFT_API_TOKEN') or None,
            cors_origins=tuple(o.strip() for o in os.getenv('HEATSHIFT_CORS_ORIGINS','').split(',') if o.strip()),
            seed=int(os.getenv('HEATSHIFT_SEED','42')),max_operations=int(os.getenv('HEATSHIFT_MAX_OPERATIONS','10000')),
            max_body_bytes=int(os.getenv('HEATSHIFT_MAX_BODY_BYTES','65536')))


def create_app(settings: APISettings | None = None, *, service: SimulationService | None = None):
    settings=settings or APISettings.from_env()
    service=service or SimulationService(settings.seed,max_operations=settings.max_operations)
    errors={status:{'model':ErrorResponse} for status in (401,403,409,413,422,503,500)}
    app=FastAPI(title='HeatShift Component A',version='1.0',responses=errors,
        description='Synthetic simulator only. One process / one worker. No risk evaluation.')
    app.add_middleware(BodyLimitMiddleware,max_bytes=settings.max_body_bytes)
    app.add_middleware(CORSMiddleware,allow_origins=list(settings.cors_origins),
        allow_credentials=False,allow_methods=['GET','POST'],
        allow_headers=['Authorization','Content-Type','Idempotency-Key'])
    bearer=HTTPBearer(auto_error=False)

    def authorize(credentials: Annotated[HTTPAuthorizationCredentials | None,Depends(bearer)]):
        if settings.token is None:
            raise ServiceError(503,'authentication_unconfigured','Configure HEATSHIFT_API_TOKEN to enable mutations')
        supplied=credentials.credentials if credentials else ''
        if not hmac.compare_digest(supplied.encode(),settings.token.encode()):
            raise ServiceError(401,'unauthorized','Valid bearer authentication required')

    def read_authorize(credentials: Annotated[HTTPAuthorizationCredentials | None,Depends(bearer)]):
        if settings.mode=='deployment': authorize(credentials)

    def error(status,code,message):
        return JSONResponse(status_code=status,content={'schema_version':'1.0','error':{'code':code,'message':message}},
            headers={'WWW-Authenticate':'Bearer'} if status==401 else None)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request,exc: ServiceError): return error(exc.status,exc.code,exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request,exc: RequestValidationError):
        # Do not reflect arbitrary payloads, authorization headers or secret values.
        fields=', '.join('.'.join(map(str,e['loc'])) for e in exc.errors())
        return error(422,'invalid_request','Invalid request fields: '+fields)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request,exc: HTTPException):
        return error(exc.status_code,'http_error','Request not supported')

    @app.exception_handler(Exception)
    async def internal_error(request: Request,exc: Exception):
        return error(500,'internal_error','Request failed; no candidate state was committed')

    @app.get('/health',response_model=Health)
    def health(): return Health()

    reads=[Depends(read_authorize)]
    @app.get('/api/v1/simulation/state',response_model=SimulationSnapshot,dependencies=reads)
    def state(): return service.snapshot()

    def collection(name, model):
        snapshot=service.snapshot()
        items=[z.environment for z in snapshot.zones] if name=='observations' else getattr(snapshot,name)
        return Collection[model](**{k:getattr(snapshot,k) for k in ('simulation_id','instance_id','state_version','elapsed_seconds','simulated_at')},items=items)

    @app.get('/api/v1/zones',response_model=Collection[ZoneSnapshot],dependencies=reads)
    def zones(): return collection('zones',ZoneSnapshot)
    @app.get('/api/v1/workers',response_model=Collection[WorkerSnapshot],dependencies=reads)
    def workers(): return collection('workers',WorkerSnapshot)
    @app.get('/api/v1/tasks',response_model=Collection[TaskSnapshot],dependencies=reads)
    def tasks(): return collection('tasks',TaskSnapshot)
    @app.get('/api/v1/observations',response_model=Collection[EnvironmentalObservation],dependencies=reads)
    def observations(): return collection('observations',EnvironmentalObservation)
    @app.get('/api/v1/events',response_model=Collection[SimulationEvent],dependencies=reads)
    def events(): return collection('events',SimulationEvent)
    @app.get('/api/v1/scenarios',response_model=Collection[ScenarioInfo],dependencies=reads)
    def scenarios():
        s=service.snapshot()
        return Collection[ScenarioInfo](**{k:getattr(s,k) for k in ('simulation_id','instance_id','state_version','elapsed_seconds','simulated_at')},
            items=[ScenarioInfo(scenario_id=n,version=1,parameters=to_json_value(load_scenario(n,seed=settings.seed))) for n in EngineeringScenarioName])

    Key=Annotated[str,Header(alias='Idempotency-Key',min_length=1,max_length=128,pattern=r'^[A-Za-z0-9_.:-]+$')]
    writes=[Depends(authorize)]
    # Explicit endpoint signatures keep generated OpenAPI exact and client-friendly.
    @app.post('/api/v1/simulation/tick',response_model=SimulationCommandResult,dependencies=writes)
    def tick(body:TickRequest,key:Key): return service.mutate('tick',body,key)
    @app.post('/api/v1/simulation/reset',response_model=SimulationCommandResult,dependencies=writes)
    def reset(body:MutationRequest,key:Key): return service.mutate('reset',body,key)
    @app.post('/api/v1/simulation/pause',response_model=SimulationCommandResult,dependencies=writes)
    def pause(body:MutationRequest,key:Key): return service.mutate('pause',body,key)
    @app.post('/api/v1/simulation/resume',response_model=SimulationCommandResult,dependencies=writes)
    def resume(body:MutationRequest,key:Key): return service.mutate('resume',body,key)
    @app.post('/api/v1/scenarios/activate',response_model=SimulationCommandResult,dependencies=writes)
    def activate(body:ActivateRequest,key:Key): return service.mutate('activate',body,key)
    @app.post('/api/v1/simulation/commands',response_model=SimulationCommandResult,dependencies=writes)
    def commands(body:CommandRequest,key:Key): return service.mutate('commands',body,key)
    return app
