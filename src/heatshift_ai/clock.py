"""Explicit simulated time; no sleeping, physiological model or automatic dispatch."""
import logging
from dataclasses import replace

from .assignment_manager import AssignmentManager, AssignmentRequest
from .enums import AvailabilityStatus, TaskStatus, WorkStatus, ZoneKind
from .state import SimulationState
from .validation import identifier, seconds

logger = logging.getLogger(__name__)


class SimulationClock(AssignmentManager):
    """One state owner for clock, assignments and explicit activity transitions.

    Pause only suppresses ticks. Reset restores the exact configured initial
    snapshot (including nonzero historical counters) and resumes the clock.
    """

    def __init__(self, state: SimulationState, *, tick_seconds: int | None = None,
                 initial_assignments: tuple[AssignmentRequest, ...] = ()) -> None:
        if tick_seconds is not None:
            seconds(tick_seconds, 'tick_seconds', positive=True)
            if not isinstance(state, SimulationState):
                raise ValueError('state must be SimulationState')
            state = replace(state, time=replace(state.time, tick_seconds=tick_seconds))
        super().__init__(state, initial_assignments=initial_assignments)
        self._initial_state = self._state
        self._paused = False

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._paused

    def pause(self) -> None:
        with self._lock:
            self._paused = True
            logger.info('simulation paused')

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            logger.info('simulation resumed')

    def reset(self) -> SimulationState:
        with self._lock:
            self._state = self._initial_state
            self._paused = False
            logger.info('simulation reset to configured initial snapshot')
            return self._state

    def tick(self, delta_seconds: int | None = None) -> SimulationState:
        with self._lock:
            try:
                delta = self._state.time.tick_seconds if delta_seconds is None else delta_seconds
                seconds(delta, 'delta_seconds', positive=True)
                if self._paused:
                    logger.debug('tick ignored while paused')
                    return self._state
                state = self._state
                zones = {z.zone_id: z for z in state.zones}
                workers = []
                for worker in state.workers:
                    working = worker.work_status == WorkStatus.WORKING and zones[worker.current_zone_id].kind == ZoneKind.WORK
                    resting = worker.work_status == WorkStatus.RESTING
                    workers.append(replace(worker,
                        exposure_elapsed_seconds=worker.exposure_elapsed_seconds + (delta if working else 0),
                        rest_elapsed_seconds=worker.rest_elapsed_seconds + (delta if resting else 0),
                        current_work_period_seconds=worker.current_work_period_seconds + delta if working else 0,
                        current_rest_period_seconds=worker.current_rest_period_seconds + delta if resting else 0))
                candidate = replace(state, workers=tuple(workers),
                                    time=replace(state.time, elapsed_seconds=state.time.elapsed_seconds + delta))
            except ValueError as exc:
                logger.warning('tick rejected: %s', exc)
                raise
            self._state = candidate
            logger.debug('tick committed delta=%d elapsed=%d', delta, candidate.time.elapsed_seconds)
            return candidate

    def start_task(self, *, task_id: str) -> SimulationState:
        """Explicitly start a reserved task; elapsed time is unchanged."""
        with self._lock:
            try:
                identifier(task_id, 'task_id')
                state = self._state
                task = next((t for t in state.tasks if t.task_id == task_id), None)
                if task is None or task.task_status != TaskStatus.ASSIGNED:
                    raise ValueError('start_task requires a known assigned task')
                worker = next(w for w in state.workers if w.worker_id == task.assigned_worker_id)
                updated = replace(worker, work_status=WorkStatus.WORKING,
                                  current_work_period_seconds=0, current_rest_period_seconds=0)
                candidate = replace(state,
                    workers=tuple(updated if w.worker_id == worker.worker_id else w for w in state.workers),
                    tasks=tuple(replace(t, task_status=TaskStatus.IN_PROGRESS) if t.task_id == task_id else t for t in state.tasks))
            except ValueError as exc:
                logger.warning('start_task rejected task=%r: %s', task_id, exc)
                raise
            self._state = candidate
            logger.info('start_task committed task=%s', task_id)
            return candidate

    def start_rest(self, *, worker_id: str, zone_id: str) -> SimulationState:
        """Explicitly move an unassigned idle worker to rest; mark unavailable."""
        return self._rest_transition(worker_id=worker_id, zone_id=zone_id, starting=True)

    def end_rest(self, *, worker_id: str) -> SimulationState:
        """Explicitly release rest to idle/available; retain rest-zone location."""
        return self._rest_transition(worker_id=worker_id, zone_id=None, starting=False)

    def _rest_transition(self, *, worker_id: str, zone_id: str | None, starting: bool) -> SimulationState:
        with self._lock:
            operation = 'start_rest' if starting else 'end_rest'
            try:
                identifier(worker_id, 'worker_id')
                state = self._state
                worker = next((w for w in state.workers if w.worker_id == worker_id), None)
                expected = WorkStatus.IDLE if starting else WorkStatus.RESTING
                if worker is None or worker.current_task_id is not None or worker.work_status != expected:
                    raise ValueError(f'{operation} requires an unassigned {expected.value} worker')
                if starting:
                    identifier(zone_id, 'zone_id')
                    if not any(z.zone_id == zone_id and z.kind == ZoneKind.REST for z in state.zones):
                        raise ValueError('start_rest requires a known rest zone')
                updated = replace(worker,
                    current_zone_id=zone_id if starting else worker.current_zone_id,
                    work_status=WorkStatus.RESTING if starting else WorkStatus.IDLE,
                    availability_status=AvailabilityStatus.UNAVAILABLE if starting else AvailabilityStatus.AVAILABLE,
                    current_work_period_seconds=0, current_rest_period_seconds=0)
                candidate = replace(state, workers=tuple(updated if w.worker_id == worker_id else w for w in state.workers))
            except ValueError as exc:
                logger.warning('%s rejected worker=%r: %s', operation, worker_id, exc)
                raise
            self._state = candidate
            logger.info('%s committed worker=%s', operation, worker_id)
            return candidate
