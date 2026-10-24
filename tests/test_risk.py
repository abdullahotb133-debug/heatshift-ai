"""G2 reference arithmetic, conservative failure paths and Component A compatibility."""
from copy import deepcopy
from decimal import Decimal, localcontext
import json
from pathlib import Path

import pytest

from heatshift_ai.api_contracts import CommandRequest, SimulationSnapshot, simulation_timestamp
from heatshift_ai.api_service import SimulationService
from heatshift_ai.risk import AssessmentBasis, Outcome, assess_worker, reference_limit_celsius


@pytest.fixture(scope="module")
def complete():
    # Explicit synthetic constant-environment reference case; no fixture claims to
    # represent measured work, medical clearance or the unmodified demo population.
    original = SimulationService(instance_id="g2-reference").snapshot().model_dump(mode="json")
    worker = next(w for w in original['workers'] if w['work_status'] == 'working')
    worker['acclimatization_status'] = 'acclimatized'
    task = next(t for t in original['tasks'] if t['task_id'] == worker['current_task_id'])
    task['estimated_metabolic_rate_watts'] = 200.0
    zone = next(z for z in original['zones'] if z['zone_id'] == worker['current_zone_id'])
    obs = zone['environment']
    obs['wbgt_celsius'] = 28.0
    for c in obs['conditions']:
        if c['name'] in ('air_temperature_c', 'globe_temperature_c', 'natural_wet_bulb_c'):
            c['value'] = 28.0
    samples = []
    for elapsed in range(0, 3601, 10):
        row = deepcopy(original)
        row['elapsed_seconds'] = elapsed
        row['state_version'] = elapsed // 10
        row['simulated_at'] = simulation_timestamp(elapsed).isoformat()
        for w in row['workers']:
            if w['work_status'] == 'working':
                w['exposure_elapsed_seconds'] = elapsed
                w['current_work_period_seconds'] = elapsed
        for z in row['zones']:
            o = z['environment']
            o['elapsed_seconds'] = o['observed_at_seconds'] = elapsed
            o['observed_at'] = row['simulated_at']
            o['source_metadata']['observed_at_seconds'] = str(elapsed)
        samples.append(row)
    basis = AssessmentBasis(worker_id=worker['worker_id'], task_id=task['task_id'],
        clothing_profile=worker['clothing_profile'], clothing_ensemble='conventional_one_layer',
        clothing_basis='Explicit reference fixture: conventional one-layer woven work clothing.',
        metabolic_rate_basis='Explicit 200 W whole-body reference fixture, not inferred from task label.',
        population_basis='Synthetic NIOSH reference person, healthy and fit for the task; scenario assumption.',
        reference_person_applicable=True)
    return samples, worker['worker_id'], basis


def run(case):
    samples, worker, basis = case
    return assess_worker(samples[-1], worker, history=samples[:-1], basis=basis)


def edited(complete):
    return deepcopy(complete)


def target(row, worker):
    return next(w for w in row['workers'] if w['worker_id'] == worker)


def observation(row, worker):
    return next(z['environment'] for z in row['zones'] if z['zone_id'] == target(row, worker)['current_zone_id'])


def set_temperature(row, worker, value):
    o = observation(row, worker)
    o['wbgt_celsius'] = value
    for c in o['conditions']:
        if c['name'] in ('air_temperature_c', 'globe_temperature_c', 'natural_wet_bulb_c'):
            c['value'] = value


def test_complete_deterministic_json_no_mutation(complete):
    before = json.dumps(complete[0], sort_keys=True)
    first, second = run(complete), run(complete)
    assert first == second
    assert first.outcome == Outcome.WITHIN_APPLICABLE_LIMIT
    assert first.wbgt_twa_celsius == 28.0
    assert first.reference_limit_kind == 'REL'
    assert first.reference_limit_celsius == pytest.approx(30.23815504986422)
    assert first.sample_count == 361 and first.simulation_based
    assert first.assessment_timestamp == simulation_timestamp(3600)
    assert json.loads(first.model_dump_json())['worker_id'] == complete[1]
    assert before == json.dumps(complete[0], sort_keys=True)


@pytest.mark.parametrize('watts', [116, 200, 300, 348.9, 400, 580])
@pytest.mark.parametrize('status,a,b', [('acclimatized', '56.7', '11.5'), ('not_acclimatized', '59.9', '14.1')])
def test_niosh_equations_independent_decimal_reference(watts, status, a, b):
    # Independent high-precision natural-log calculation, not production log10.
    with localcontext() as ctx:
        ctx.prec = 50
        reference = Decimal(a) - Decimal(b) * Decimal(str(watts)).ln() / Decimal(10).ln()
    assert reference_limit_celsius(watts, status) == pytest.approx(float(reference), abs=1e-12)


