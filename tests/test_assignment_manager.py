import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from heatshift_ai import (AssignmentManager, AssignmentRequest, SimulationState, SimulationTime,
                         Task, TaskStatus, Worker, WorkStatus, Zone, ZoneKind, to_json)


def base(**changes):
    return SimulationState(**({
        'zones': (Zone(zone_id='A', kind=ZoneKind.WORK), Zone(zone_id='B', kind=ZoneKind.WORK),
                  Zone(zone_id='REST', kind=ZoneKind.REST)),
        'workers': tuple(Worker(worker_id=f'W-{i}', display_name=f'Fictional {i}', current_zone_id='A',
                                qualifications=frozenset({'skill'})) for i in (1, 2)),
        'tasks': tuple(Task(task_id=f'T-{i}', task_name=f'Fixture {i}', workload_category='moderate',
                           required_qualifications=frozenset({'skill'}), allowed_zone_ids=frozenset({'A', 'B'}))
                       for i in (1, 2)),
        'time': SimulationTime(elapsed_seconds=20),
    } | changes))


def test_assign_and_unassign_atomic_references_and_preserved_fields(caplog):
    caplog.set_level(logging.INFO)
    original = base()
    manager = AssignmentManager(original)
    assigned = manager.assign_task(worker_id='W-1', task_id='T-1', zone_id='B')
    assert manager.state is assigned
    assert original.assignments == () and original.workers[0].current_task_id is None
    worker, task = assigned.workers[0], assigned.tasks[0]
    assert (worker.current_task_id, task.assigned_worker_id, worker.current_zone_id) == ('T-1', 'W-1', 'B')
    assert task.task_status is TaskStatus.ASSIGNED and worker.work_status is WorkStatus.IDLE
    assert assigned.assignments[0].started_at_elapsed_seconds == 20
    assert assigned.workers[1] is original.workers[1]
    assert assigned.tasks[1] is original.tasks[1]
    assert replace(worker, current_zone_id='A', current_task_id=None) == original.workers[0]
    released = manager.unassign_task(task_id='T-1')
    assert manager.state is released
    assert released.assignments == ()
    assert released.workers[0].current_task_id is None
    assert released.workers[0].current_zone_id == 'B'
    assert released.tasks[0].assigned_worker_id is None
    assert released.tasks[0].task_status is TaskStatus.PENDING
    assert released.time == original.time
    assert 'assign_task committed' in caplog.text and 'unassign_task committed' in caplog.text


@pytest.mark.parametrize('changes,match', [
    ({'qualifications': frozenset()}, 'qualifications'),
    ({'availability_status': 'unavailable'}, 'unavailable'),
    ({'work_status': 'resting', 'current_zone_id': 'REST'}, 'resting'),
])
def test_worker_rejections_leave_identical_state(changes, match, caplog):
    state = base()
    state = replace(state, workers=(replace(state.workers[0], **changes), state.workers[1]))
    manager = AssignmentManager(state)
    before = manager.state
    serialized = to_json(before)
    with pytest.raises(ValueError, match=match):
        manager.assign_task(worker_id='W-1', task_id='T-1')
    assert manager.state is before and to_json(manager.state) == serialized
    assert 'assign_task rejected' in caplog.text


@pytest.mark.parametrize('kwargs,match', [
    ({'worker_id': 'UNKNOWN', 'task_id': 'T-1'}, 'unknown worker'),
    ({'worker_id': 'W-1', 'task_id': 'UNKNOWN'}, 'unknown task'),
    ({'worker_id': '', 'task_id': 'T-1'}, 'worker_id'),
    ({'worker_id': 'W-1', 'task_id': ''}, 'task_id'),
    ({'worker_id': 'W-1', 'task_id': 'T-1', 'zone_id': 'UNKNOWN'}, 'zone'),
    ({'worker_id': 'W-1', 'task_id': 'T-1', 'zone_id': 'REST'}, 'zone'),
    ({'worker_id': 'W-1', 'task_id': 'T-1', 'zone_id': ''}, 'zone_id'),
])
def test_bad_references_unchanged(kwargs, match):
    manager = AssignmentManager(base())
    before = manager.state
    with pytest.raises(ValueError, match=match):
        manager.assign_task(**kwargs)
    assert manager.state is before


