"""Single-writer HTTP application service; no FastAPI or safety decisions."""
from dataclasses import replace
from threading import RLock
from uuid import uuid4
from .engineering_scenarios import EngineeringScenarioRunner, load_scenario
from .integrated_engine import EngineCommand
from .api_contracts import SimulationSnapshot, SimulationCommandResult

class ServiceError(Exception):
    def __init__(self, status, code, message):
        self.status,self.code,self.message=status,code,message

class SimulationService:
    def __init__(self, seed=42, *, instance_id=None, max_operations=10000):
        self._lock=RLock()
        self._runner=EngineeringScenarioRunner(load_scenario('NORMAL_OPERATION',seed=seed))
        self._runner.start()
        self._instance=instance_id or str(uuid4())
        self._version=0
        self._ledger={}
        self._operations=()
        self._max_operations=max_operations

    def _snapshot(self, runner, version, operations):
        raw=runner.snapshot()
        events=[]
        epoch=operations[0]['event_id'] if operations and operations[0]['action']=='reset' else 'initial'
        for event in raw['events']:
            wid=event['worker_id']
            events.append(dict(event_id=f"{epoch}-worker-{event['event_id']}",elapsed_seconds=event['elapsed_seconds'],
                action=event['action'],worker_id=wid,reason=event['reason'],source='simulated',
                old_worker=next(w for w in event['old_state']['workers'] if w['worker_id']==wid),
                new_worker=next(w for w in event['new_state']['workers'] if w['worker_id']==wid)))
        events.extend(operations)
        events.sort(key=lambda e:e['elapsed_seconds'])
        zones=raw['zones']
        for zone in zones:
            obs=zone['environment']; meta=obs['source_metadata']
            obs.update(observed_at_seconds=int(meta['observed_at_seconds']),quality=meta['quality'],
                       wbgt_kind=meta['wbgt_kind'])
        return SimulationSnapshot.model_validate(dict(simulation_id=raw['simulation_id'],instance_id=self._instance,
            state_version=version,elapsed_seconds=raw['simulated_time_seconds'],zones=zones,
            workers=raw['workers'],tasks=raw['tasks'],assignments=raw['assignments'],events=events,
            random_seed=raw['random_seed'],tick_seconds=raw['tick_seconds'],scenario=raw['scenario'],
            scenario_input=raw['scenario_input'],scenario_phase=raw['scenario_phase'],paused=raw['paused']))

    def snapshot(self):
        with self._lock: return self._snapshot(self._runner,self._version,self._operations)

    def mutate(self, action, request, key):
        # Validation, eligibility, response serialization and replay-cache publication
        # all occur under the same lock and before committing the candidate.
        with self._lock:
            fingerprint=(action,request.model_dump_json())
            if key in self._ledger:
                old_fingerprint,result=self._ledger[key]
                if fingerprint!=old_fingerprint:
                    raise ServiceError(409,'idempotency_conflict','Key already used for a different request')
                return result.model_copy(deep=True)
            if request.instance_id!=self._instance or request.simulation_id!=self._runner.config.simulation_id:
                raise ServiceError(409,'simulation_conflict','Read a snapshot from the current service instance')
            if request.expected_state_version!=self._version:
                raise ServiceError(409,'stale_version','State changed; read a fresh snapshot')
            if len(self._ledger)>=self._max_operations:
                raise ServiceError(503,'operation_capacity','In-memory operation capacity reached; export and restart')
            candidate=self._runner.fork()
            try:
                if action=='tick': candidate.step(request.delta_seconds)
                elif action=='reset':
                    d=candidate.definition
                    definition=replace(d,start_seconds=0,failure_start_seconds=d.failure_start_seconds-d.start_seconds)
                    candidate=EngineeringScenarioRunner(definition,config=candidate.config)
                    candidate.start()
                elif action=='pause': candidate.engine.pause()
                elif action=='resume': candidate.engine.resume()
                elif action=='commands':
                    candidate.engine.execute_batch(tuple(EngineCommand(**c.model_dump()) for c in request.commands))
                elif action=='activate':
                    now=candidate.engine.get_state().simulation.time.elapsed_seconds
                    definition=load_scenario(request.scenario_id,seed=candidate.config.seed)
                    definition=replace(definition,start_seconds=now,
                        failure_start_seconds=now+definition.failure_start_seconds,failure_mode=request.failure_mode)
                    activated=EngineeringScenarioRunner(definition,config=candidate.config)
                    activated.activate_on(candidate.engine)
                    candidate=activated
                else: raise ValueError('unsupported service operation')
            except (ValueError,LookupError) as exc:
                raise ServiceError(422,'domain_rejection',str(exc)) from exc
            version=self._version+1
            event=dict(event_id=f'api-{version}',elapsed_seconds=candidate.engine.get_state().simulation.time.elapsed_seconds,
                action=action,reason='explicit HTTP request',source='api_command')
            operations=(() if action=='reset' else self._operations)+(event,)
            snapshot=self._snapshot(candidate,version,operations)
            previous_ids={e.event_id for e in self.snapshot().events} if action!='reset' else set()
            result=SimulationCommandResult(**{k:getattr(snapshot,k) for k in ('simulation_id','instance_id','state_version','elapsed_seconds')},
                idempotency_key=key,event_ids=[e.event_id for e in snapshot.events if e.event_id not in previous_ids],snapshot=snapshot)
            # Force JSON encoding before publication, including finite numeric validation.
            result.model_dump_json()
            self._runner,self._version,self._operations=candidate,version,operations
            self._ledger[key]=(fingerprint,result.model_copy(deep=True))
            return result
