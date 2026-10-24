"""G2 extension: explicit simulated one-hour assignment forecasts, never observed history.

Shares G2's validation and scientific calculation; adds no thresholds or rest policy.
"""
from collections.abc import Mapping
from hashlib import sha256
import json
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from .api_contracts import EnvironmentalObservation, SimulationSnapshot, simulation_timestamp
from .enums import AcclimatizationStatus
from .risk import (AssessmentBasis, RiskModel, RiskAssessment, Outcome, Issue, Text,
                   _snapshot, _wbgt, _validated_wbgt, _require, _Problem, _hour_comparison,
                   CLOTHING_ADJUSTMENTS, MIN_WATTS, MAX_WATTS, WINDOW_SECONDS)

PROSPECTIVE_VERSION = '1.0.0'
LIMITATIONS = (
    'Explicit simulated forecast; future samples are assumptions, not observed measurements.',
    'One continuous task/zone for exactly one hour; no mixed activity, travel or work/rest prescription.',
    'Uses G2 NIOSH equations and clothing subset; within-limit is not individual safety or authorization.',
    'Prior heat strain and reference-person fitness must be explicitly supported by the scenario owner; not inferred from idle status or counters.',
    'Forecast interpolation cannot exclude unobserved peaks; changed conditions require reassessment.',
    'No recovery, medical fitness, affected-worker disposition or real-world forecast accuracy is established.',
)


def snapshot_fingerprint(snapshot: SimulationSnapshot | Mapping) -> str:
    state = _snapshot(snapshot)
    return sha256(json.dumps(state.model_dump(mode='json'), sort_keys=True,
                             separators=(',', ':')).encode()).hexdigest()


class ProspectivePlan(RiskModel):
    origin_fingerprint: Text
    worker_id: Text
    task_id: Text
    destination_zone_id: Text
    duration_seconds: Annotated[int, Field(strict=True, gt=0)]
    forecast_source: Literal['explicit_simulation_scenario']
    forecast_basis: Text
    prior_exposure_basis: Text
    prior_heat_strain_excluded: bool = False
    basis: AssessmentBasis
    observations: Annotated[tuple[EnvironmentalObservation, ...], Field(min_length=2, max_length=3601)]


class ProspectiveAssessment(RiskAssessment):
    evaluation_mode: Literal['prospective_simulation'] = 'prospective_simulation'
    prospective_version: str = PROSPECTIVE_VERSION
    origin_fingerprint: str | None = None
    duration_seconds: int | None = None
    forecast_source: str | None = None
    forecast_basis: str | None = None
    prior_exposure_basis: str | None = None
    prior_heat_strain_excluded: bool = False
    limitations: tuple[str, ...] = LIMITATIONS


