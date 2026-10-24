"""G4: actual A simulation/API -> G2 -> G3, with explicit synthetic inputs.

Only the test construction of A supplies an existing EngineConfig. No risk result,
command validator, snapshot, clock or decision function is mocked or replaced.
"""
from copy import deepcopy
from dataclasses import replace
from functools import partial
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from heatshift_ai import api_service
from heatshift_ai.api import APISettings, create_app
from heatshift_ai.api_contracts import (
    CommandRequest, ErrorResponse, SimulationCommandResult, SimulationSnapshot, TickRequest,
)
from heatshift_ai.assignment_manager import AssignmentRequest
from heatshift_ai.decision import AssessmentEvidence, Decision, DecisionOutcome, decide
from heatshift_ai.engineering_scenarios import EngineeringScenarioRunner
from heatshift_ai.integrated_engine import EngineConfig
from heatshift_ai.risk import AssessmentBasis, Outcome, RiskAssessment, assess_worker

TOKEN = 'g4-test-only-token-not-a-deployment-secret'


def context(snapshot):
    return {"schema_version": "1.0", "simulation_id": snapshot.simulation_id,
            "instance_id": snapshot.instance_id, "expected_state_version": snapshot.state_version}


def get_state(client):
    response = client.get('/api/v1/simulation/state')
    assert response.status_code == 200
    return SimulationSnapshot.model_validate_json(response.text)


def post(client, path, body, key):
    return client.post(path, json=body, headers={
        'Authorization': 'Bearer ' + TOKEN, 'Idempotency-Key': key})


def chain(samples, basis):
    current = samples[-1]
    risk = assess_worker(current, basis.worker_id, history=samples[:-1], basis=basis)
    evidence = AssessmentEvidence(assessment=risk, history=tuple(samples[:-1]), basis=basis)
    decision = decide(current, basis.worker_id, evidence=evidence)
    return risk, evidence, decision


@pytest.fixture(scope='module')
def integrated_run():
    # Fictional, documented study inputs supplied BEFORE initialization through A's
    # existing configuration models. These assumptions do not validate real workers.
    base = EngineConfig(seed=42)
    config = replace(base,
        worker_config=replace(base.worker_config, count=3,
            qualification_profiles=(frozenset({'inspection'}),),
            acclimatization_statuses=('acclimatized',),
            clothing_profiles=('g4_explicit_one_layer_fixture',)),
        task_config=replace(base.task_config, definitions=tuple(
            replace(t, estimated_metabolic_rate_watts=200.0) for t in base.task_config.definitions)),
        environment_zones=tuple(replace(z, air_temperature_c=28.0,
            globe_temperature_c=28.0, natural_wet_bulb_c=28.0, variability_c=0.0)
            for z in base.environment_zones),
        initial_assignments=(AssignmentRequest(worker_id='W-01', task_id='T-01', zone_id='ZONE_A'),))
    # SimulationService has no config-injection argument. Test-only constructor
    # substitution uses the real runner and preserves its validators and behavior.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(api_service, 'EngineeringScenarioRunner', partial(EngineeringScenarioRunner, config=config))
        service = api_service.SimulationService(seed=42, instance_id='g4-integrated')
    app = create_app(APISettings(token=TOKEN), service=service)
    with TestClient(app) as client:
        start = get_state(client)
        basis = AssessmentBasis(worker_id='W-01', task_id='T-01',
            clothing_profile='g4_explicit_one_layer_fixture', clothing_ensemble='conventional_one_layer',
            clothing_basis='Explicit synthetic G4 one-layer woven clothing scenario.',
            metabolic_rate_basis='Explicit 200 W whole-body synthetic task configuration, not inferred from workload label.',
            population_basis='Synthetic healthy, fit NIOSH reference-person assumption; not a field validation.',
            reference_person_applicable=True)

        def hour(initial, prefix):
            rows = [initial]
            for step in range(360):
                request = TickRequest(**context(rows[-1]), delta_seconds=10)
                rows.append(service.mutate('tick', request, f'{prefix}-{step}').snapshot)
            # Independent HTTP projection must reproduce the service result.
            assert get_state(client) == rows[-1]
            return tuple(rows)

        normal = hour(start, 'normal')
        # Remove the spare workers from availability through A's validated API.
        unavailable = post(client, '/api/v1/simulation/commands', {
            **context(normal[-1]), 'commands': [
                {'action': 'mark_unavailable', 'worker_id': wid,
                 'reason': 'Explicit fictional absence for G4 no-replacement scenario'}
                for wid in ('W-02', 'W-03')]}, 'fixture-absence')
        assert unavailable.status_code == 200
        before_heat = SimulationCommandResult.model_validate_json(unavailable.text).snapshot
        activation = post(client, '/api/v1/scenarios/activate', {
            **context(before_heat), 'scenario_id': 'HEAT_ESCALATION'}, 'heat-activation')
        assert activation.status_code == 200
        hot = hour(SimulationCommandResult.model_validate_json(activation.text).snapshot, 'heat')
        yield client, normal, hot, basis


