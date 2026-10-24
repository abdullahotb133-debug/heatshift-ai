"""G3 tests use actual G2 computation, never invented risk outcomes or winners."""
from copy import deepcopy
import json

import pytest

from test_risk import complete as reference_history
from heatshift_ai.api_contracts import ActivateRequest, CommandRequest, SimulationSnapshot, TickRequest
from heatshift_ai.api_service import SimulationService
from heatshift_ai.decision import AssessmentEvidence, DecisionOutcome, decide
from heatshift_ai.risk import Outcome, assess_worker
from heatshift_ai.serialization import to_json_value
from heatshift_ai.workers import Worker


def evidence_for(current, worker_id, history=(), basis=None):
    result = assess_worker(current, worker_id, history=history, basis=basis)
    return AssessmentEvidence(assessment=result,
        history=tuple(SimulationSnapshot.model_validate(s) if isinstance(s, dict) else s for s in history), basis=basis)


@pytest.fixture(scope='module')
def excess(reference_history):
    samples, worker, basis = reference_history
    # Explicit clothing scenario, evaluated by the real G2 function: 28 + 3 > REL.
    basis = basis.model_copy(update={'clothing_ensemble': 'double_layer_cloth',
        'clothing_basis': 'G3 synthetic reference scenario: double-layer cloth, NIOSH Table 3-2.'})
    evidence = evidence_for(samples[-1], worker, samples[:-1], basis)
    assert evidence.assessment.outcome == Outcome.EXCEEDS_APPLICABLE_LIMIT
    return samples, worker, basis, evidence


def configured_candidate(current, affected, *, worker_id='G3-CAND-A', qualifications=None,
                         availability='available', resting=False):
    """Create an explicit fictional fixture before assessment; engine never grants skills."""
    current = deepcopy(current)
    target = next(w for w in current['workers'] if w['worker_id'] == affected)
    task = next(t for t in current['tasks'] if t['task_id'] == target['current_task_id'])
    worker = Worker(worker_id=worker_id, display_name='Fictional G3 fixture candidate',
        current_zone_id='REST_ZONE' if resting else target['current_zone_id'],
        qualifications=frozenset(task['required_qualifications'] if qualifications is None else qualifications),
        availability_status='unavailable' if resting else availability,
        work_status='resting' if resting else 'idle')
    current['workers'].append(to_json_value(worker))
    return current


def run_changed(excess, current, candidate_evidence=None):
    samples, worker, basis, _ = excess
    evidence = evidence_for(current, worker, samples[:-1], basis)
    assert evidence.assessment.outcome == Outcome.EXCEEDS_APPLICABLE_LIMIT
    return decide(current, worker, evidence=evidence, candidate_evidence=candidate_evidence)


def candidate_alternatives(result, candidate='G3-CAND-A'):
    return [a for a in result.alternatives if a.kind == 'replacement' and a.worker_id == candidate]


def status(alternative, code):
    return next(c.status for c in alternative.constraints if c.code == code)


def test_verified_excess_identification_and_no_false_clearance(excess):
    samples, worker, _, evidence = excess
    result = decide(samples[-1], worker, evidence=evidence)
    assert result.outcome == DecisionOutcome.NO_FEASIBLE_ACTION
    assert result.intervention_required and result.unresolved_intervention
    assert result.requires_supervisor_review and result.assessment_reference == evidence.assessment.assessment_id
    assert result.selected_proposal is None and not result.verified_safe_replacement_ids
    assert result.manual_stop_work_proposal.review_status == 'MANUAL_REVIEW_REQUIRED'
    assert not result.manual_stop_work_proposal.submitted


def test_within_limit_is_relative_to_verified_historical_assessment(reference_history):
    samples, worker, basis = reference_history
    evidence = evidence_for(samples[-1], worker, samples[:-1], basis)
    result = decide(samples[-1], worker, evidence=evidence)
    assert result.outcome == DecisionOutcome.NO_INTERVENTION_REQUIRED
    assert result.intervention_required is False
    assert result.selected_proposal is None and result.manual_stop_work_proposal is None


@pytest.mark.parametrize('field,value', [('outcome', Outcome.WITHIN_APPLICABLE_LIMIT),
    ('reference_limit_celsius', 999.0), ('assessment_id', 'invented'), ('methodology_version', 'unverified'),
    ('explanation', 'invented clearance')])
