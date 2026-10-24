"""Corrective scenarios: actual A histories/forecasts, unchanged G2 equations."""
from dataclasses import replace
from decimal import Decimal, localcontext
import pytest

from test_backend_integration import integrated_run as baseline_run, context, post
from heatshift_ai.api_contracts import EnvironmentalObservation, SimulationCommandResult, SimulationSnapshot, simulation_timestamp
from heatshift_ai.decision import AssessmentEvidence, Decision, DecisionOutcome, decide
from heatshift_ai.engineering_scenarios import load_scenario
from heatshift_ai.environmental_simulator import EnvironmentalSimulator, default_environment_zones
from heatshift_ai.prospective import ProspectivePlan, ProspectiveAssessment, assess_proposed_assignment, snapshot_fingerprint
from heatshift_ai.risk import Outcome, assess_worker
from heatshift_ai.serialization import to_json_value


def forecast(current, zone):
    # Same explicit 28 C input configuration as the actual G4 source simulation.
    zones = tuple(replace(z, air_temperature_c=28.0, globe_temperature_c=28.0,
                          natural_wet_bulb_c=28.0, variability_c=0.0) for z in default_environment_zones())
    definition = replace(load_scenario('HEAT_ESCALATION', seed=42), start_seconds=3600)
    simulator = EnvironmentalSimulator(seed=42, zones=zones, forcing=definition.forcing())
    samples = []
    for t in range(current.elapsed_seconds, current.elapsed_seconds + 3601, 10):
        raw = to_json_value(simulator.observe(zone_id=zone, elapsed_seconds=t))
        # Match A's snapshot projection: domain metadata is immutable pairs.
        meta = raw['source_metadata'] = dict(raw['source_metadata'])
        raw.update(observed_at_seconds=int(meta['observed_at_seconds']), quality=meta['quality'],
                   wbgt_kind=meta['wbgt_kind'], observed_at=simulation_timestamp(int(meta['observed_at_seconds'])))
        samples.append(EnvironmentalObservation.model_validate(raw))
    return tuple(samples)


@pytest.fixture(scope='module')
def scenario(baseline_run):
    client, _, hot, basis = baseline_run
    response = post(client, '/api/v1/simulation/commands', {**context(hot[-1]), 'commands': [
        {'action': 'mark_available', 'worker_id': wid, 'reason': 'Explicit fictional candidate availability'}
        for wid in ('W-02', 'W-03')]}, 'corrective-candidates')
    assert response.status_code == 200
    current = SimulationCommandResult.model_validate_json(response.text).snapshot
    return client, hot[:-1], current, basis


def plan_for(scenario, worker='W-02', zone='ZONE_B', *, current=None, task='T-01', ensemble='conventional_one_layer'):
    current = scenario[2] if current is None else current
    person = next(w for w in current.workers if w.worker_id == worker)
    basis = scenario[3].model_copy(update={'worker_id': worker, 'task_id': task,
        'clothing_profile': person.clothing_profile, 'clothing_ensemble': ensemble,
        'metabolic_rate_basis': 'Explicit numeric rate of the proposed synthetic task in this exact snapshot.'})
    return ProspectivePlan(origin_fingerprint=snapshot_fingerprint(current), worker_id=worker,
        task_id=task, destination_zone_id=zone, duration_seconds=3600,
        forecast_source='explicit_simulation_scenario',
        forecast_basis='A EnvironmentalSimulator: seed 42, documented 28 C configuration, unchanged HEAT_ESCALATION forcing beginning at t=3600; no new interventions during the planned hour.',
        prior_exposure_basis='Explicit idealized reference-person assumption: candidate has no pre-existing heat strain. Not inferred from idle status, counters or a medical measurement.',
        prior_heat_strain_excluded=True, basis=basis, observations=forecast(current, zone))


def evaluate(scenario, plans, *, current=None, candidate_evidence=None):
    current = scenario[2] if current is None else current
    risk = assess_worker(current, 'W-01', history=scenario[1], basis=scenario[3])
    assert risk.outcome == Outcome.EXCEEDS_APPLICABLE_LIMIT
    evidence = AssessmentEvidence(assessment=risk, history=scenario[1], basis=scenario[3])
    return decide(current, 'W-01', evidence=evidence, prospective_plans=plans, candidate_evidence=candidate_evidence)


def adjusted(scenario, change):
    raw = scenario[2].model_dump(mode='json')
    change(raw)
    return SimulationSnapshot.model_validate(raw)


