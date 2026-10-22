import json
import random
from dataclasses import FrozenInstanceError, replace

import pytest

from heatshift_ai import (
    AvailabilityStatus, InitialWorkerStatus, SimulationState, SimulationTime,
    WorkerConfig, WorkerSimulator, WorkStatus, Zone, ZoneKind,
)


def assembled(sim):
    return SimulationState(
        workers=sim.list_workers(), random_seed=sim.seed,
        zones=tuple(Zone(zone_id=z, kind=ZoneKind.WORK) for z in sim.config.work_zone_ids)
        + (Zone(zone_id=sim.config.rest_zone_id, kind=ZoneKind.REST),),
    )


def test_default_count_identity_and_variation():
    sim = WorkerSimulator()
    workers = sim.list_workers()
    assert len(workers) == 10
    assert [w.worker_id for w in workers] == [f'W-{i:02d}' for i in range(1, 11)]
    assert len({w.display_name for w in workers}) == 10
    assert all(w.display_name.startswith('Fictional Worker ') for w in workers)
    for attr in ('qualifications', 'acclimatization_status', 'clothing_profile',
                 'work_status', 'availability_status'):
        assert len({getattr(w, attr) for w in workers}) > 1


def test_seed_reproducibility_identity_and_rng_isolation():
    before = random.getstate()
    first = WorkerSimulator(seed=42)
    assert random.getstate() == before
    assert first.export_json() == WorkerSimulator(seed=42).export_json()
    second = WorkerSimulator(seed=43)
    assert first.list_workers() != second.list_workers()
    assert [(w.worker_id, w.display_name) for w in first.list_workers()] == [
        (w.worker_id, w.display_name) for w in second.list_workers()]


@pytest.mark.parametrize('seed', [0, 1, 2, 42, 43, 100, -1])
def test_consistent_status_zones_and_state(seed):
    sim = WorkerSimulator(seed=seed)
    assert assembled(sim).workers == sim.list_workers()
    for worker in sim.list_workers():
        assert worker.current_task_id is None
        assert worker.exposure_elapsed_seconds == worker.rest_elapsed_seconds == 0
        assert worker.work_status != WorkStatus.WORKING
        if worker.work_status == WorkStatus.RESTING:
            assert worker.availability_status == AvailabilityStatus.UNAVAILABLE
            assert worker.current_zone_id == sim.config.rest_zone_id
        else:
            assert worker.current_zone_id in sim.config.work_zone_ids


def test_retrieval_and_time_changes_preserve_identity_and_qualifications():
    sim = WorkerSimulator()
    original = sim.list_workers()
    for worker in original:
        assert sim.get_worker(worker.worker_id) is worker
    sim.export_json()
    assert sim.list_workers() is original
    state = assembled(sim)
    for elapsed in (10, 20, 30):
        state = replace(state, time=SimulationTime(elapsed_seconds=elapsed))
        assert state.workers is original
    with pytest.raises(FrozenInstanceError):
        original[0].qualifications = frozenset()
    with pytest.raises(FrozenInstanceError):
        original[0].worker_id = 'W-99'
    with pytest.raises(KeyError, match='unknown worker_id'):
        sim.get_worker('W-99')
    with pytest.raises(ValueError, match='worker_id'):
        sim.get_worker('')


def test_json_is_explicitly_simulated_and_complete():
    sim = WorkerSimulator(seed=3)
    data = json.loads(sim.export_json())
    assert data['data_origin'] == 'simulated'
    assert data['seed'] == 3
    assert data['config']['count'] == 10
    assert len(data['workers']) == 10
    assert data['workers'][0]['current_task_id'] is None
    assert isinstance(data['workers'][0]['qualifications'], list)
    assert not {'heart_rate', 'medical_condition', 'wbgt'} & data['workers'][0].keys()


def test_explicit_config_controls_population():
    config = WorkerConfig(
        count=3, work_zone_ids=('CUSTOM_WORK',), rest_zone_id='CUSTOM_REST',
        qualification_profiles=(frozenset({'custom_skill'}),),
        acclimatization_statuses=('unknown',), clothing_profiles=('custom_clothing',),
        initial_statuses=(InitialWorkerStatus(work_status='idle', availability_status='available'),),
    )
    sim = WorkerSimulator(config=config, seed=11)
    assert len(assembled(sim).workers) == 3
    for worker in sim.list_workers():
        assert worker.current_zone_id == 'CUSTOM_WORK'
        assert worker.qualifications == frozenset({'custom_skill'})
        assert worker.clothing_profile == 'custom_clothing'
        assert worker.acclimatization_status == 'unknown'
    assert sim.export_json() == WorkerSimulator(config=config, seed=11).export_json()


@pytest.mark.parametrize('changes', [
    {'count': 0}, {'count': -1}, {'count': True}, {'count': 1.5},
    {'work_zone_ids': ()}, {'work_zone_ids': ['A']}, {'work_zone_ids': ('A', 'A')},
    {'work_zone_ids': ('REST_ZONE',)}, {'work_zone_ids': ('bad zone',)}, {'rest_zone_id': ''},
    {'qualification_profiles': ()}, {'qualification_profiles': ('skill',)},
    {'qualification_profiles': (frozenset({1}),)},
    {'acclimatization_statuses': ()}, {'acclimatization_statuses': ('invalid',)},
    {'clothing_profiles': ()}, {'clothing_profiles': ('',)},
    {'initial_statuses': ()}, {'initial_statuses': ('idle',)},
])
def test_invalid_configuration(changes):
    with pytest.raises(ValueError):
        WorkerConfig(**changes)


@pytest.mark.parametrize('work, availability', [
    ('working', 'available'), ('working', 'unavailable'), ('resting', 'available'),
    ('invalid', 'available'), ('idle', 'invalid'),
])
def test_invalid_initial_status(work, availability):
    with pytest.raises(ValueError):
        InitialWorkerStatus(work_status=work, availability_status=availability)


@pytest.mark.parametrize('seed', [True, 1.5, '42', None])
def test_invalid_seed(seed):
    with pytest.raises(ValueError, match='seed'):
        WorkerSimulator(seed=seed)


def test_invalid_config_type():
    with pytest.raises(ValueError, match='config'):
        WorkerSimulator(config={})