def test_tampered_risk_output_is_rejected(excess, field, value):
    samples, worker, _, evidence = excess
    tampered = evidence.model_copy(update={'assessment': evidence.assessment.model_copy(update={field: value})})
    result = decide(samples[-1], worker, evidence=tampered)
    assert result.outcome == DecisionOutcome.INSUFFICIENT_DATA
    assert result.constraints[0].code == 'assessment_integrity'
    assert result.manual_stop_work_proposal is None


@pytest.mark.parametrize('field,value', [('state_version', 1), ('instance_id', 'old-instance'),
    ('worker_id', 'W-OTHER'), ('task_id', 'T-OTHER'), ('zone_id', 'ZONE_OTHER')])
def test_stale_or_wrong_context_rejected(excess, field, value):
    samples, worker, _, evidence = excess
    old = evidence.model_copy(update={'assessment': evidence.assessment.model_copy(update={field: value})})
    result = decide(samples[-1], worker, evidence=old)
    assert result.outcome == DecisionOutcome.INSUFFICIENT_DATA
    assert result.constraints[0].code == 'assessment_context'


def test_qualified_available_candidate_considered_but_not_cleared(excess):
    samples, worker, _, _ = excess
    current = configured_candidate(samples[-1], worker)
    result = run_changed(excess, current)
    choices = candidate_alternatives(result)
    assert any(a.mechanical_eligibility for a in choices)
    assert 'G3-CAND-A' in result.mechanically_eligible_replacement_ids
    assert all(status(a, 'prospective_exposure_supported') == 'UNKNOWN' for a in choices)
    assert result.selected_proposal is None


@pytest.mark.parametrize('kwargs,code', [({'qualifications': ()}, 'qualifications'),
    ({'availability': 'unavailable'}, 'availability'), ({'resting': True}, 'idle_not_resting')])
def test_hard_candidate_constraints(excess, kwargs, code):
    current = configured_candidate(excess[0][-1], excess[1], **kwargs)
    result = run_changed(excess, current)
    alternatives = candidate_alternatives(result)
    assert alternatives and all(status(a, code) == 'FAIL' for a in alternatives)
    assert all(not a.mechanical_eligibility for a in alternatives)
    assert 'G3-CAND-A' not in result.mechanically_eligible_replacement_ids


def test_existing_assignments_respected(excess):
    samples, worker, _, evidence = excess
    assigned = next(w['worker_id'] for w in samples[-1]['workers'] if w['current_task_id'] and w['worker_id'] != worker)
    result = decide(samples[-1], worker, evidence=evidence)
    alternatives = candidate_alternatives(result, assigned)
    assert alternatives and all(status(a, 'no_existing_assignment') == 'FAIL' for a in alternatives)


def test_task_destination_must_be_a_permitted_work_zone(excess):
    result = run_changed(excess, configured_candidate(excess[0][-1], excess[1]))
    rest = next(a for a in candidate_alternatives(result) if a.destination_zone_id == 'REST_ZONE')
    assert status(rest, 'work_zone') == 'FAIL' and status(rest, 'allowed_task_zone') == 'FAIL'


@pytest.mark.parametrize('quality', ['missing', 'stale', 'invalid'])
def test_unavailable_rest_destination_rejected(excess, quality):
    current = deepcopy(excess[0][-1])
    rest = next(z['environment'] for z in current['zones'] if z['zone_id'] == 'REST_ZONE')
    rest['quality'] = quality; rest['wbgt_celsius'] = None
    result = run_changed(excess, current)
    choice = next(a for a in result.alternatives if a.kind == 'rest')
    assert status(choice, 'destination_observation_available') == 'FAIL'
    assert choice.feasibility == 'REJECTED' and result.selected_proposal is None


def test_cooler_rest_zone_does_not_establish_safe_rest(excess):
    result = decide(excess[0][-1], excess[1], evidence=excess[3])
    rest = next(a for a in result.alternatives if a.kind == 'rest')
    assert status(rest, 'destination_observation_available') == 'PASS'
    assert status(rest, 'prospective_exposure_supported') == 'UNKNOWN'
    assert rest.feasibility == 'UNVERIFIED'