def test_complete_prospective_reference_and_reproducibility(scenario):
    plan = plan_for(scenario)
    result = assess_proposed_assignment(scenario[2], plan.worker_id, plan.task_id, plan.destination_zone_id, plan=plan)
    with localcontext() as ctx:
        ctx.prec = 50
        limit = Decimal('56.7') - Decimal('11.5') * Decimal(200).ln() / Decimal(10).ln()
        total = sum((Decimal(str(a.wbgt_celsius)) + Decimal(str(b.wbgt_celsius))) / 2 *
                    Decimal(b.elapsed_seconds-a.elapsed_seconds) for a, b in zip(plan.observations, plan.observations[1:]))
    assert result.reference_limit_celsius == pytest.approx(float(limit), abs=1e-12)
    assert result.wbgt_twa_celsius == pytest.approx(float(total / Decimal(3600)))
    assert result.outcome == Outcome.WITHIN_APPLICABLE_LIMIT
    assert result.evaluation_mode == 'prospective_simulation' and result.wbgt_source == 'simulated'
    assert result.sample_count == 361 and result.state_version == scenario[2].state_version
    assert result.assessment_timestamp == scenario[2].simulated_at
    assert result.window_end_seconds == scenario[2].elapsed_seconds + 3600
    assert result.evidence == plan.basis and result.forecast_basis and result.limitations
    assert ProspectiveAssessment.model_validate_json(result.model_dump_json()) == result
    assert assess_proposed_assignment(scenario[2], 'W-02', 'T-01', 'ZONE_B', plan=plan.model_dump(mode='json')) == result


def test_proposed_task_rate_not_idle_workers_current_workload_is_used(scenario):
    current = adjusted(scenario, lambda raw: next(t for t in raw['tasks'] if t['task_id'] == 'T-02').update(estimated_metabolic_rate_watts=400.0))
    plan = plan_for(scenario, current=current, task='T-02')
    result = assess_proposed_assignment(current, 'W-02', 'T-02', 'ZONE_B', plan=plan)
    assert result.metabolic_rate_watts == 400 and result.task_id == 'T-02'
    assert result.outcome == Outcome.EXCEEDS_APPLICABLE_LIMIT


@pytest.mark.parametrize('zone,ensemble,acclimatization,outcome', [
    ('ZONE_B', 'conventional_one_layer', 'acclimatized', Outcome.WITHIN_APPLICABLE_LIMIT),
    ('ZONE_A', 'conventional_one_layer', 'acclimatized', Outcome.EXCEEDS_APPLICABLE_LIMIT),
    ('ZONE_B', 'double_layer_cloth', 'acclimatized', Outcome.EXCEEDS_APPLICABLE_LIMIT),
    ('ZONE_B', 'conventional_one_layer', 'not_acclimatized', Outcome.EXCEEDS_APPLICABLE_LIMIT),
])
def test_destination_clothing_and_acclimatization_are_not_overridden(scenario, zone, ensemble, acclimatization, outcome):
    current = adjusted(scenario, lambda raw: next(w for w in raw['workers'] if w['worker_id'] == 'W-02').update(acclimatization_status=acclimatization))
    plan = plan_for(scenario, current=current, zone=zone, ensemble=ensemble)
    result = assess_proposed_assignment(current, 'W-02', 'T-01', zone, plan=plan)
    assert result.zone_id == zone and result.acclimatization_status == acclimatization
    assert result.clothing_adjustment_celsius == (3 if ensemble == 'double_layer_cloth' else 0)
    assert result.outcome == outcome


@pytest.mark.parametrize('defect', ['absent', 'duration', 'gap', 'duplicate', 'origin', 'wrong_worker', 'missing', 'stale',
    'invalid', 'wbgt', 'unit', 'measured', 'timestamp', 'clothing', 'fitness', 'prior_strain'])