def test_normal_simulator_history_to_risk_to_decision_preserves_context(integrated_run):
    _, normal, _, basis = integrated_run
    risk, _, decision = chain(normal, basis)
    snapshot = normal[-1]
    worker = next(w for w in snapshot.workers if w.worker_id == basis.worker_id)
    observation = next(z.environment for z in snapshot.zones if z.zone_id == worker.current_zone_id)
    assert risk.outcome == Outcome.WITHIN_APPLICABLE_LIMIT
    assert decision.outcome == DecisionOutcome.NO_INTERVENTION_REQUIRED
    assert (risk.simulation_id, risk.instance_id, risk.state_version, risk.worker_id, risk.task_id, risk.zone_id) == (
        snapshot.simulation_id, snapshot.instance_id, snapshot.state_version,
        worker.worker_id, worker.current_task_id, worker.current_zone_id)
    assert (decision.simulation_id, decision.instance_id, decision.input_state_version,
            decision.affected_worker_id, decision.current_task_id, decision.current_zone_id) == (
        risk.simulation_id, risk.instance_id, risk.state_version, risk.worker_id, risk.task_id, risk.zone_id)
    assert observation.observed_at == snapshot.simulated_at == risk.assessment_timestamp == decision.timestamp
    assert risk.wbgt_source == 'simulated' and risk.simulation_based and decision.simulation_based
    assert risk.metabolic_rate_watts == 200 and risk.sample_count == 361
    assert risk.evidence == basis and risk.limitations and decision.limitations
    assert decision.assessment_reference == risk.assessment_id
    assert decision.selected_proposal is None


def test_actual_heat_ramp_reassesses_and_no_available_replacement_is_not_clearance(integrated_run):
    _, normal, hot, basis = integrated_run
    normal_risk, _, _ = chain(normal, basis)
    risk, _, decision = chain(hot, basis)
    assert hot[-1].scenario == 'HEAT_ESCALATION'
    assert risk.wbgt_twa_celsius > normal_risk.wbgt_twa_celsius
    assert risk.outcome == Outcome.EXCEEDS_APPLICABLE_LIMIT
    assert decision.outcome == DecisionOutcome.NO_FEASIBLE_ACTION
    assert decision.intervention_required and decision.unresolved_intervention and decision.requires_supervisor_review
    assert not decision.mechanically_eligible_replacement_ids and not decision.verified_safe_replacement_ids
    replacements = [a for a in decision.alternatives if a.kind == 'replacement']
    assert {a.worker_id for a in replacements} == {'W-02', 'W-03'}
    assert all(any(c.code == 'availability' and c.status == 'FAIL' for c in a.constraints) for a in replacements)
    assert all(a.feasibility == 'REJECTED' for a in replacements)
    assert decision.selected_proposal is None
    assert decision.manual_stop_work_proposal.submitted is False
    assert decision.manual_stop_work_proposal.thermal_safety_verified is False


def test_serialization_and_repeated_evaluation_are_lossless_and_deterministic(integrated_run):
    _, _, hot, basis = integrated_run
    before = hot[-1].model_dump_json()
    risk, evidence, decision = chain(hot, basis)
    assert RiskAssessment.model_validate_json(risk.model_dump_json()) == risk
    assert Decision.model_validate_json(decision.model_dump_json()) == decision
    decoded = AssessmentEvidence.model_validate_json(evidence.model_dump_json())
    restored_snapshot = SimulationSnapshot.model_validate_json(before)
    assert decide(restored_snapshot, basis.worker_id, evidence=decoded) == decision
    assert assess_worker(restored_snapshot, basis.worker_id, history=decoded.history, basis=decoded.basis) == risk
    assert hot[-1].model_dump_json() == before


