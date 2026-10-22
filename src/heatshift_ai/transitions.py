"""Explicit worker commands with atomic state/event publication."""
import logging
from dataclasses import dataclass, replace
from typing import Callable

from .clock import SimulationClock
from .enums import AvailabilityStatus, WorkStatus, ZoneKind
from .serialization import to_json
from .state import SimulationState
from .validation import identifier, nonempty
from .workers import Worker

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TransitionEvent:
    event_id: int
    action: str
    worker_id: str
    elapsed_seconds: int
    reason: str
    old_state: SimulationState
    new_state: SimulationState
    data_origin: str = 'simulated'


class WorkerStateManager(SimulationClock):
    """Use as the sole state owner for assignments, activity and ticks.

    Successful worker commands emit one event; rejected/no-op commands emit none.
    Clock ticks/pause/resume are clock operations, not worker-transition events.
    """

    def __init__(self, state: SimulationState, **kwargs) -> None:
        super().__init__(state, **kwargs)
        self._events: tuple[TransitionEvent, ...] = ()

    @property
    def events(self) -> tuple[TransitionEvent, ...]:
        with self._lock:
            return self._events

    def export_events_json(self) -> str:
        with self._lock:
            return to_json(self._events)

    def reset(self) -> SimulationState:
        with self._lock:
            state = super().reset()
            self._events = ()
            return state

    @staticmethod
    def _worker(state: SimulationState, worker_id: str) -> Worker:
        identifier(worker_id, 'worker_id')
        worker = next((w for w in state.workers if w.worker_id == worker_id), None)
        if worker is None:
            raise ValueError(f'unknown worker_id: {worker_id}')
        return worker

    def _transition(self, action: str, worker_id: str, reason: str,
                    operation: Callable[[SimulationClock, Worker], SimulationState]) -> SimulationState:
        with self._lock:
            try:
                nonempty(reason, 'reason')
                old = self._state
                worker = self._worker(old, worker_id)
                # Reuse existing invariant checks against a private candidate owner.
                candidate = operation(SimulationClock(old), worker)
                candidate = replace(candidate)  # Full final validation before publication.
                if candidate == old:
                    raise ValueError(f'{action} would not change worker state')
                event = TransitionEvent(event_id=len(self._events) + 1, action=action,
                    worker_id=worker_id, elapsed_seconds=old.time.elapsed_seconds,
                    reason=reason, old_state=old, new_state=candidate)
                events = self._events + (event,)
            except ValueError as exc:
                logger.warning('%s rejected worker=%r: %s', action, worker_id, exc)
                raise
            self._state, self._events = candidate, events
            logger.info('%s committed worker=%s event=%d', action, worker_id, event.event_id)
            return candidate

    def start_work(self, *, worker_id: str, reason: str) -> SimulationState:
        def apply(clock, worker):
            if worker.work_status != WorkStatus.IDLE or worker.current_task_id is None:
                raise ValueError('start_work requires an idle worker with a reserved task')
            if worker.availability_status != AvailabilityStatus.AVAILABLE:
                raise ValueError('start_work requires an available worker')
            return clock.start_task(task_id=worker.current_task_id)
        return self._transition('start_work', worker_id, reason, apply)

    def stop_work(self, *, worker_id: str, reason: str) -> SimulationState:
        def apply(clock, worker):
            if worker.work_status != WorkStatus.WORKING:
                raise ValueError('stop_work requires a working worker')
            return clock.unassign_task(task_id=worker.current_task_id)
        return self._transition('stop_work', worker_id, reason, apply)

    def start_rest(self, *, worker_id: str, zone_id: str, reason: str) -> SimulationState:
        def apply(clock, worker):
            if worker.work_status == WorkStatus.RESTING:
                raise ValueError('worker is already resting')
            if worker.current_task_id is not None:
                clock.unassign_task(task_id=worker.current_task_id)
            return clock.start_rest(worker_id=worker_id, zone_id=zone_id)
        return self._transition('start_rest', worker_id, reason, apply)

    def end_rest(self, *, worker_id: str, reason: str) -> SimulationState:
        return self._transition('end_rest', worker_id, reason,
                                lambda clock, worker: clock.end_rest(worker_id=worker_id))

    def change_zone(self, *, worker_id: str, zone_id: str, reason: str) -> SimulationState:
        def apply(clock, worker):
            identifier(zone_id, 'zone_id')
            state = clock.state
            zone = next((z for z in state.zones if z.zone_id == zone_id), None)
            if zone is None:
                raise ValueError(f'unknown zone_id: {zone_id}')
            if worker.current_zone_id == zone_id:
                raise ValueError('worker is already in requested zone')
            if worker.work_status == WorkStatus.RESTING and zone.kind != ZoneKind.REST:
                raise ValueError('resting worker must remain in a rest zone')
            # SimulationState checks the task allowed-zone relation as well.
            updated = replace(worker, current_zone_id=zone_id)
            return replace(state,
                workers=tuple(updated if w.worker_id == worker_id else w for w in state.workers),
                assignments=tuple(replace(a, zone_id=zone_id) if a.worker_id == worker_id else a for a in state.assignments))
        return self._transition('change_zone', worker_id, reason, apply)

    def change_task(self, *, worker_id: str, task_id: str, reason: str,
                    zone_id: str | None = None) -> SimulationState:
        def apply(clock, worker):
            identifier(task_id, 'task_id')
            if worker.current_task_id is None or worker.work_status == WorkStatus.RESTING:
                raise ValueError('change_task requires a current assignment')
            if worker.current_task_id == task_id:
                raise ValueError('worker is already assigned to requested task')
            clock.unassign_task(task_id=worker.current_task_id)
            clock.assign_task(worker_id=worker_id, task_id=task_id, zone_id=zone_id)
            if worker.work_status == WorkStatus.WORKING:
                clock.start_task(task_id=task_id)
                # No idle/rest time elapsed: work remains uninterrupted.
                return replace(clock.state, workers=tuple(
                    replace(w, current_work_period_seconds=worker.current_work_period_seconds)
                    if w.worker_id == worker_id else w for w in clock.state.workers))
            return clock.state
        return self._transition('change_task', worker_id, reason, apply)

    def mark_unavailable(self, *, worker_id: str, reason: str) -> SimulationState:
        def apply(clock, worker):
            if worker.availability_status == AvailabilityStatus.UNAVAILABLE:
                raise ValueError('worker is already unavailable')
            if worker.current_task_id is not None:
                clock.unassign_task(task_id=worker.current_task_id)
            return replace(clock.state, workers=tuple(
                replace(w, availability_status=AvailabilityStatus.UNAVAILABLE) if w.worker_id == worker_id else w
                for w in clock.state.workers))
        return self._transition('mark_unavailable', worker_id, reason, apply)

    def mark_available(self, *, worker_id: str, reason: str) -> SimulationState:
        def apply(clock, worker):
            if worker.work_status == WorkStatus.RESTING:
                raise ValueError('end_rest before marking worker available')
            if worker.availability_status == AvailabilityStatus.AVAILABLE:
                raise ValueError('worker is already available')
            return replace(clock.state, workers=tuple(
                replace(w, availability_status=AvailabilityStatus.AVAILABLE) if w.worker_id == worker_id else w
                for w in clock.state.workers))
        return self._transition('mark_available', worker_id, reason, apply)

    def assign_task(self, *, worker_id: str, task_id: str, zone_id: str | None = None,
                    reason: str = 'explicit assignment') -> SimulationState:
        return self._transition('assign_task', worker_id, reason,
            lambda clock, worker: clock.assign_task(worker_id=worker_id, task_id=task_id, zone_id=zone_id))

    def _assigned_worker_id(self, task_id: str) -> str:
        identifier(task_id, 'task_id')
        task = next((t for t in self._state.tasks if t.task_id == task_id), None)
        if task is None or task.assigned_worker_id is None:
            logger.warning('task command rejected: task=%r has no assignment', task_id)
            raise ValueError('task must exist and have an assignment')
        return task.assigned_worker_id

    def unassign_task(self, *, task_id: str, reason: str = 'explicit release') -> SimulationState:
        with self._lock:
            worker_id = self._assigned_worker_id(task_id)
            return self._transition('unassign_task', worker_id, reason,
                                    lambda clock, worker: clock.unassign_task(task_id=task_id))

    def start_task(self, *, task_id: str, reason: str = 'explicit work start') -> SimulationState:
        with self._lock:
            return self.start_work(worker_id=self._assigned_worker_id(task_id), reason=reason)