def assess_proposed_assignment(snapshot: SimulationSnapshot | Mapping, worker_id: str,
                               task_id: str, zone_id: str, *,
                               plan: ProspectivePlan | Mapping | None) -> ProspectiveAssessment:
    """Evaluate a supplied forecast against the proposed task and actual worker factors.

    No qualification, fitness, weather or workload defaults are synthesized here.
    Mechanical command eligibility remains independently enforced by G3 and A.
    """
    context = {}
    digest = {'version': PROSPECTIVE_VERSION}
    issues = ()
    try:
        _require(all(isinstance(value, str) for value in (worker_id, task_id, zone_id)),
                 'invalid_identifier', 'Worker, task and zone identifiers must be strings.')
        current = _snapshot(snapshot)
        _require(not current.paused, 'paused_projection',
                 'A paused simulation cannot begin the planned exposure period.', unsupported=True)
        origin = snapshot_fingerprint(current)
        context.update(simulation_id=current.simulation_id, instance_id=current.instance_id,
            state_version=current.state_version, assessment_timestamp=current.simulated_at,
            worker_id=worker_id, task_id=task_id, zone_id=zone_id, origin_fingerprint=origin,
            window_start_seconds=current.elapsed_seconds)
        digest.update(origin=origin, worker=worker_id, task=task_id, zone=zone_id)
        worker = next((w for w in current.workers if w.worker_id == worker_id), None)
        task = next((t for t in current.tasks if t.task_id == task_id), None)
        zone = next((z for z in current.zones if z.zone_id == zone_id), None)
        _require(worker is not None and task is not None and zone is not None, 'unknown_entity',
                 'Worker, proposed task and destination must exist in the current state.')
        _wbgt(current, worker.current_zone_id)
        _wbgt(current, zone_id)
        context.update(simulation_based=True, wbgt_celsius=zone.environment.wbgt_celsius,
            wbgt_quality=zone.environment.quality, wbgt_source=zone.environment.source.value,
            wbgt_method=zone.environment.method, metabolic_rate_watts=task.estimated_metabolic_rate_watts,
            workload_category=task.workload_category.value, clothing_profile=worker.clothing_profile,
            acclimatization_status=worker.acclimatization_status.value,
            exposure_elapsed_seconds=worker.exposure_elapsed_seconds, rest_elapsed_seconds=worker.rest_elapsed_seconds,
            current_work_period_seconds=worker.current_work_period_seconds)
        _require(plan is not None, 'missing_prospective_plan', 'Explicit destination forecast and scenario evidence are required.')
        plan = ProspectivePlan.model_validate_json(plan.model_dump_json() if isinstance(plan, ProspectivePlan)
                                                   else json.dumps(plan, allow_nan=False), strict=True)
        digest['plan'] = plan.model_dump(mode='json')
        context.update(duration_seconds=plan.duration_seconds, forecast_source=plan.forecast_source,
            forecast_basis=plan.forecast_basis, prior_exposure_basis=plan.prior_exposure_basis,
            prior_heat_strain_excluded=plan.prior_heat_strain_excluded, evidence=plan.basis)
        _require((plan.origin_fingerprint, plan.worker_id, plan.task_id, plan.destination_zone_id) ==
                 (origin, worker_id, task_id, zone_id), 'prospective_context_mismatch',
                 'Plan must match the exact current snapshot, worker, proposed task and destination.')
        _require(plan.duration_seconds == WINDOW_SECONDS, 'unsupported_duration',
                 'Only an explicit continuous 3600-second planned assignment is supported.', unsupported=True)
        _require(plan.prior_heat_strain_excluded, 'prior_exposure_unknown',
                 'Idle status and elapsed-work counters cannot establish absence of prior heat strain.')
        _require(task.estimated_metabolic_rate_watts is not None, 'missing_metabolic_rate',
                 'Proposed task requires an explicit numeric rate; current activity is not a substitute.')
        _require(MIN_WATTS <= task.estimated_metabolic_rate_watts <= MAX_WATTS, 'unsupported_metabolic_rate',
                 'Proposed rate is outside G2 reference range.', unsupported=True)
        basis = plan.basis
        _require((basis.worker_id, basis.task_id, basis.clothing_profile) ==
                 (worker_id, task_id, worker.clothing_profile), 'basis_mismatch',
                 'Evidence must bind actual worker clothing and proposed task.')
        _require(basis.reference_person_applicable, 'unsupported_population',
                 'Explicit reference-person scenario applicability is required.', unsupported=True)
        _require(basis.clothing_ensemble in CLOTHING_ADJUSTMENTS, 'unsupported_clothing',
                 'Clothing is outside the G2 supported subset.', unsupported=True)
        _require(worker.acclimatization_status != AcclimatizationStatus.UNKNOWN,
                 'unknown_acclimatization', 'Acclimatization is unknown.')
        _require(worker.acclimatization_status in (AcclimatizationStatus.ACCLIMATIZED, AcclimatizationStatus.NOT_ACCLIMATIZED),
                 'unsupported_acclimatization', 'Partial acclimatization is not interpolated.', unsupported=True)
        _require(1 <= current.tick_seconds <= 10, 'unsupported_sampling', 'G2 sampling contract requires 1–10 seconds.', unsupported=True)
        observations = plan.observations
        _require(observations[0] == zone.environment, 'forecast_origin_mismatch',
                 'Forecast must begin with the actual destination observation, including metadata.')
        _require(observations[-1].elapsed_seconds == current.elapsed_seconds + WINDOW_SECONDS,
                 'incomplete_forecast', 'Forecast must cover the entire proposed hour.')
        values, times = [], []
        for observation in observations:
            t = observation.elapsed_seconds
            if times:
                _require(0 < t - times[-1] <= current.tick_seconds, 'forecast_gap_or_order',
                         'No duplicate, reordered or missing forecast tick is allowed.')
            values.append(_validated_wbgt(observation, zone_id, t, simulation_timestamp(t)))
            times.append(t)
        context.update(window_end_seconds=times[-1], sample_count=len(times),
            **_hour_comparison(values, times, task.estimated_metabolic_rate_watts,
                               basis.clothing_ensemble, worker.acclimatization_status))
        exceeds = context['effective_wbgt_twa_celsius'] > context['reference_limit_celsius']
        outcome = Outcome.EXCEEDS_APPLICABLE_LIMIT if exceeds else Outcome.WITHIN_APPLICABLE_LIMIT
        explanation = ('Proposed one-hour assignment ' + ('exceeds' if exceeds else 'does not exceed') +
            ' the applicable G2 NIOSH limit under the explicit simulated forecast; human review remains required.')
    except _Problem as exc:
        outcome, issues, explanation = exc.outcome, (exc.issue,), exc.issue.message
    except (ValidationError, ValueError, TypeError, OverflowError):
        outcome = Outcome.INSUFFICIENT_DATA
        issues = (Issue(code='invalid_prospective_input', message='Prospective input violates existing data or evidence contracts.'),)
        explanation = issues[0].message
    digest['issues'] = [i.model_dump() for i in issues]
    identity = sha256(json.dumps(digest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return ProspectiveAssessment(assessment_id='prospective-' + identity, outcome=outcome,
                                 issues=issues, explanation=explanation, **context)