def test_current_unknown_candidate_assessment_is_not_safe(excess):
    current = configured_candidate(excess[0][-1], excess[1])
    candidate = evidence_for(current, 'G3-CAND-A')
    assert candidate.assessment.outcome == Outcome.NOT_ASSESSABLE
    result = run_changed(excess, current, {'G3-CAND-A': candidate})
    alternatives = candidate_alternatives(result)
    assert all(status(a, 'assessment_integrity') == 'PASS' for a in alternatives)
    assert all(status(a, 'candidate_current_exposure') == 'UNKNOWN' for a in alternatives)
    assert not result.verified_safe_replacement_ids


def test_foreign_risk_cannot_clear_candidate(excess):
    current = configured_candidate(excess[0][-1], excess[1])
    result = run_changed(excess, current, {'G3-CAND-A': excess[3]})
    assert all(status(a, 'assessment_context') == 'FAIL' for a in candidate_alternatives(result))


def test_no_eligible_replacement_preserves_unresolved_intervention(excess):
    current = deepcopy(excess[0][-1])
    for w in current['workers']:
        if w['current_task_id'] is None: w['availability_status'] = 'unavailable'
    result = run_changed(excess, current)
    assert result.outcome == DecisionOutcome.NO_FEASIBLE_ACTION
    assert not result.mechanically_eligible_replacement_ids
    assert result.intervention_required and result.unresolved_intervention and result.requires_supervisor_review
    assert result.selected_proposal is None


def test_multiple_mechanically_eligible_candidates_have_stable_order_not_fake_winner(excess):
    current = configured_candidate(excess[0][-1], excess[1], worker_id='G3-CAND-B')
    current = configured_candidate(current, excess[1], worker_id='G3-CAND-A')
    first = run_changed(excess, current)
    second = run_changed(excess, current)
    assert first == second
    assert first.mechanically_eligible_replacement_ids == tuple(sorted(first.mechanically_eligible_replacement_ids))
    assert {'G3-CAND-A', 'G3-CAND-B'} <= set(first.mechanically_eligible_replacement_ids)
    assert first.selected_proposal is None
    # Feasible thermal selection is deliberately NOT claimed/tested with fabricated evidence.


def test_json_rejections_and_input_immutability(excess):
    before = json.dumps(excess[0], sort_keys=True)
    result = decide(excess[0][-1], excess[1], evidence=excess[3])
    payload = json.loads(result.model_dump_json())
    assert payload['input_state_version'] == excess[0][-1]['state_version']
    assert all(any(c['status'] != 'PASS' for c in a['constraints']) for a in payload['alternatives'])
    assert all(a.rejection_reasons for a in result.alternatives)
    assert json.dumps(excess[0], sort_keys=True) == before


def test_review_only_proposal_matches_openapi_and_canonical_a_transition(excess):
    from pathlib import Path
    from heatshift_ai.assignments import Assignment
    from heatshift_ai.state import SimulationState
    from heatshift_ai.tasks import Task
    from heatshift_ai.time import SimulationTime
    from heatshift_ai.transitions import WorkerStateManager
    from heatshift_ai.zones import Zone

    result = decide(excess[0][-1], excess[1], evidence=excess[3])
    draft = result.manual_stop_work_proposal
    body = CommandRequest.model_validate_json(draft.body.model_dump_json())
    spec = json.loads((Path(__file__).resolve().parents[1]/'openapi.json').read_text())
    supported = spec['components']['schemas']['SimulationCommand']['properties']['action']['enum']
    assert all(c.action in supported for c in body.commands)
    assert body.instance_id == result.instance_id and body.expected_state_version == result.input_state_version
    state = SimulationSnapshot.model_validate(excess[0][-1])
    domain = SimulationState(
        workers=tuple(Worker(**{**w.model_dump(), 'qualifications': frozenset(w.qualifications)}) for w in state.workers),
        tasks=tuple(Task(**{**t.model_dump(), 'required_qualifications': frozenset(t.required_qualifications),
                           'allowed_zone_ids': frozenset(t.allowed_zone_ids)}) for t in state.tasks),
        zones=tuple(Zone(zone_id=z.zone_id, kind=z.kind) for z in state.zones),
        assignments=tuple(Assignment(**a.model_dump()) for a in state.assignments),
        time=SimulationTime(elapsed_seconds=state.elapsed_seconds, tick_seconds=state.tick_seconds))
    # Test-only canonical A transition on a detached fixture, never an HTTP submission.
    manager = WorkerStateManager(domain)
    command = body.commands[0]
    manager.stop_work(worker_id=command.worker_id, reason=command.reason)
    after = manager.state
    stopped = next(w for w in after.workers if w.worker_id == excess[1])
    task = next(t for t in after.tasks if t.task_id == result.current_task_id)
    assert stopped.work_status == 'idle' and stopped.current_task_id is None
    assert stopped.current_zone_id == result.current_zone_id
    assert task.task_status == 'pending' and task.assigned_worker_id is None
    assert after.time == domain.time and result.selected_proposal is None


