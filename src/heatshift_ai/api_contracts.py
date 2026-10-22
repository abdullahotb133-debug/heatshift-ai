"""Version 1 HTTP projections. Domain dataclasses remain the authoritative state."""
from typing import Annotated, Generic, Literal, TypeVar
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .enums import (AcclimatizationStatus, AvailabilityStatus, WorkStatus,
                    TaskStatus, WorkloadCategory, ZoneKind, MeasurementSource)
from .engineering_scenarios import EngineeringScenarioName

ID = Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')]
Seconds = Annotated[int, Field(strict=True, ge=0)]

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Context(Contract):
    schema_version: Literal['1.0'] = '1.0'
    simulation_id: ID
    instance_id: str
    state_version: Seconds
    elapsed_seconds: Seconds
    source: Literal['synthetic_simulator'] = 'synthetic_simulator'
    time_unit: Literal['s'] = 's'

class WorkerSnapshot(Contract):
    worker_id: ID
    display_name: str
    current_zone_id: ID
    qualifications: list[str]
    acclimatization_status: AcclimatizationStatus
    clothing_profile: str
    current_task_id: ID | None
    work_status: WorkStatus
    availability_status: AvailabilityStatus
    exposure_elapsed_seconds: Seconds
    rest_elapsed_seconds: Seconds
    current_work_period_seconds: Seconds
    current_rest_period_seconds: Seconds

class TaskSnapshot(Contract):
    task_id: ID
    task_name: str
    workload_category: WorkloadCategory
    allowed_zone_ids: list[ID]
    estimated_metabolic_rate_watts: float | None
    required_qualifications: list[str]
    task_status: TaskStatus
    assigned_worker_id: ID | None

class Condition(Contract):
    name: str
    value: float | None
    unit: str

class EnvironmentalObservation(Contract):
    zone_id: ID
    elapsed_seconds: Seconds
    observed_at_seconds: Seconds
    source: MeasurementSource
    quality: Literal['good', 'missing', 'stale', 'invalid']
    wbgt_celsius: float | None
    wbgt_unit: Literal['degC'] = 'degC'
    wbgt_kind: Literal['calculated', 'unavailable', 'estimated']
    method: str | None
    source_metadata: dict[str, str]
    conditions: list[Condition]

class ZoneSnapshot(Contract):
    zone_id: ID
    kind: ZoneKind
    environment: EnvironmentalObservation

class SimulationEvent(Contract):
    event_id: str
    elapsed_seconds: Seconds
    action: str
    worker_id: ID | None = None
    reason: str
    source: Literal['simulated', 'scripted_scenario_input', 'api_command']
    old_worker: WorkerSnapshot | None = None
    new_worker: WorkerSnapshot | None = None

class AssignmentSnapshot(Contract):
    worker_id: ID
    task_id: ID
    zone_id: ID
    started_at_elapsed_seconds: Seconds

class SimulationSnapshot(Context):
    zones: list[ZoneSnapshot]
    workers: list[WorkerSnapshot]
    tasks: list[TaskSnapshot]
    assignments: list[AssignmentSnapshot]
    events: list[SimulationEvent]
    random_seed: int
    tick_seconds: Seconds
    scenario: EngineeringScenarioName
    scenario_input: dict
    scenario_phase: Literal['scheduled', 'active', 'complete', 'stopped']
    paused: bool
    valid: Literal[True] = True

T = TypeVar('T')
class Collection(Context, Generic[T]):
    items: list[T]

class ScenarioInfo(Contract):
    scenario_id: EngineeringScenarioName
    version: int
    parameters: dict

class MutationRequest(Contract):
    schema_version: Literal['1.0']
    simulation_id: ID
    instance_id: str
    expected_state_version: Seconds

class TickRequest(MutationRequest):
    delta_seconds: Annotated[int, Field(strict=True, ge=1, le=86400)] = 10

class ActivateRequest(MutationRequest):
    scenario_id: EngineeringScenarioName
    failure_mode: Literal['missing', 'stale', 'invalid'] = 'missing'

class SimulationCommand(Contract):
    action: Literal['assign_task','unassign_task','start_work','stop_work','start_rest',
                    'end_rest','change_zone','change_task','mark_unavailable','mark_available']
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    worker_id: ID | None = None
    task_id: ID | None = None
    zone_id: ID | None = None

    @model_validator(mode='after')
    def arguments(self):
        required = {'assign_task': {'worker_id','task_id'}, 'unassign_task': {'task_id'},
                    'start_rest': {'worker_id','zone_id'}, 'change_zone': {'worker_id','zone_id'},
                    'change_task': {'worker_id','task_id'}}.get(self.action, {'worker_id'})
        optional = {'zone_id'} if self.action in ('assign_task','change_task') else set()
        provided = {k for k in ('worker_id','task_id','zone_id') if getattr(self,k) is not None}
        if not required <= provided or provided - required - optional:
            raise ValueError('incorrect command arguments')
        if not self.reason.strip(): raise ValueError('reason must not be blank')
        return self

class CommandRequest(MutationRequest):
    commands: Annotated[list[SimulationCommand], Field(min_length=1, max_length=32)]

class SimulationCommandResult(Context):
    status: Literal['applied'] = 'applied'
    idempotency_key: str
    event_ids: list[str]
    snapshot: SimulationSnapshot

class ErrorDetail(Contract):
    code: str
    message: str

class ErrorResponse(Contract):
    schema_version: Literal['1.0'] = '1.0'
    error: ErrorDetail

class Health(Contract):
    schema_version: Literal['1.0'] = '1.0'
    status: Literal['ok'] = 'ok'
    component: Literal['A'] = 'A'