def test_missing_invalid_or_unsupported_forecasts_never_approve(scenario, defect):
    plan = plan_for(scenario).model_dump(mode='json')
    if defect == 'absent': plan = None
    elif defect == 'duration': plan['duration_seconds'] = 1800
    elif defect == 'gap': plan['observations'].pop(180)
    elif defect == 'duplicate': plan['observations'][180] = plan['observations'][179]
    elif defect == 'origin': plan['origin_fingerprint'] = 'stale'
    elif defect == 'wrong_worker': plan['worker_id'] = 'W-03'
    elif defect in ('missing', 'stale', 'invalid'): plan['observations'][180]['quality'] = defect
    elif defect == 'wbgt': plan['observations'][180]['wbgt_celsius'] = None
    elif defect == 'unit': plan['observations'][180]['conditions'][0]['unit'] = 'degF'
    elif defect == 'measured': plan['observations'][180]['source'] = 'measured'
    elif defect == 'timestamp': plan['observations'][180]['observed_at_seconds'] -= 1
    elif defect == 'clothing': plan['basis']['clothing_ensemble'] = 'unknown'
    elif defect == 'fitness': plan['basis']['reference_person_applicable'] = False
    elif defect == 'prior_strain': plan['prior_heat_strain_excluded'] = False
    result = assess_proposed_assignment(scenario[2], 'W-02', 'T-01', 'ZONE_B', plan=plan)
    assert result.outcome in (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE)
    assert result.issues and result.reference_limit_celsius is None


@pytest.mark.parametrize('status', ['unknown', 'partially_acclimatized'])
def test_unsupported_worker_factors_fail_closed(scenario, status):
    current = adjusted(scenario, lambda raw: next(w for w in raw['workers'] if w['worker_id'] == 'W-02').update(acclimatization_status=status))
    result = assess_proposed_assignment(current, 'W-02', 'T-01', 'ZONE_B', plan=plan_for(scenario, current=current))
    assert result.outcome in (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE)


def test_missing_proposed_workload_cannot_use_old_rate(scenario):
    current = adjusted(scenario, lambda raw: next(t for t in raw['tasks'] if t['task_id'] == 'T-02').update(estimated_metabolic_rate_watts=None))
    result = assess_proposed_assignment(current, 'W-02', 'T-02', 'ZONE_B', plan=plan_for(scenario, current=current, task='T-02'))
    assert result.outcome == Outcome.INSUFFICIENT_DATA
    assert result.issues[0].code == 'missing_metabolic_rate'


@pytest.mark.parametrize('defect', ['paused', 'invalid_identifier'])
def test_projection_does_not_start_from_invalid_operational_context(scenario, defect):
    current = scenario[2]
    if defect == 'paused': current = adjusted(scenario, lambda raw: raw.update(paused=True))
    result = assess_proposed_assignment(current, object() if defect == 'invalid_identifier' else 'W-02',
        'T-01', 'ZONE_B', plan=None)
    assert result.outcome in (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE)
    assert result.reference_limit_celsius is None


def test_conflicting_current_candidate_evidence_blocks_an_otherwise_acceptable_forecast(scenario):
    risk = assess_worker(scenario[2], 'W-01', history=scenario[1], basis=scenario[3])
    wrong_person = AssessmentEvidence(assessment=risk, history=scenario[1], basis=scenario[3])
    result = evaluate(scenario, [plan_for(scenario)], candidate_evidence={'W-02': wrong_person})
    assert result.selected_proposal is None
    choice = next(a for a in result.alternatives if a.worker_id == 'W-02' and a.destination_zone_id == 'ZONE_B')
    assert any(c.code == 'assessment_context' and c.status == 'FAIL' for c in choice.constraints)


def test_valid_replacement_and_stable_selection_from_actual_forecasts(scenario):
    plans = [plan_for(scenario, worker='W-03'), plan_for(scenario, worker='W-02')]
    first, second = evaluate(scenario, plans), evaluate(scenario, list(reversed(plans)))
    assert first == second and first.outcome == DecisionOutcome.ACTION_PROPOSED
    assert first.prospectively_acceptable_replacement_ids == ('W-02', 'W-03')
    assert first.selected_proposal.proposed_replacement_worker_id == 'W-02'  # equal margin -> ID order
    assert first.selected_proposal.proposed_destination_zone_id == 'ZONE_B'
    assert first.unresolved_intervention and first.requires_supervisor_review
    assert not first.verified_safe_replacement_ids and not first.selected_proposal.thermal_safety_verified
    assert not first.selected_proposal.submitted
    assert Decision.model_validate_json(first.model_dump_json()) == first
    assert all(a.rejection_reasons for a in first.alternatives if a.feasibility != 'FEASIBLE_FOR_REVIEW')


