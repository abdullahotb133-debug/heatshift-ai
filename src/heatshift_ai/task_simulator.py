"""Configurable synthetic task definitions and fresh, unassigned task states."""
import logging
from dataclasses import dataclass, field

from .enums import WorkloadCategory, ZoneKind
from .serialization import to_json
from .tasks import Task
from .validation import identifier, string_set
from .zones import Zone

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TaskDefinition:
    """Reusable scenario input; no execution status or worker assignment."""
    task_id: str
    task_name: str
    workload_category: WorkloadCategory
    required_qualifications: frozenset[str]
    allowed_zone_ids: frozenset[str]
    estimated_metabolic_rate_watts: float | None = None

    def __post_init__(self) -> None:
        # Reuse the existing model's field validation without changing its schema.
        validated = self.new_task()
        object.__setattr__(self, 'workload_category', validated.workload_category)
        if not self.required_qualifications:
            raise ValueError(f'task {self.task_id}: required_qualifications must not be empty')

    def new_task(self, *, task_id: str | None = None) -> Task:
        """Create an independent pending/unassigned execution snapshot.

        A new ID permits reuse within the same SimulationState. Later execution
        changes use dataclasses.replace and full SimulationState validation.
        """
        return Task(
            task_id=self.task_id if task_id is None else task_id,
            task_name=self.task_name,
            workload_category=self.workload_category,
            required_qualifications=self.required_qualifications,
            allowed_zone_ids=self.allowed_zone_ids,
            estimated_metabolic_rate_watts=self.estimated_metabolic_rate_watts,
        )


def default_task_definitions() -> tuple[TaskDefinition, ...]:
    """Illustrative manual/assisted scenarios, not job-specific measurements."""
    rows = (
        ('T-01', 'Site Inspection', WorkloadCategory.LIGHT,
         ('inspection',), ('ZONE_A', 'ZONE_B', 'ZONE_C')),
        ('T-02', 'Material Handling', WorkloadCategory.HEAVY,
         ('manual_handling',), ('ZONE_A', 'ZONE_B')),
        ('T-03', 'Equipment Operation', WorkloadCategory.LIGHT,
         ('equipment_operation',), ('ZONE_B', 'ZONE_C')),
        ('T-04', 'Reinforcement Installation', WorkloadCategory.HEAVY,
         ('manual_handling', 'reinforcement_installation'), ('ZONE_B',)),
        ('T-05', 'Concrete Placement', WorkloadCategory.HEAVY,
         ('manual_handling', 'concrete_placement'), ('ZONE_C',)),
        ('T-06', 'Surveying', WorkloadCategory.MODERATE,
         ('surveying',), ('ZONE_A', 'ZONE_B', 'ZONE_C')),
    )
    return tuple(TaskDefinition(task_id=tid, task_name=name, workload_category=load,
                                required_qualifications=frozenset(quals),
                                allowed_zone_ids=frozenset(zones))
                 for tid, name, load, quals, zones in rows)


def _default_zones() -> tuple[Zone, ...]:
    return tuple(Zone(zone_id=z, kind=ZoneKind.WORK) for z in ('ZONE_A', 'ZONE_B', 'ZONE_C')) + (
        Zone(zone_id='REST_ZONE', kind=ZoneKind.REST),)


@dataclass(frozen=True, kw_only=True)
class TaskConfig:
    count: int = 6
    definitions: tuple[TaskDefinition, ...] = field(default_factory=default_task_definitions)
    zones: tuple[Zone, ...] = field(default_factory=_default_zones)
    known_qualifications: frozenset[str] = frozenset({
        'inspection', 'manual_handling', 'equipment_operation', 'rigging',
        'reinforcement_installation', 'concrete_placement', 'surveying',
    })

    def __post_init__(self) -> None:
        if type(self.count) is not int or self.count < 1:
            raise ValueError('count must be a positive integer')
        if not isinstance(self.definitions, tuple) or len(self.definitions) != self.count:
            raise ValueError('definitions must be a tuple matching configured task count')
        if any(not isinstance(d, TaskDefinition) for d in self.definitions):
            raise ValueError('definitions must contain TaskDefinition models')
        if len({d.task_id for d in self.definitions}) != len(self.definitions):
            raise ValueError('definitions contain duplicate task_id')
        if not isinstance(self.zones, tuple) or not self.zones or any(not isinstance(z, Zone) for z in self.zones):
            raise ValueError('zones must be a non-empty tuple of Zone models')
        zones = {z.zone_id: z for z in self.zones}
        if len(zones) != len(self.zones):
            raise ValueError('zones contain duplicate zone_id')
        string_set(self.known_qualifications, 'known_qualifications')
        for definition in self.definitions:
            missing = definition.required_qualifications - self.known_qualifications
            if missing:
                raise ValueError(f'task {definition.task_id}: unknown qualifications {sorted(missing)}')
            for zone_id in sorted(definition.allowed_zone_ids):
                if zone_id not in zones or zones[zone_id].kind != ZoneKind.WORK:
                    raise ValueError(f'task {definition.task_id}: allowed zone {zone_id} must reference a work zone')


@dataclass(frozen=True, kw_only=True)
class TaskSimulator:
    """Deterministic catalog; no random sampling, assignments or execution loop."""
    config: TaskConfig = field(default_factory=TaskConfig)
    _tasks: tuple[Task, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.config, TaskConfig):
            raise ValueError('config must be TaskConfig')
        object.__setattr__(self, '_tasks', tuple(d.new_task() for d in self.config.definitions))
        logger.debug('Initialized %d pending synthetic tasks', len(self._tasks))

    def list_definitions(self) -> tuple[TaskDefinition, ...]:
        return self.config.definitions

    def get_definition(self, task_id: str) -> TaskDefinition:
        identifier(task_id, 'task_id')
        for definition in self.config.definitions:
            if definition.task_id == task_id:
                return definition
        raise KeyError(f'unknown task_id: {task_id}')

    def list_tasks(self) -> tuple[Task, ...]:
        return self._tasks

    def get_task(self, task_id: str) -> Task:
        identifier(task_id, 'task_id')
        for task in self._tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(f'unknown task_id: {task_id}')

    def export_json(self) -> str:
        return to_json({'data_origin': 'simulated', 'config': self.config, 'tasks': self._tasks})