@pytest.mark.parametrize('scenario', ['NORMAL_OPERATION', 'HEAT_ESCALATION', 'NO_ELIGIBLE_REPLACEMENT'])
def test_unmodified_http_scenarios_expose_missing_scientific_inputs(scenario):
    service = api_service.SimulationService(instance_id='g4-default-' + scenario)
    with TestClient(create_app(APISettings(token=TOKEN), service=service)) as client:
        s = get_state(client)
        response = post(client, '/api/v1/scenarios/activate', {**context(s), 'scenario_id': scenario}, 'activate')
        assert response.status_code == 200
        s = SimulationCommandResult.model_validate_json(response.text).snapshot
        response = post(client, '/api/v1/simulation/tick', {**context(s), 'delta_seconds': 40}, 'tick')
        assert response.status_code == 200
        s = SimulationCommandResult.model_validate_json(response.text).snapshot
        worker = next(w for w in s.workers if w.work_status == 'working')
        risk = assess_worker(s, worker.worker_id)
        decision = decide(s, worker.worker_id, evidence=AssessmentEvidence(assessment=risk))
        assert risk.outcome == Outcome.INSUFFICIENT_DATA and risk.reference_limit_celsius is None
        assert decision.outcome == DecisionOutcome.INSUFFICIENT_DATA
        assert decision.selected_proposal is None and decision.manual_stop_work_proposal is None
        assert get_state(client) == s


@pytest.mark.parametrize('defect', ['missing_basis', 'missing_history', 'missing', 'stale', 'invalid', 'wrong_unit'])
def test_scientific_input_failures_survive_the_full_python_chain(integrated_run, defect):
    _, normal, _, basis = integrated_run
    current = normal[-1].model_dump(mode='json')
    history = normal[:-1]
    if defect == 'missing_basis': basis = None
    elif defect == 'missing_history': history = ()
    else:
        observation = next(z['environment'] for z in current['zones'] if z['zone_id'] == 'ZONE_A')
        if defect == 'wrong_unit': observation['conditions'][0]['unit'] = 'wrong'
        else: observation['quality'] = defect; observation['wbgt_celsius'] = None
    risk = assess_worker(current, 'W-01', history=history, basis=basis)
    decision = decide(current, 'W-01', evidence=AssessmentEvidence(assessment=risk, history=history, basis=basis))
    assert risk.outcome in (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE)
    assert decision.outcome == DecisionOutcome.INSUFFICIENT_DATA
    assert decision.requires_supervisor_review and decision.selected_proposal is None


