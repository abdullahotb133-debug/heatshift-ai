from dataclasses import replace
import json
import pytest

from heatshift_ai import (AssignmentRequest, SimulationClock, SimulationState, SimulationTime,
                         Task, Worker, Zone, to_json)


def initial():
    return SimulationState(
        zones=(Zone(zone_id='WORK', kind='work'), Zone(zone_id='REST', kind='rest')),
        workers=(Worker(worker_id='W-1', display_name='Fictional One', current_zone_id='WORK'),
                 Worker(worker_id='W-2', display_name='Fictional Two', current_zone_id='REST',
                        work_status='resting', availability_status='unavailable'),
                 Worker(worker_id='W-3', display_name='Fictional Three', current_zone_id='WORK')),
        tasks=(Task(task_id='T-1', task_name='Fixture', workload_category='light',
                    allowed_zone_ids=frozenset({'WORK'})),))


def active_clock(**kwargs):
    clock = SimulationClock(initial(), **kwargs)
    clock.assign_task(worker_id='W-1', task_id='T-1')
    clock.start_task(task_id='T-1')
    return clock


def test_one_tick_one_active_worker():
    clock = active_clock()
    assert clock.state.time.elapsed_seconds == 0
    state = clock.tick(10)
    worker = state.workers[0]
    assert state.time.elapsed_seconds == 10
    assert worker.work_elapsed_seconds == worker.exposure_elapsed_seconds == 10
    assert worker.current_work_period_seconds == 10
    assert worker.rest_elapsed_seconds == worker.current_rest_period_seconds == 0


def test_five_ticks_all_workers_and_identity():
    clock = active_clock()
    before = clock.state
    for _ in range(5):
        clock.tick()
    state = clock.state
    assert state.time.elapsed_seconds == 50
    working, resting, idle = state.workers
    assert working.exposure_elapsed_seconds == working.current_work_period_seconds == 50
    assert resting.rest_elapsed_seconds == resting.current_rest_period_seconds == 50
    assert resting.exposure_elapsed_seconds == 0
    assert idle.exposure_elapsed_seconds == idle.rest_elapsed_seconds == 0
    assert state.tasks is before.tasks and state.assignments is before.assignments
    for a, b in zip(before.workers, state.workers):
        assert (a.worker_id, a.display_name, a.qualifications) == (b.worker_id, b.display_name, b.qualifications)


def test_reserved_and_unavailable_workers_are_not_working():
    state = initial()
    state = replace(state, workers=state.workers[:2] + (replace(state.workers[2], availability_status='unavailable'),))
    clock = SimulationClock(state, initial_assignments=(AssignmentRequest(worker_id='W-1', task_id='T-1'),))
    result = clock.tick()
    assert result.workers[0].exposure_elapsed_seconds == result.workers[2].exposure_elapsed_seconds == 0


def test_custom_and_explicit_delta_no_construction_advance():
    clock = active_clock(tick_seconds=3)
    assert clock.state.time.elapsed_seconds == 0
    assert clock.tick().time.elapsed_seconds == 3
    assert clock.tick(7).time.elapsed_seconds == 10
    assert clock.tick().time.elapsed_seconds == 13
    assert clock.state.time.tick_seconds == 3
    clock = SimulationClock(replace(initial(), time=SimulationTime(tick_seconds=4)))
    assert clock.tick().time.elapsed_seconds == 4


def test_pause_resume_preserve_periods_and_no_catchup():
    clock = active_clock()
    before = clock.tick()
    clock.pause()
    clock.pause()
    assert clock.paused
    assert clock.tick(100) is before
    clock.resume()
    clock.resume()
    assert not clock.paused
    assert clock.tick().workers[0].current_work_period_seconds == 20
    assert clock.state.time.elapsed_seconds == 20