@pytest.mark.parametrize('watts', [0, 115.9, 580.1, float('nan'), float('inf'), True, '200'])
def test_no_equation_extrapolation(watts):
    with pytest.raises(ValueError): reference_limit_celsius(watts, 'acclimatized')


@pytest.mark.parametrize('temperature,outcome', [(30.23815504986422, Outcome.WITHIN_APPLICABLE_LIMIT),
                                               (30.23815514986422, Outcome.EXCEEDS_APPLICABLE_LIMIT),
                                               (30.23815494986422, Outcome.WITHIN_APPLICABLE_LIMIT)])
def test_unrounded_limit_boundary(complete, temperature, outcome):
    samples, worker, basis = edited(complete)
    for row in samples: set_temperature(row, worker, temperature)
    assert run((samples, worker, basis)).outcome == outcome


def test_time_weighted_linear_reference(complete):
    samples, worker, basis = edited(complete)
    for row in samples: set_temperature(row, worker, 26.0 + row['elapsed_seconds'] / 900)
    result = run((samples, worker, basis))
    # Integral of 26 + t/900 over 0..3600 divided by 3600 is exactly 28.
    assert result.wbgt_twa_celsius == pytest.approx(28.0)


@pytest.mark.parametrize('ensemble,adjustment,outcome', [('conventional_one_layer', 0, Outcome.WITHIN_APPLICABLE_LIMIT),
    ('cloth_coveralls', 0, Outcome.WITHIN_APPLICABLE_LIMIT), ('double_layer_cloth', 3, Outcome.EXCEEDS_APPLICABLE_LIMIT)])
def test_clothing_table_3_2_verified_subset(complete, ensemble, adjustment, outcome):
    samples, worker, basis = complete
    result = run((samples, worker, basis.model_copy(update={'clothing_ensemble': ensemble})))
    assert result.clothing_adjustment_celsius == adjustment
    assert result.effective_wbgt_twa_celsius == 28 + adjustment
    assert result.outcome == outcome


@pytest.mark.parametrize('status,outcome,kind', [('not_acclimatized', Outcome.EXCEEDS_APPLICABLE_LIMIT, 'RAL'),
    ('unknown', Outcome.INSUFFICIENT_DATA, None), ('partially_acclimatized', Outcome.NOT_ASSESSABLE, None)])
def test_acclimatization(complete, status, outcome, kind):
    samples, worker, basis = edited(complete)
    for row in samples: target(row, worker)['acclimatization_status'] = status
    result = run((samples, worker, basis))
    assert result.outcome == outcome and result.reference_limit_kind == kind


@pytest.mark.parametrize('mode', ['missing', 'stale', 'invalid'])
@pytest.mark.parametrize('index', [150, -1])
def test_bad_quality_at_any_time(complete, mode, index):
    samples, worker, basis = edited(complete)
    observation(samples[index], worker)['quality'] = mode
    assert run((samples, worker, basis)).outcome == Outcome.INSUFFICIENT_DATA


@pytest.mark.parametrize('defect', ['null_wbgt', 'null_tnw', 'missing_globe', 'unit', 'timestamp', 'solar',
    'metadata', 'calculation', 'duplicate_channel', 'nan', 'boolean_wbgt', 'future', 'string_rate', 'invalid_workload'])
def test_invalid_inputs_never_within_limit(complete, defect):
    samples, worker, basis = edited(complete)
    row = samples[-1]; o = observation(row, worker)
    if defect == 'null_wbgt': o['wbgt_celsius'] = None
    if defect == 'null_tnw': next(c for c in o['conditions'] if c['name'] == 'natural_wet_bulb_c')['value'] = None
    if defect == 'missing_globe': o['conditions'] = [c for c in o['conditions'] if c['name'] != 'globe_temperature_c']
    if defect == 'unit': o['wbgt_unit'] = 'degF'
    if defect == 'timestamp': o['observed_at_seconds'] -= 1
    if defect == 'solar': o['source_metadata'].pop('solar_exposure')
    if defect == 'metadata': o['source_metadata']['wbgt_input_source'] = 'measured'
    if defect == 'calculation': o['wbgt_celsius'] += 1
    if defect == 'duplicate_channel': o['conditions'].append(deepcopy(o['conditions'][0]))
    if defect == 'nan': o['wbgt_celsius'] = float('nan')
    if defect == 'boolean_wbgt': o['wbgt_celsius'] = True
    if defect == 'future': row['simulated_at'] = simulation_timestamp(3601).isoformat()
    if defect == 'string_rate': next(t for t in row['tasks'] if t['task_id'] == basis.task_id)['estimated_metabolic_rate_watts'] = '200'
    if defect == 'invalid_workload': next(t for t in row['tasks'] if t['task_id'] == basis.task_id)['workload_category'] = 'easy'
    assert run((samples, worker, basis)).outcome == Outcome.INSUFFICIENT_DATA