def test_proposal_http_auth_stale_atomicity_idempotency_and_confirmed_test_execution(integrated_run):
    # Only this test mutates the completed fixture. Explicit test-harness submission
    # of a review-only draft does not add automatic approval/execution to G3.
    client, _, hot, basis = integrated_run
    _, old_evidence, old_decision = chain(hot, basis)
    draft = old_decision.manual_stop_work_proposal
    assert draft.review_status == 'MANUAL_REVIEW_REQUIRED' and not draft.submitted
    body = draft.body.model_dump(mode='json')
    before = get_state(client)
    denied = client.post('/api/v1/simulation/commands', json=body, headers={'Idempotency-Key': draft.idempotency_key})
    assert denied.status_code == 401 and ErrorResponse.model_validate_json(denied.text).error.code == 'unauthorized'
    assert get_state(client) == before
    advanced = post(client, '/api/v1/simulation/tick', {**context(before), 'delta_seconds': 10}, 'advance-for-conflict')
    assert advanced.status_code == 200
    fresh = SimulationCommandResult.model_validate_json(advanced.text).snapshot
    stale = post(client, '/api/v1/simulation/commands', body, draft.idempotency_key)
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'stale_version'
    assert get_state(client) == fresh
    assert decide(fresh, basis.worker_id, evidence=old_evidence).outcome == DecisionOutcome.INSUFFICIENT_DATA
    _, _, updated = chain((*hot[1:], fresh), basis)
    approved_in_test = updated.manual_stop_work_proposal
    body = approved_in_test.body.model_dump(mode='json')
    assert CommandRequest.model_validate(body).expected_state_version == fresh.state_version
    invalid_batch = deepcopy(body)
    invalid_batch['commands'].append({'action': 'assign_task', 'worker_id': 'W-02',
        'task_id': 'T-02', 'zone_id': 'ZONE_A', 'reason': 'Test must reject unavailable and unqualified replacement'})
    rejected = post(client, '/api/v1/simulation/commands', invalid_batch, 'invalid-atomic-batch')
    assert rejected.status_code == 422 and rejected.json()['error']['code'] == 'domain_rejection'
    assert get_state(client) == fresh  # First stop in the rejected batch was also rolled back.
    key = approved_in_test.idempotency_key
    first = post(client, '/api/v1/simulation/commands', body, key)
    assert first.status_code == 200
    result = SimulationCommandResult.model_validate_json(first.text)
    assert result.status == 'applied' and result.before_state_version == fresh.state_version
    assert result.after_state_version == result.state_version == fresh.state_version + 1
    confirmed = get_state(client)
    assert confirmed == result.snapshot
    worker = next(w for w in confirmed.workers if w.worker_id == basis.worker_id)
    task = next(t for t in confirmed.tasks if t.task_id == basis.task_id)
    assert worker.work_status == 'idle' and worker.current_task_id is None and worker.current_zone_id == 'ZONE_A'
    assert task.task_status == 'pending' and task.assigned_worker_id is None
    new_events = [e for e in confirmed.events if e.event_id in result.event_ids]
    assert {e.action for e in new_events} == {'stop_work', 'commands'}
    assert all(e.before_state_version == fresh.state_version and e.after_state_version == confirmed.state_version for e in new_events)
    assert post(client, '/api/v1/simulation/pause', context(confirmed), 'later-pause').status_code == 200
    later = get_state(client)
    replay = post(client, '/api/v1/simulation/commands', body, key)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert get_state(client) == later and later.state_version > replay.json()['state_version']
    changed = deepcopy(body); changed['commands'][0]['reason'] = 'Different request with same key'
    conflict = post(client, '/api/v1/simulation/commands', changed, key)
    assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'idempotency_conflict'
    assert get_state(client) == later
    assert old_decision.selected_proposal is None and not approved_in_test.submitted


def assert_local_refs_resolve(document):
    def visit(value):
        if isinstance(value, dict):
            if '$ref' in value:
                assert value['$ref'].startswith('#/')
                resolved = document
                for part in value['$ref'][2:].split('/'):
                    resolved = resolved[part.replace('~1', '/').replace('~0', '~')]
                assert isinstance(resolved, dict)
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    visit(document)


def test_openapi_and_python_schemas_match_actual_boundaries():
    app = create_app(APISettings(token=TOKEN))
    spec = app.openapi()
    canonical = json.loads((Path(__file__).resolve().parents[1] / 'openapi.json').read_text())
    assert spec == canonical
    assert_local_refs_resolve(spec)
    assert spec['paths']['/api/v1/simulation/commands']['post']['requestBody']['content']['application/json']['schema']['$ref'].endswith('/CommandRequest')
    for path, methods in spec['paths'].items():
        assert 'risk' not in path and 'decision' not in path
        for verb, operation in methods.items():
            if verb != 'post': continue
            assert operation['security'] == [{'HTTPBearer': []}]
            assert any(p['name'] == 'Idempotency-Key' and p['required'] for p in operation['parameters'])
            assert operation['responses']['200']['content']['application/json']['schema']['$ref'].endswith('/SimulationCommandResult')
    for model in (RiskAssessment, AssessmentEvidence, Decision):
        assert_local_refs_resolve(model.model_json_schema())
    with TestClient(app) as client:
        state = get_state(client)
        malformed = post(client, '/api/v1/simulation/commands', {**context(state), 'commands': []}, 'malformed')
        assert malformed.status_code == 422
        assert ErrorResponse.model_validate_json(malformed.text).error.code == 'invalid_request'
        assert get_state(client) == state
