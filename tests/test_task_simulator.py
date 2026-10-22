import json
from dataclasses import FrozenInstanceError, replace

import pytest

from heatshift_ai import (
    SimulationState, TaskConfig, TaskDefinition, TaskSimulator, TaskStatus,
    WorkerSimulator, WorkloadCategory, Zone, ZoneKind, default_task_definitions, to_json,
)

NAMES = ('Site Inspection', 'Material Handling', 'Equipment Operation',
         'Reinforcement Installation', 'Concrete Placement', 'Surveying')


def test_exact_six_unique_deterministic_definitions_and_states():
    sim = TaskSimulator()
    assert len(sim.list_definitions()) == len(sim.list_tasks()) == 6
    assert tuple(d.task_name for d in sim.list_definitions()) == NAMES
    assert [d.task_id for d in sim.list_definitions()] == [f'T-{i:02d}' for i in range(1, 7)]
    assert len({t.task_id for t in sim.list_tasks()}) == 6
    assert len({d.workload_category for d in sim.list_definitions()}) > 1
    assert sim.export_json() == TaskSimulator().export_json()


@pytest.mark.parametrize('definition', default_task_definitions(), ids=lambda d: d.task_id)
def test_each_definition_valid_references_json_and_unassigned_state(definition):
    config = TaskConfig()
    zones = {z.zone_id: z for z in config.zones}
    assert isinstance(definition.workload_category, WorkloadCategory)
    assert definition.required_qualifications <= config.known_qualifications
    assert definition.required_qualifications
    assert definition.allowed_zone_ids
    assert all(zones[z].kind == ZoneKind.WORK for z in definition.allowed_zone_ids)
    task = definition.new_task()
    assert task.task_status is TaskStatus.PENDING
    assert task.assigned_worker_id is None
    assert task.estimated_metabolic_rate_watts is None
    assert json.loads(to_json(definition))['task_id'] == definition.task_id
    assert json.loads(to_json(task))['assigned_worker_id'] is None


def test_combined_state_and_qualification_gaps_are_explicit():
    sim = TaskSimulator()
    workers = WorkerSimulator().list_workers()
    state = SimulationState(zones=sim.config.zones, workers=workers, tasks=sim.list_tasks())
    assert state.assignments == ()
    # Specialized tasks remain valid definitions even when no worker is qualified.
    unavailable_skills = {'reinforcement_installation', 'concrete_placement', 'surveying'}
    assert not unavailable_skills & set().union(*(w.qualifications for w in workers))


def test_lookup_export_and_reusable_definition():
    sim = TaskSimulator()
    definition = sim.get_definition('T-01')
    assert definition is sim.list_definitions()[0]
    assert sim.get_task('T-01') is sim.list_tasks()[0]
    copy = definition.new_task(task_id='T-INSPECTION-SECOND')
    assert copy.task_id != definition.task_id
    assert copy.task_name == definition.task_name
    completed = replace(copy, task_status=TaskStatus.COMPLETED)
    assert completed.task_status is TaskStatus.COMPLETED
    assert sim.get_task('T-01').task_status is TaskStatus.PENDING
    assert not hasattr(definition, 'assigned_worker_id')
    with pytest.raises(FrozenInstanceError):
        definition.task_name = 'Changed'
    for lookup in (sim.get_task, sim.get_definition):
        with pytest.raises(KeyError, match='unknown task_id'):
            lookup('T-99')
        with pytest.raises(ValueError, match='task_id'):
            lookup('')
    data = json.loads(sim.export_json())
    assert data['data_origin'] == 'simulated'
    assert len(data['config']['definitions']) == len(data['tasks']) == 6
    assert all(t['task_status'] == 'pending' and t['assigned_worker_id'] is None for t in data['tasks'])


@pytest.mark.parametrize('changes', [
    {'task_id': ''}, {'task_name': ' '}, {'workload_category': 'invalid'},
    {'estimated_metabolic_rate_watts': -1}, {'estimated_metabolic_rate_watts': float('nan')},
    {'estimated_metabolic_rate_watts': True}, {'required_qualifications': frozenset()},
    {'required_qualifications': frozenset({''})}, {'required_qualifications': ['inspection']},
    {'allowed_zone_ids': frozenset()}, {'allowed_zone_ids': frozenset({'bad zone'})},
])
def test_invalid_single_definition(changes):
    with pytest.raises(ValueError):
        replace(default_task_definitions()[0], **changes)


@pytest.mark.parametrize('field,value,message', [
    ('required_qualifications', frozenset({'unknown_skill'}), 'T-01: unknown qualifications'),
    ('allowed_zone_ids', frozenset({'UNKNOWN_ZONE'}), 'T-01: allowed zone'),
    ('allowed_zone_ids', frozenset({'REST_ZONE'}), 'T-01: allowed zone'),
])
def test_invalid_single_definition_references(field, value, message):
    definitions = default_task_definitions()
    bad = replace(definitions[0], **{field: value})
    with pytest.raises(ValueError, match=message):
        TaskConfig(definitions=(bad,) + definitions[1:])


@pytest.mark.parametrize('changes', [
    {'definitions': ()}, {'definitions': default_task_definitions()[:5]},
    {'definitions': list(default_task_definitions())}, {'definitions': (None,) * 6},
    {'definitions': (default_task_definitions()[0],) * 6},
    {'zones': ()}, {'zones': ('ZONE_A',)},
    {'zones': (Zone(zone_id='ZONE_A', kind=ZoneKind.WORK),) * 2},
    {'known_qualifications': frozenset()}, {'known_qualifications': {'inspection'}},
])
def test_invalid_config(changes):
    with pytest.raises(ValueError):
        TaskConfig(**changes)


def test_explicit_custom_config_and_optional_rate():
    definitions = tuple(replace(d, allowed_zone_ids=frozenset({'CUSTOM_ZONE'}),
                                required_qualifications=frozenset({'custom_skill'}),
                                workload_category='moderate', estimated_metabolic_rate_watts=200)
                        for d in default_task_definitions())
    sim = TaskSimulator(config=TaskConfig(
        definitions=definitions, zones=(Zone(zone_id='CUSTOM_ZONE', kind=ZoneKind.WORK),),
        known_qualifications=frozenset({'custom_skill'})))
    SimulationState(zones=sim.config.zones, tasks=sim.list_tasks())
    assert all(t.estimated_metabolic_rate_watts == 200 for t in sim.list_tasks())
    assert json.loads(sim.export_json())['tasks'][0]['estimated_metabolic_rate_watts'] == 200


def test_invalid_simulator_config():
    with pytest.raises(ValueError, match='config'):
        TaskSimulator(config={})
