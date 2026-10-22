import json
from dataclasses import FrozenInstanceError, replace
import pytest
from heatshift_ai import (
    Assignment, EnvironmentObservation, MeasurementSource, SimulationState,
    SimulationTime, Task, TaskStatus, Worker, WorkloadCategory, WorkStatus, Zone,
    ZoneKind, to_json, to_json_value,
)


def worker(**changes):
    return Worker(**({'worker_id': 'W_1', 'display_name': 'Fictional Worker',
                     'current_zone_id': 'ZONE_A'} | changes))


def task(**changes):
    return Task(**({'task_id': 'T_1', 'task_name': 'Test fixture task',
                   'workload_category': WorkloadCategory.LIGHT,
                   'allowed_zone_ids': frozenset({'ZONE_A'})} | changes))


def state(**changes):
    return SimulationState(**({'zones': (Zone(zone_id='ZONE_A', kind=ZoneKind.WORK),
                                         Zone(zone_id='REST_ZONE', kind=ZoneKind.REST)),
                               'workers': (worker(),), 'tasks': (task(),)} | changes))


def active_state(**changes):
    return state(**({'workers': (worker(current_task_id='T_1', work_status=WorkStatus.WORKING),),
                     'tasks': (task(assigned_worker_id='W_1', task_status=TaskStatus.IN_PROGRESS),),
                     'assignments': (Assignment(worker_id='W_1', task_id='T_1', zone_id='ZONE_A'),)} | changes))


def test_valid_models_and_optional_json():
    data = json.loads(to_json(state()))
    assert data['data_origin'] == 'simulated'
    assert data['time'] == {'elapsed_seconds': 0, 'tick_seconds': 10}
    assert data['workers'][0]['current_task_id'] is None
    assert data['tasks'][0]['assigned_worker_id'] is None
    assert data['tasks'][0]['estimated_metabolic_rate_watts'] is None
    assert data['tasks'][0]['workload_category'] == 'light'
    assert json.loads(to_json(task(estimated_metabolic_rate_watts=180)))['estimated_metabolic_rate_watts'] == 180
    assert to_json(state()) == to_json(state())
    assert to_json_value(worker(qualifications=frozenset({'z', 'a'})))['qualifications'] == ['a', 'z']


@pytest.mark.parametrize('bad', ['', ' ', 'bad id', '1worker', None, 1, True])
def test_invalid_ids(bad):
    for build in (lambda: worker(worker_id=bad), lambda: worker(current_task_id=bad) if bad is not None else worker(current_zone_id=bad),
                  lambda: task(task_id=bad), lambda: Zone(zone_id=bad, kind=ZoneKind.WORK),
                  lambda: Assignment(worker_id=bad, task_id='T', zone_id='Z')):
        with pytest.raises(ValueError, match='ID'):
            build()


@pytest.mark.parametrize('field', ['work_status', 'availability_status', 'acclimatization_status'])
@pytest.mark.parametrize('bad', ['invalid', '', None, 7])
def test_invalid_worker_status(field, bad):
    with pytest.raises(ValueError, match=field):
        worker(**{field: bad})


@pytest.mark.parametrize('field', ['task_status', 'workload_category'])
@pytest.mark.parametrize('bad', ['invalid', '', None, 7])
def test_invalid_task_enum(field, bad):
    with pytest.raises(ValueError, match=field):
        task(**{field: bad})


@pytest.mark.parametrize('bad', [-1, 1.5, True, '10', None])
def test_invalid_duration(bad):
    for build in (lambda: worker(exposure_elapsed_seconds=bad), lambda: worker(rest_elapsed_seconds=bad),
                  lambda: SimulationTime(elapsed_seconds=bad), lambda: SimulationTime(tick_seconds=bad),
                  lambda: Assignment(worker_id='W', task_id='T', zone_id='Z', started_at_elapsed_seconds=bad)):
        with pytest.raises(ValueError, match='seconds'):
            build()


def test_tick_zero_rejected_and_configurable_time():
    with pytest.raises(ValueError, match='positive'):
        SimulationTime(tick_seconds=0)
    assert SimulationTime(elapsed_seconds=7, tick_seconds=3).elapsed_seconds == 7


@pytest.mark.parametrize('bad', [-1, 0, float('inf'), float('nan'), True, '100'])
def test_invalid_metabolic_rate(bad):
    with pytest.raises(ValueError, match='estimated_metabolic_rate_watts'):
        task(estimated_metabolic_rate_watts=bad)


@pytest.mark.parametrize('build', [
    lambda: worker(display_name=' '), lambda: worker(clothing_profile=''),
    lambda: worker(qualifications='rigging'), lambda: worker(qualifications=frozenset({1})),
    lambda: task(required_qualifications=frozenset({''})), lambda: task(allowed_zone_ids=frozenset()),
    lambda: task(allowed_zone_ids=frozenset({'bad zone'})), lambda: task(assigned_worker_id=''),
    lambda: Zone(zone_id='Z', kind='invalid'),
])
def test_other_model_validation(build):
    with pytest.raises(ValueError):
        build()


def test_valid_enum_strings_normalized():
    assert worker(work_status='idle').work_status is WorkStatus.IDLE
    assert task(workload_category='heavy').workload_category is WorkloadCategory.HEAVY