def test_zone_disallowed_and_default_zone_not_silently_changed():
    original = base()
    state = replace(original, tasks=(replace(original.tasks[0], allowed_zone_ids=frozenset({'B'})), original.tasks[1]))
    manager = AssignmentManager(state)
    before = manager.state
    with pytest.raises(ValueError, match='zone A'):
        manager.assign_task(worker_id='W-1', task_id='T-1')
    assert manager.state is before
    manager.assign_task(worker_id='W-1', task_id='T-1', zone_id='B')


@pytest.mark.parametrize('worker,task', [('W-1', 'T-1'), ('W-1', 'T-2'), ('W-2', 'T-1')])
def test_duplicates_rejected(worker, task):
    manager = AssignmentManager(base())
    before = manager.assign_task(worker_id='W-1', task_id='T-1')
    with pytest.raises(ValueError, match='already'):
        manager.assign_task(worker_id=worker, task_id=task)
    assert manager.state is before


@pytest.mark.parametrize('status', [TaskStatus.COMPLETED, TaskStatus.CANCELLED])
def test_terminal_task_rejected(status):
    original = base()
    manager = AssignmentManager(replace(original, tasks=(replace(original.tasks[0], task_status=status), original.tasks[1])))
    before = manager.state
    with pytest.raises(ValueError, match='pending'):
        manager.assign_task(worker_id='W-1', task_id='T-1')
    assert manager.state is before


@pytest.mark.parametrize('task_id', ['T-1', 'UNKNOWN', ''])
def test_unassign_rejection_unchanged(task_id, caplog):
    manager = AssignmentManager(base())
    before = manager.state
    with pytest.raises(ValueError):
        manager.unassign_task(task_id=task_id)
    assert manager.state is before
    assert 'unassign_task rejected' in caplog.text


def test_initial_configuration_all_or_nothing(caplog):
    caplog.set_level(logging.INFO)
    original = base()
    requests = (AssignmentRequest(worker_id='W-1', task_id='T-1'),
                AssignmentRequest(worker_id='W-2', task_id='T-2', zone_id='B'))
    manager = AssignmentManager(original, initial_assignments=requests)
    assert len(manager.state.assignments) == 2
    assert original.assignments == ()
    assert to_json(manager.state) == to_json(AssignmentManager(original, initial_assignments=requests).state)
    caplog.clear()
    invalid = (requests[0], AssignmentRequest(worker_id='W-2', task_id='T-1'))
    with pytest.raises(ValueError, match='already'):
        AssignmentManager(original, initial_assignments=invalid)
    assert original.assignments == () and all(w.current_task_id is None for w in original.workers)
    assert 'initial assignments rejected' in caplog.text
    assert 'committed' not in caplog.text


def test_unassign_in_progress_preserves_counters_and_allows_explicit_reassignment():
    manager = AssignmentManager(base())
    assigned = manager.assign_task(worker_id='W-1', task_id='T-1')
    running = replace(assigned,
        workers=(replace(assigned.workers[0], work_status='working', exposure_elapsed_seconds=10), assigned.workers[1]),
        tasks=(replace(assigned.tasks[0], task_status='in_progress'), assigned.tasks[1]))
    manager = AssignmentManager(running)
    released = manager.unassign_task(task_id='T-1')
    assert released.workers[0].exposure_elapsed_seconds == 10
    assert released.workers[0].work_status is WorkStatus.IDLE
    manager.assign_task(worker_id='W-2', task_id='T-1')
    assert manager.state.tasks[0].assigned_worker_id == 'W-2'


def test_final_validation_failure_never_publishes_candidate(monkeypatch, caplog):
    manager = AssignmentManager(base())
    before = manager.state
    def fail_validation(self):
        raise ValueError('injected final validation failure')
    monkeypatch.setattr(SimulationState, '__post_init__', fail_validation)
    with pytest.raises(ValueError, match='final validation'):
        manager.assign_task(worker_id='W-1', task_id='T-1')
    assert manager.state is before
    assert 'assign_task rejected' in caplog.text


def test_concurrent_competition_cannot_double_assign():
    manager = AssignmentManager(base())
    def attempt(worker_id):
        try:
            manager.assign_task(worker_id=worker_id, task_id='T-1')
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ('W-1', 'W-2')))
    assert sorted(results) == [False, True]
    assert len(manager.state.assignments) == 1
    replace(manager.state)  # Verify all reciprocal invariants.


@pytest.mark.parametrize('kwargs', [{'state': None}, {'state': base(), 'initial_assignments': []},
                                    {'state': base(), 'initial_assignments': ('bad',)}])
def test_invalid_manager_config(kwargs):
    with pytest.raises(ValueError):
        AssignmentManager(**kwargs)
