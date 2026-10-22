import logging
from dataclasses import dataclass, field
from typing import Literal
from .assignments import Assignment
from .enums import AvailabilityStatus, TaskStatus, WorkStatus, ZoneKind
from .tasks import Task
from .time import SimulationTime
from .workers import Worker
from .zones import Zone

logger = logging.getLogger(__name__)


def indexed(items: tuple, model: type, key: str) -> dict:
    if not isinstance(items, tuple) or any(not isinstance(item, model) for item in items):
        raise ValueError(f"{model.__name__} collection must be a tuple of {model.__name__} models")
    result = {getattr(item, key): item for item in items}
    if len(result) != len(items):
        raise ValueError(f"duplicate {key}")
    return result


@dataclass(frozen=True, kw_only=True)
class SimulationState:
    zones: tuple[Zone, ...] = ()
    workers: tuple[Worker, ...] = ()
    tasks: tuple[Task, ...] = ()
    assignments: tuple[Assignment, ...] = ()
    time: SimulationTime = field(default_factory=SimulationTime)
    random_seed: int = 0
    data_origin: Literal["simulated"] = field(default="simulated", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.time, SimulationTime):
            raise ValueError("time must be SimulationTime")
        if type(self.random_seed) is not int:
            raise ValueError("random_seed must be an integer")
        zones = indexed(self.zones, Zone, "zone_id")
        workers = indexed(self.workers, Worker, "worker_id")
        tasks = indexed(self.tasks, Task, "task_id")
        by_worker = indexed(self.assignments, Assignment, "worker_id")
        indexed(self.assignments, Assignment, "task_id")
        for worker in self.workers:
            if worker.current_zone_id not in zones:
                raise ValueError(f"worker {worker.worker_id}: unknown zone {worker.current_zone_id}")
            if worker.exposure_elapsed_seconds + worker.rest_elapsed_seconds > self.time.elapsed_seconds:
                raise ValueError(f"worker {worker.worker_id}: exposure plus rest exceeds elapsed simulation time")
            if worker.work_status == WorkStatus.RESTING and zones[worker.current_zone_id].kind != ZoneKind.REST:
                raise ValueError(f"worker {worker.worker_id}: resting requires a rest zone")
            assignment = by_worker.get(worker.worker_id)
            if worker.current_task_id != (assignment.task_id if assignment else None):
                raise ValueError(f"worker {worker.worker_id}: current_task_id does not match assignment")
            if worker.work_status == WorkStatus.WORKING and assignment is None:
                raise ValueError(f"worker {worker.worker_id}: working requires an assignment")
        for task in self.tasks:
            for zone_id in task.allowed_zone_ids:
                if zone_id not in zones or zones[zone_id].kind != ZoneKind.WORK:
                    raise ValueError(f"task {task.task_id}: allowed zone {zone_id} must reference a work zone")
            active = task.task_status in (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS)
            if active != (task.assigned_worker_id is not None):
                raise ValueError(f"task {task.task_id}: status and assigned_worker_id are inconsistent")
            if task.assigned_worker_id is not None:
                assignment = by_worker.get(task.assigned_worker_id)
                if assignment is None or assignment.task_id != task.task_id:
                    raise ValueError(f"task {task.task_id}: assigned_worker_id does not match assignment")
        for assignment in self.assignments:
            worker = workers.get(assignment.worker_id)
            task = tasks.get(assignment.task_id)
            if worker is None or task is None or assignment.zone_id not in zones:
                raise ValueError("assignment references an unknown worker, task or zone")
            if task.assigned_worker_id != worker.worker_id or worker.current_task_id != task.task_id:
                raise ValueError("assignment must match both worker and task references")
            if assignment.zone_id != worker.current_zone_id or assignment.zone_id not in task.allowed_zone_ids:
                raise ValueError("assignment zone must match worker zone and be allowed by task")
            if not task.required_qualifications <= worker.qualifications:
                raise ValueError("assigned worker lacks required qualifications")
            if worker.availability_status != AvailabilityStatus.AVAILABLE:
                raise ValueError("assigned worker must be available")
            expected = WorkStatus.WORKING if task.task_status == TaskStatus.IN_PROGRESS else WorkStatus.IDLE
            if worker.work_status != expected:
                raise ValueError("worker work_status does not match assigned task status")
            if assignment.started_at_elapsed_seconds > self.time.elapsed_seconds:
                raise ValueError("assignment start cannot be in the future")
        logger.debug("Validated simulation state: %d workers, %d tasks", len(workers), len(tasks))