def test_invalid_zone_references():
    with pytest.raises(ValueError, match='unknown zone'):
        state(workers=(worker(current_zone_id='MISSING'),))
    for zone in ('MISSING', 'REST_ZONE'):
        with pytest.raises(ValueError, match='work zone'):
            state(tasks=(task(allowed_zone_ids=frozenset({zone})),))


def test_valid_assignment_and_rest_states():
    assert json.loads(to_json(active_state()))['workers'][0]['current_task_id'] == 'T_1'
    active_state(workers=(worker(current_task_id='T_1'),),
                 tasks=(task(assigned_worker_id='W_1', task_status=TaskStatus.ASSIGNED),))
    state(workers=(worker(current_zone_id='REST_ZONE', work_status=WorkStatus.RESTING,
                          rest_elapsed_seconds=10),), time=SimulationTime(elapsed_seconds=10))
    state(workers=(worker(availability_status='unavailable'),))


@pytest.mark.parametrize('changes, message', [
    ({'workers': (worker(current_task_id='T_1'),)}, 'current_task_id'),
    ({'workers': (worker(work_status=WorkStatus.WORKING),)}, 'working requires'),
    ({'workers': (worker(work_status=WorkStatus.RESTING),)}, 'rest zone'),
    ({'workers': (worker(exposure_elapsed_seconds=1),)}, 'exceeds'),
    ({'workers': (worker(rest_elapsed_seconds=1),)}, 'exceeds'),
    ({'tasks': (task(task_status=TaskStatus.IN_PROGRESS),)}, 'inconsistent'),
    ({'tasks': (task(assigned_worker_id='W_1'),)}, 'inconsistent'),
    ({'workers': (worker(), worker())}, 'duplicate'),
    ({'tasks': (task(), task())}, 'duplicate'),
    ({'workers': []}, 'tuple'),
    ({'time': 10}, 'SimulationTime'),
    ({'random_seed': True}, 'integer'),
])
def test_invalid_state(changes, message):
    with pytest.raises(ValueError, match=message):
        state(**changes)


@pytest.mark.parametrize('changes, message', [
    ({'tasks': (task(assigned_worker_id='W_2', task_status=TaskStatus.IN_PROGRESS),)}, 'assignment'),
    ({'tasks': (task(assigned_worker_id='W_1', task_status=TaskStatus.IN_PROGRESS,
                     required_qualifications=frozenset({'permit'})),)}, 'qualifications'),
    ({'workers': (worker(current_task_id='T_1', work_status=WorkStatus.WORKING,
                         availability_status='unavailable'),)}, 'available'),
    ({'workers': (worker(current_task_id='T_1'),)}, 'work_status'),
    ({'assignments': (Assignment(worker_id='W_1', task_id='T_1', zone_id='MISSING'),)}, 'unknown'),
    ({'assignments': (Assignment(worker_id='W_1', task_id='T_1', zone_id='REST_ZONE'),)}, 'zone'),
    ({'assignments': (Assignment(worker_id='W_1', task_id='T_1', zone_id='ZONE_A', started_at_elapsed_seconds=1),)}, 'future'),
])
def test_invalid_assignment(changes, message):
    with pytest.raises(ValueError, match=message):
        active_state(**changes)


def test_missing_entity_and_duplicate_assignment():
    with pytest.raises(ValueError, match='unknown'):
        SimulationState(assignments=(Assignment(worker_id='W', task_id='T', zone_id='Z'),))
    assignment = Assignment(worker_id='W_1', task_id='T_1', zone_id='ZONE_A')
    with pytest.raises(ValueError, match='duplicate'):
        active_state(assignments=(assignment, assignment))
    with pytest.raises(ValueError, match='duplicate task_id'):
        active_state(assignments=(assignment, replace(assignment, worker_id='W_2')))


def test_immutable_state_and_seed():
    value = state(random_seed=42)
    assert to_json_value(value)['random_seed'] == 42
    with pytest.raises(FrozenInstanceError):
        value.workers[0].current_zone_id = 'MISSING'
    with pytest.raises(ValueError, match='unknown zone'):
        replace(value, workers=(replace(value.workers[0], current_zone_id='MISSING'),))


def test_environment_boundary_serialization():
    for source in MeasurementSource:
        observation = EnvironmentObservation(zone_id='ZONE_A', elapsed_seconds=10,
                                             wbgt_celsius=None, source=source)
        assert json.loads(to_json(observation))['source'] == source.value
        assert json.loads(to_json(observation))['wbgt_celsius'] is None
    observation = EnvironmentObservation(zone_id='ZONE_A', elapsed_seconds=10,
                                         wbgt_celsius=26.5, source=MeasurementSource.SIMULATED)
    assert to_json_value(observation)['wbgt_celsius'] == 26.5


@pytest.mark.parametrize('changes', [{'zone_id': ''}, {'elapsed_seconds': -1},
                                    {'source': 'unknown'}, {'wbgt_celsius': float('nan')}])
def test_invalid_environment_observation(changes):
    with pytest.raises(ValueError):
        EnvironmentObservation(**({'zone_id': 'ZONE_A', 'elapsed_seconds': 0,
                                   'wbgt_celsius': None, 'source': MeasurementSource.SIMULATED} | changes))


def test_no_generated_data():
    value = SimulationState()
    assert value.workers == value.tasks == value.assignments == value.zones == ()
