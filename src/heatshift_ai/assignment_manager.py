"""Explicit atomic setup operations over immutable simulation snapshots."""
import logging
from dataclasses import dataclass, replace
from threading import RLock

from .assignments import Assignment
from .enums import AvailabilityStatus, TaskStatus, WorkStatus, ZoneKind
from .state import SimulationState
from .validation import identifier

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AssignmentRequest:
    worker_id: str
    task_id: str
    zone_id: str | None = None

    def __post_init__(self) -> None:
        identifier(self.worker_id, 'worker_id')
        identifier(self.task_id, 'task_id')
        if self.zone_id is not None:
            identifier(self.zone_id, 'zone_id')


def _assign(state: SimulationState, request: AssignmentRequest) -> SimulationState:
    worker = next((w for w in state.workers if w.worker_id == request.worker_id), None)
    task = next((t for t in state.tasks if t.task_id == request.task_id), None)
    if worker is None:
        raise ValueError(f'unknown worker_id: {request.worker_id}')
    if task is None:
        raise ValueError(f'unknown task_id: {request.task_id}')
    if worker.work_status == WorkStatus.RESTING:
        raise ValueError(f'worker {worker.worker_id} is resting')
    if worker.availability_status != AvailabilityStatus.AVAILABLE:
        raise ValueError(f'worker {worker.worker_id} is unavailable')
    if worker.current_task_id is not None or any(a.worker_id == worker.worker_id for a in state.assignments):
        raise ValueError(f'worker {worker.worker_id} already has an active task')
    if task.assigned_worker_id is not None or any(a.task_id == task.task_id for a in state.assignments):
        raise ValueError(f'task {task.task_id} already has an assigned worker')
    if task.task_status != TaskStatus.PENDING:
        raise ValueError(f'task {task.task_id} must be pending')
    if worker.work_status != WorkStatus.IDLE:
        raise ValueError(f'worker {worker.worker_id} must be idle')
    missing = task.required_qualifications - worker.qualifications
    if missing:
        raise ValueError(f'worker {worker.worker_id} lacks required qualifications: {sorted(missing)}')
    zone_id = worker.current_zone_id if request.zone_id is None else request.zone_id
    zone = next((z for z in state.zones if z.zone_id == zone_id), None)
    if zone is None or zone.kind != ZoneKind.WORK or zone_id not in task.allowed_zone_ids:
        raise ValueError(f'zone {zone_id} must be a known work zone allowed by task {task.task_id}')
    updated_worker = replace(worker, current_zone_id=zone_id, current_task_id=task.task_id)
    updated_task = replace(task, assigned_worker_id=worker.worker_id, task_status=TaskStatus.ASSIGNED)
    assignment = Assignment(worker_id=worker.worker_id, task_id=task.task_id, zone_id=zone_id,
                            started_at_elapsed_seconds=state.time.elapsed_seconds)
    return replace(state,
                   workers=tuple(updated_worker if w.worker_id == worker.worker_id else w for w in state.workers),
                   tasks=tuple(updated_task if t.task_id == task.task_id else t for t in state.tasks),
                   assignments=state.assignments + (assignment,))


class AssignmentManager:
    """Publish a validated snapshot once per operation; never mutate input models.

    Explicit zone_id permits setup relocation; omission retains current location.
    Assignment reserves work (ASSIGNED/IDLE); it does not start execution.
    """

    def __init__(self, state: SimulationState, *, initial_assignments: tuple[AssignmentRequest, ...] = ()) -> None:
        self._lock = RLock()
        try:
            if not isinstance(state, SimulationState):
                raise ValueError('state must be SimulationState')
            if not isinstance(initial_assignments, tuple) or any(
                    not isinstance(r, AssignmentRequest) for r in initial_assignments):
                raise ValueError('initial_assignments must be a tuple of AssignmentRequest models')
            candidate = replace(state)  # Revalidate the entire starting snapshot.
            for request in initial_assignments:
                candidate = _assign(candidate, request)
        except ValueError as exc:
            logger.warning('initial assignments rejected: %s', exc)
            raise
        self._state = candidate
        logger.info('initial assignments committed: count=%d', len(initial_assignments))

    @property
    def state(self) -> SimulationState:
        with self._lock:
            return self._state

    def assign_task(self, *, worker_id: str, task_id: str, zone_id: str | None = None) -> SimulationState:
        with self._lock:
            try:
                candidate = _assign(self._state, AssignmentRequest(worker_id=worker_id, task_id=task_id, zone_id=zone_id))
            except ValueError as exc:
                logger.warning('assign_task rejected worker=%r task=%r zone=%r: %s', worker_id, task_id, zone_id, exc)
                raise
            self._state = candidate
            logger.info('assign_task committed worker=%s task=%s zone=%s', worker_id, task_id,
                        next(a.zone_id for a in candidate.assignments if a.task_id == task_id))
            return candidate

    def unassign_task(self, *, task_id: str) -> SimulationState:
        """Release an assigned/in-progress task to PENDING, worker to IDLE.

        Retains location, availability and all exposure/rest counters. Does not
        mark completion, reverse elapsed time or perform automatic reassignment.
        """
        with self._lock:
            try:
                identifier(task_id, 'task_id')
                state = self._state
                task = next((t for t in state.tasks if t.task_id == task_id), None)
                if task is None:
                    raise ValueError(f'unknown task_id: {task_id}')
                assignment = next((a for a in state.assignments if a.task_id == task_id), None)
                if assignment is None:
                    raise ValueError(f'task {task_id} has no active assignment')
                worker = next(w for w in state.workers if w.worker_id == assignment.worker_id)
                updated_worker = replace(worker, current_task_id=None, work_status=WorkStatus.IDLE,
                                         current_work_period_seconds=0, current_rest_period_seconds=0)
                updated_task = replace(task, assigned_worker_id=None, task_status=TaskStatus.PENDING)
                candidate = replace(state,
                    workers=tuple(updated_worker if w.worker_id == worker.worker_id else w for w in state.workers),
                    tasks=tuple(updated_task if t.task_id == task_id else t for t in state.tasks),
                    assignments=tuple(a for a in state.assignments if a.task_id != task_id))
            except ValueError as exc:
                logger.warning('unassign_task rejected task=%r: %s', task_id, exc)
                raise
            self._state = candidate
            logger.info('unassign_task committed worker=%s task=%s', worker.worker_id, task_id)
            return candidate