def test_unsafe_even_cooler_replacements_are_rejected(scenario):
    # 28 C is cooler than A but exceeds the actual unacclimatized 200 W RAL.
    def change(raw):
        for w in raw['workers']:
            if w['worker_id'] != 'W-01': w['acclimatization_status'] = 'not_acclimatized'
    current = adjusted(scenario, change)
    plans = [plan_for(scenario, worker=w, zone=z, current=current)
             for w in ('W-02', 'W-03') for z in ('ZONE_A', 'ZONE_B', 'ZONE_C')]
    result = evaluate(scenario, plans, current=current)
    assert result.outcome == DecisionOutcome.NO_FEASIBLE_ACTION and result.unresolved_intervention
    assert result.selected_proposal is None
    choices = [a for a in result.alternatives if a.kind == 'replacement' and a.mechanical_eligibility]
    assert choices and all(a.prospective_assessment.outcome == Outcome.EXCEEDS_APPLICABLE_LIMIT for a in choices)
    assert all(any(c.code == 'prospective_exposure' and c.status == 'FAIL' for c in a.constraints) for a in choices)


def test_insufficient_forecast_preserves_known_intervention(scenario):
    result = evaluate(scenario, [])
    assert result.outcome == DecisionOutcome.INSUFFICIENT_DATA
    assert result.intervention_required and result.unresolved_intervention and result.selected_proposal is None


@pytest.mark.parametrize('defect', ['unqualified', 'unavailable', 'resting', 'assigned'])
def test_prospective_pass_never_overrides_hard_constraints(scenario, defect):
    def change(raw):
        for w in raw['workers']:
            if w['worker_id'] == 'W-01': continue
            if defect == 'unqualified': w['qualifications'] = []
            elif defect == 'unavailable': w['availability_status'] = 'unavailable'
            elif defect == 'resting': w.update(availability_status='unavailable', work_status='resting', current_zone_id='REST_ZONE')
            elif defect == 'assigned':
                tid = 'T-02' if w['worker_id'] == 'W-02' else 'T-03'
                t = next(t for t in raw['tasks'] if t['task_id'] == tid)
                w.update(current_task_id=tid, qualifications=t['required_qualifications'], current_zone_id='ZONE_B')
                t.update(assigned_worker_id=w['worker_id'], task_status='assigned')
                raw['assignments'].append(dict(worker_id=w['worker_id'], task_id=tid, zone_id='ZONE_B', started_at_elapsed_seconds=raw['elapsed_seconds']))
    current = adjusted(scenario, change)
    plans = [plan_for(scenario, worker=w, current=current) for w in ('W-02', 'W-03')]
    result = evaluate(scenario, plans, current=current)
    assert result.outcome == DecisionOutcome.NO_FEASIBLE_ACTION
    assert not result.mechanically_eligible_replacement_ids and result.selected_proposal is None


def test_stale_plan_cannot_be_rebound_by_only_changing_assessment_context(scenario):
    plan = plan_for(scenario)
    current = adjusted(scenario, lambda raw: raw.update(state_version=raw['state_version'] + 1))
    result = evaluate(scenario, [plan], current=current)
    assert result.selected_proposal is None and result.unresolved_intervention
    choice = next(a for a in result.alternatives if a.worker_id == 'W-02' and a.destination_zone_id == 'ZONE_B')
    assert choice.prospective_assessment.issues[0].code == 'prospective_context_mismatch'


def test_controlled_simulated_proposal_execution_uses_a_contract_and_confirms_state(scenario):
    client, _, current, _ = scenario
    decision = evaluate(scenario, [plan_for(scenario)])
    proposal = decision.selected_proposal
    response = post(client, '/api/v1/simulation/commands', proposal.body.model_dump(mode='json'), proposal.idempotency_key)
    assert response.status_code == 200
    result = SimulationCommandResult.model_validate_json(response.text)
    confirmed = SimulationSnapshot.model_validate_json(client.get('/api/v1/simulation/state').text)
    assert result.snapshot == confirmed and confirmed.state_version == current.state_version + 1
    affected = next(w for w in confirmed.workers if w.worker_id == 'W-01')
    replacement = next(w for w in confirmed.workers if w.worker_id == proposal.proposed_replacement_worker_id)
    assert affected.work_status == 'idle' and affected.availability_status == 'unavailable'
    assert affected.current_zone_id == 'ZONE_A'  # No unsupported recovery/movement claim.
    assert replacement.work_status == 'working' and replacement.current_task_id == 'T-01' and replacement.current_zone_id == 'ZONE_B'
    repeated = post(client, '/api/v1/simulation/commands', proposal.body.model_dump(mode='json'), proposal.idempotency_key)
    assert repeated.status_code == 200 and repeated.json() == response.json()
    assert decision.unresolved_intervention and not proposal.submitted