def test_cumulative_history_and_zero_time_interruptions():
    clock = active_clock()
    clock.tick()
    clock.unassign_task(task_id='T-1')
    assert clock.state.workers[0].current_work_period_seconds == 0
    assert clock.state.workers[0].work_elapsed_seconds == 10
    clock.start_rest(worker_id='W-1', zone_id='REST')
    clock.tick(5)
    clock.end_rest(worker_id='W-1')
    assert clock.state.workers[0].current_rest_period_seconds == 0
    clock.start_rest(worker_id='W-1', zone_id='REST')
    clock.tick(3)
    assert clock.state.workers[0].current_rest_period_seconds == 3
    clock.end_rest(worker_id='W-1')
    clock.assign_task(worker_id='W-1', task_id='T-1', zone_id='WORK')
    clock.start_task(task_id='T-1')
    clock.tick(2)
    worker = clock.state.workers[0]
    assert worker.work_elapsed_seconds == 12
    assert worker.rest_elapsed_seconds == 8
    assert worker.current_work_period_seconds == 2
    assert worker.current_rest_period_seconds == 0
    assert clock.state.time.elapsed_seconds == 20


def test_reset_exact_initial_snapshot_including_history_and_assignments():
    original = active_clock().tick(10)
    clock = SimulationClock(original, tick_seconds=5)
    initial_snapshot = clock.state
    clock.tick()
    clock.unassign_task(task_id='T-1')
    clock.pause()
    assert clock.reset() is initial_snapshot
    assert not clock.paused
    assert clock.state.time.elapsed_seconds == 10
    assert clock.state.time.tick_seconds == 5
    assert clock.state.workers[0].current_work_period_seconds == 10
    assert clock.tick().time.elapsed_seconds == 15
    fresh = SimulationClock(initial())
    fresh.tick()
    assert fresh.reset().time.elapsed_seconds == 0


def test_identical_operation_sequences_and_json():
    def run():
        clock = active_clock()
        clock.tick(2)
        clock.pause()
        clock.tick()
        clock.resume()
        clock.tick(3)
        return to_json(clock.state)
    assert run() == run()
    assert json.loads(run())['workers'][0]['current_work_period_seconds'] == 5


@pytest.mark.parametrize('bad', [0, -1, True, 1.5, '10'])
def test_bad_delta_rejected_even_paused_without_mutation(bad):
    clock = active_clock()
    before = clock.state
    for paused in (False, True):
        if paused:
            clock.pause()
        with pytest.raises(ValueError, match='delta_seconds'):
            clock.tick(bad)
        assert clock.state is before
    with pytest.raises(ValueError, match='tick_seconds'):
        SimulationClock(initial(), tick_seconds=bad)


@pytest.mark.parametrize('operation', [
    lambda c: c.start_task(task_id='UNKNOWN'),
    lambda c: c.start_task(task_id='T-1'),
    lambda c: c.start_rest(worker_id='W-1', zone_id='WORK'),
    lambda c: c.start_rest(worker_id='UNKNOWN', zone_id='REST'),
    lambda c: c.end_rest(worker_id='W-1'),
])
def test_bad_transitions_atomic(operation):
    clock = SimulationClock(initial())
    before = clock.state
    with pytest.raises(ValueError):
        operation(clock)
    assert clock.state is before


def test_working_cannot_enter_rest_without_unassignment():
    clock = active_clock()
    before = clock.state
    with pytest.raises(ValueError):
        clock.start_rest(worker_id='W-1', zone_id='REST')
    assert clock.state is before


@pytest.mark.parametrize('changes', [
    {'current_work_period_seconds': -1}, {'current_rest_period_seconds': True},
    {'current_work_period_seconds': 1}, {'current_rest_period_seconds': 1},
    {'current_work_period_seconds': 1, 'exposure_elapsed_seconds': 1},
    {'current_rest_period_seconds': 1, 'rest_elapsed_seconds': 1},
])
def test_period_validation(changes):
    with pytest.raises(ValueError):
        replace(initial().workers[0], **changes)


def test_final_tick_validation_failure_does_not_publish(monkeypatch):
    clock = active_clock()
    before = clock.state
    def reject(self):
        raise ValueError('injected state failure')
    monkeypatch.setattr(SimulationState, '__post_init__', reject)
    with pytest.raises(ValueError, match='injected'):
        clock.tick()
    assert clock.state is before