@pytest.mark.parametrize('scenario', ['HEAT_ESCALATION', 'NO_ELIGIBLE_REPLACEMENT'])
def test_actual_component_a_scenarios_do_not_fabricate_missing_g2_inputs(scenario):
    service = SimulationService(instance_id='g3-' + scenario)
    s = service.snapshot()
    request = ActivateRequest(schema_version='1.0', simulation_id=s.simulation_id, instance_id=s.instance_id,
                              expected_state_version=s.state_version, scenario_id=scenario)
    s = service.mutate('activate', request, 'activate').snapshot
    tick = TickRequest(schema_version='1.0', simulation_id=s.simulation_id, instance_id=s.instance_id,
                       expected_state_version=s.state_version, delta_seconds=40)
    s = service.mutate('tick', tick, 'tick').snapshot
    target_task = 'T-01' if scenario == 'HEAT_ESCALATION' else 'T-04'
    worker = next(t.assigned_worker_id for t in s.tasks if t.task_id == target_task)
    evidence = evidence_for(s, worker)
    result = decide(s, worker, evidence=evidence)
    assert evidence.assessment.outcome == Outcome.INSUFFICIENT_DATA
    assert result.outcome == DecisionOutcome.INSUFFICIENT_DATA
    assert result.selected_proposal is None and result.manual_stop_work_proposal is None
    assert service.snapshot() == s


@pytest.mark.parametrize('defect', ['no_evidence', 'invalid_snapshot', 'unknown_worker', 'broken_assignment'])
def test_invalid_or_missing_input_fails_closed(excess, defect):
    current = deepcopy(excess[0][-1]); worker = excess[1]; evidence = excess[3]
    if defect == 'no_evidence': evidence = None
    if defect == 'invalid_snapshot': current = {}
    if defect == 'unknown_worker': worker = 'NOT-PRESENT'
    if defect == 'broken_assignment': current['assignments'] = []
    result = decide(current, worker, evidence=evidence)
    assert result.outcome == DecisionOutcome.INSUFFICIENT_DATA
    assert result.selected_proposal is None and result.manual_stop_work_proposal is None


@pytest.mark.parametrize('quality', ['missing', 'stale', 'invalid'])
def test_affected_worker_missing_environment_never_becomes_no_intervention(excess, quality):
    samples, worker, basis, _ = excess
    current = deepcopy(samples[-1])
    zone_id = next(w['current_zone_id'] for w in current['workers'] if w['worker_id'] == worker)
    observation = next(z['environment'] for z in current['zones'] if z['zone_id'] == zone_id)
    observation['quality'] = quality; observation['wbgt_celsius'] = None
    evidence = evidence_for(current, worker, samples[:-1], basis)
    assert evidence.assessment.outcome == Outcome.INSUFFICIENT_DATA
    result = decide(current, worker, evidence=evidence)
    assert result.outcome == DecisionOutcome.INSUFFICIENT_DATA
    assert result.intervention_required is None and result.requires_supervisor_review
    assert result.selected_proposal is None


def test_replacement_current_environment_is_checked_separately(excess):
    current = configured_candidate(excess[0][-1], excess[1])
    next(w for w in current['workers'] if w['worker_id'] == 'G3-CAND-A')['current_zone_id'] = 'REST_ZONE'
    next(z['environment'] for z in current['zones'] if z['zone_id'] == 'REST_ZONE')['quality'] = 'invalid'
    result = run_changed(excess, current)
    alternatives = candidate_alternatives(result)
    assert all(status(a, 'candidate_current_observation_available') == 'FAIL' for a in alternatives)
    assert all(a.feasibility == 'REJECTED' for a in alternatives)