@pytest.mark.parametrize('defect', ['short', 'gap', 'order', 'instance', 'reset', 'duplicate', 'counter', 'paused', 'transition'])
def test_history_and_work_rest_semantics(complete, defect):
    samples, worker, basis = edited(complete)
    if defect == 'short': samples = samples[1:]
    if defect == 'gap': samples.pop(150)
    if defect == 'order': samples[150], samples[151] = samples[151], samples[150]
    if defect == 'instance': samples[150]['instance_id'] = 'other'
    if defect == 'reset': samples[150]['state_version'] = 0
    if defect == 'duplicate': samples.insert(150, deepcopy(samples[150]))
    if defect == 'counter': target(samples[150], worker)['current_work_period_seconds'] = 0
    if defect == 'paused': samples[150]['paused'] = True
    if defect == 'transition':
        event = deepcopy(next(e for e in samples[-1]['events'] if e['worker_id'] == worker))
        event.update(elapsed_seconds=100, occurred_at=simulation_timestamp(100).isoformat())
        samples[-1]['events'].append(event)
    assert run((samples, worker, basis)).outcome in (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE)


@pytest.mark.parametrize('update', [{'clothing_ensemble': 'unknown'}, {'reference_person_applicable': False},
                                  {'worker_id': 'another'}, {'metabolic_rate_basis': '   '}])
def test_evidence_is_explicit_and_bound(complete, update):
    samples, worker, basis = complete
    result = run((samples, worker, basis.model_copy(update=update)))
    assert result.outcome in (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE)
    assert result.reference_limit_celsius is None


def test_missing_history_and_evidence(complete):
    samples, worker, basis = complete
    assert assess_worker(samples[-1], worker, basis=basis).issues[0].code == 'missing_history'
    assert assess_worker(samples[-1], worker, history=samples[:-1]).issues[0].code == 'missing_assessment_basis'


def test_default_component_a_fails_closed_and_unchanged():
    service = SimulationService(instance_id='unchanged')
    before = service.snapshot()
    for worker in before.workers:
        result = assess_worker(before, worker.worker_id)
        assert result.outcome in (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE)
        assert result.reference_limit_celsius is None
    assert before == service.snapshot()


def test_component_a_typed_snapshot_and_id_evidence(complete):
    samples, worker, basis = complete
    assert assess_worker(SimulationSnapshot.model_validate(samples[-1]), worker,
                         history=samples[:-1], basis=basis) == run(complete)
    changed = basis.model_copy(update={'metabolic_rate_basis': 'A different documented scenario basis.'})
    assert run((samples, worker, changed)).assessment_id != run(complete).assessment_id
    assert assess_worker(samples[-1], 'W-NOT-PRESENT').issues[0].code == 'unknown_worker'


def test_saved_http_snapshot_compatibility():
    path = Path(__file__).resolve().parents[1] / 'examples/api/component_a_evidence.json'
    snapshot = json.loads(path.read_text())['final']
    result = assess_worker(snapshot, snapshot['workers'][0]['worker_id'])
    assert result.outcome in (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE)
    assert result.simulation_id == snapshot['simulation_id']


def test_malformed_snapshot_returns_structured_result():
    result = assess_worker({}, 'W-01')
    assert result.outcome == Outcome.INSUFFICIENT_DATA
    assert result.simulation_id is None and result.assessment_timestamp is None
    assert result.simulation_based is None


def test_actual_component_a_rest_transition_is_not_assessed_as_work():
    service = SimulationService(instance_id='rest-case')
    initial = service.snapshot()
    worker = next(w for w in initial.workers if w.work_status == 'working')
    request = CommandRequest(schema_version='1.0', simulation_id=initial.simulation_id,
        instance_id=initial.instance_id, expected_state_version=initial.state_version,
        commands=[dict(action='start_rest', worker_id=worker.worker_id, zone_id='REST_ZONE', reason='G2 test')])
    resting = service.mutate('commands', request, 'g2-rest').snapshot
    result = assess_worker(resting, worker.worker_id)
    assert result.outcome == Outcome.NOT_ASSESSABLE
    assert result.issues[0].code == 'unsupported_work_state'
    assert result.reference_limit_celsius is None


def test_unsupported_provenance_retained(complete):
    samples, worker, basis = edited(complete)
    observation(samples[-1], worker)['source'] = 'measured'
    result = run((samples, worker, basis))
    assert result.outcome == Outcome.NOT_ASSESSABLE
    assert result.simulation_based is False and result.wbgt_source == 'measured'


def test_coarse_sampling_not_accepted_as_complete(complete):
    samples, worker, basis = edited(complete)
    for row in samples: row['tick_seconds'] = 3600
    result = run(([samples[0], samples[-1]], worker, basis))
    assert result.outcome == Outcome.NOT_ASSESSABLE
    assert result.issues[0].code == 'unsupported_sampling'
