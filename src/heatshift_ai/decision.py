"""Conservative G3 decisions with optional explicit G2 assignment forecasts.

Evaluates real eligibility, verifies G2 evidence and describes rejected alternatives.
Never executes commands or upgrades historical screening into destination clearance.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from .api_contracts import (CommandRequest, SimulationCommand, SimulationSnapshot,
                            SIMULATION_EPOCH, simulation_timestamp)
from .assignments import Assignment
from .enums import AvailabilityStatus, WorkStatus, ZoneKind
from .risk import AssessmentBasis, Outcome, RiskAssessment, assess_worker
from .prospective import ProspectivePlan, ProspectiveAssessment, assess_proposed_assignment
from .state import SimulationState
from .tasks import Task
from .time import SimulationTime
from .workers import Worker
from .zones import Zone

RULESET_VERSION = "0.2.0"
LIMITATIONS = (
    "Simulated decision support only; no command has been submitted or executed.",
    "Prospective comparisons require explicit simulated forecasts; no rest, recovery or individual safety clearance is provided.",
    "A selected proposal remains conditional on human review and resolution of the affected worker's residual exposure.",
    "No feasible action is not permission to continue hazardous work; immediate supervisor review is required.",
    "An optional stop-work draft does not move the worker, prove recovery, or make the zone safe.",
)


class DecisionOutcome(StrEnum):
    ACTION_PROPOSED = "ACTION_PROPOSED"
    NO_FEASIBLE_ACTION = "NO_FEASIBLE_ACTION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NO_INTERVENTION_REQUIRED = "NO_INTERVENTION_REQUIRED"


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class AssessmentEvidence(Model):
    """Original G2 result and inputs, permitting independent recomputation."""
    assessment: RiskAssessment
    history: tuple[SimulationSnapshot, ...] = ()
    basis: AssessmentBasis | None = None


class Constraint(Model):
    code: str
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    reason: str


class Alternative(Model):
    kind: Literal["replacement", "rest", "relocation", "stop_work"]
    worker_id: str
    task_id: str | None = None
    destination_zone_id: str
    mechanical_eligibility: bool
    feasibility: Literal["REJECTED", "UNVERIFIED", "FEASIBLE_FOR_REVIEW"]
    constraints: tuple[Constraint, ...]
    assessment_reference: str | None = None
    prospective_assessment: ProspectiveAssessment | None = None

    @property
    def rejection_reasons(self) -> tuple[str, ...]:
        return tuple(c.code for c in self.constraints if c.status != "PASS")


class CommandProposal(Model):
    """A review-only draft, never a claim of execution or thermal feasibility."""
    body: CommandRequest
    idempotency_key: str
    review_status: Literal["MANUAL_REVIEW_REQUIRED"] = "MANUAL_REVIEW_REQUIRED"
    thermal_safety_verified: Literal[False] = False
    submitted: Literal[False] = False
    expected_effect: str
    proposed_replacement_worker_id: str | None = None
    proposed_task_id: str | None = None
    proposed_destination_zone_id: str | None = None
    prospective_assessment_reference: str | None = None
    planned_duration_seconds: int | None = None


class Decision(Model):
    decision_id: str
    outcome: DecisionOutcome
    simulation_id: str | None = None
    instance_id: str | None = None
    input_state_version: int | None = None
    assessment_reference: str | None = None
    affected_worker_id: str | None = None
    current_task_id: str | None = None
    current_zone_id: str | None = None
    timestamp: datetime | None = None
    time_basis: Literal["simulation_epoch"] = "simulation_epoch"
    simulation_based: bool | None = None
    intervention_required: bool | None = None
    unresolved_intervention: bool = False
    requires_supervisor_review: bool = True
    constraints: tuple[Constraint, ...] = ()
    alternatives: tuple[Alternative, ...] = ()
    mechanically_eligible_replacement_ids: tuple[str, ...] = ()
    verified_safe_replacement_ids: tuple[str, ...] = ()
    prospectively_acceptable_replacement_ids: tuple[str, ...] = ()
    selected_proposal: CommandProposal | None = None
    manual_stop_work_proposal: CommandProposal | None = None
    explanation: str
    ruleset_version: str = RULESET_VERSION
    limitations: tuple[str, ...] = LIMITATIONS


def _parse(model: type[BaseModel], value):
    data = value.model_dump_json() if isinstance(value, BaseModel) else json.dumps(value, allow_nan=False)
    return model.model_validate_json(data, strict=True)


def _snapshot(value) -> SimulationSnapshot:
    snapshot = _parse(SimulationSnapshot, value)
    # These existing domain validators enforce reciprocal assignments/qualifications.
    SimulationState(
        workers=tuple(Worker(**{**w.model_dump(), "qualifications": frozenset(w.qualifications)}) for w in snapshot.workers),
        tasks=tuple(Task(**{**t.model_dump(), "required_qualifications": frozenset(t.required_qualifications),
                           "allowed_zone_ids": frozenset(t.allowed_zone_ids)}) for t in snapshot.tasks),
        zones=tuple(Zone(zone_id=z.zone_id, kind=z.kind) for z in snapshot.zones),
        assignments=tuple(Assignment(**a.model_dump()) for a in snapshot.assignments),
        time=SimulationTime(elapsed_seconds=snapshot.elapsed_seconds, tick_seconds=snapshot.tick_seconds),
        random_seed=snapshot.random_seed,
    )
    if snapshot.simulation_epoch != SIMULATION_EPOCH or snapshot.simulated_at != simulation_timestamp(snapshot.elapsed_seconds):
        raise ValueError("inconsistent simulation timestamp")
    return snapshot


def _check(code: str, passed: bool | None, reason: str) -> Constraint:
    return Constraint(code=code, status="UNKNOWN" if passed is None else "PASS" if passed else "FAIL", reason=reason)


def _environment(snapshot: SimulationSnapshot, zone_id: str, prefix: str) -> Constraint:
    observation = next(z.environment for z in snapshot.zones if z.zone_id == zone_id)
    available = (observation.zone_id == zone_id and observation.quality == "good" and
        observation.wbgt_celsius is not None and observation.source.value == "simulated" and
        observation.wbgt_unit == "degC" and observation.wbgt_kind == "calculated" and
        observation.elapsed_seconds == observation.observed_at_seconds == snapshot.elapsed_seconds and
        observation.observed_at == snapshot.simulated_at)
    return _check(prefix + "_observation_available", available,
                  "Checks observation availability/time/provenance only; does not establish safe exposure.")


def _verify(snapshot: SimulationSnapshot, worker_id: str, supplied) -> tuple[Constraint, RiskAssessment | None]:
    if supplied is None:
        return _check("assessment_evidence", None, "G2 result and original inputs were not supplied."), None
    try:
        evidence = _parse(AssessmentEvidence, supplied)
        risk = evidence.assessment
        worker = next(w for w in snapshot.workers if w.worker_id == worker_id)
        identity = (risk.simulation_id, risk.instance_id, risk.state_version, risk.worker_id,
                    risk.task_id, risk.zone_id, risk.assessment_timestamp)
        expected = (snapshot.simulation_id, snapshot.instance_id, snapshot.state_version, worker_id,
                    worker.current_task_id, worker.current_zone_id, snapshot.simulated_at)
        if identity != expected:
            return _check("assessment_context", False, "Assessment does not match current instance/version/worker/task/zone/time."), None
        recomputed = assess_worker(snapshot, worker_id, history=evidence.history, basis=evidence.basis)
        if recomputed != risk:
            return _check("assessment_integrity", False, "G2 result does not reproduce from the supplied original inputs."), None
        return _check("assessment_integrity", True, "G2 result independently reproduced without changing inputs."), risk
    except (ValidationError, ValueError, TypeError, OverflowError, StopIteration):
        return _check("invalid_assessment_evidence", False, "G2 evidence violates its contract."), None


def _alternative(kind: str, worker_id: str, task_id: str | None, zone_id: str,
                 mechanical: tuple[Constraint, ...], other: tuple[Constraint, ...],
                 assessment_reference: str | None = None) -> Alternative:
    checks = mechanical + other
    return Alternative(kind=kind, worker_id=worker_id, task_id=task_id, destination_zone_id=zone_id,
        mechanical_eligibility=all(c.status == "PASS" for c in mechanical),
        feasibility="REJECTED" if any(c.status == "FAIL" for c in checks) else "UNVERIFIED",
        constraints=checks, assessment_reference=assessment_reference)


def decide(snapshot: SimulationSnapshot | Mapping, worker_id: str, *,
           evidence: AssessmentEvidence | Mapping | None,
           candidate_evidence: Mapping[str, AssessmentEvidence | Mapping] | None = None,
           prospective_plans: tuple[ProspectivePlan | Mapping, ...] | list | None = None) -> Decision:
    """Recompute G2, enumerate A constraints and fail closed on prospective evidence.

    Optional forecasts permit candidate selection for human review. The affected
    worker's intervention remains unresolved until supervised action is confirmed.
    """
    context: dict = {"affected_worker_id": worker_id if isinstance(worker_id, str) else None}
    seed: dict = {"ruleset_version": RULESET_VERSION, "worker_id": context["affected_worker_id"]}

    def finish(outcome: DecisionOutcome, explanation: str, **extra) -> Decision:
        payload = dict(outcome=outcome, explanation=explanation, **context, **extra)
        raw = json.dumps({"inputs": seed, "result": payload}, sort_keys=True, separators=(",", ":"),
                         default=lambda x: x.model_dump(mode="json") if isinstance(x, BaseModel) else str(x), allow_nan=False)
        return Decision(decision_id="decision-" + sha256(raw.encode()).hexdigest(), **payload)

    try:
        state = _snapshot(snapshot)
        seed["snapshot"] = state.model_dump(mode="json")
        context.update(simulation_id=state.simulation_id, instance_id=state.instance_id,
                       input_state_version=state.state_version, timestamp=state.simulated_at)
        worker = next((w for w in state.workers if w.worker_id == worker_id), None)
        if worker is None:
            return finish(DecisionOutcome.INSUFFICIENT_DATA, "Requested worker is absent.",
                          constraints=(_check("worker_exists", False, "Unknown worker identifier."),))
        context.update(current_task_id=worker.current_task_id, current_zone_id=worker.current_zone_id)
        observation = next(z.environment for z in state.zones if z.zone_id == worker.current_zone_id)
        context["simulation_based"] = observation.source.value == "simulated"
        verification, risk = _verify(state, worker_id, evidence)
        if risk is None:
            return finish(DecisionOutcome.INSUFFICIENT_DATA, "Current, reproducible G2 evidence is required.",
                          constraints=(verification,))
        context["assessment_reference"] = risk.assessment_id
        if risk.outcome in (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE):
            return finish(DecisionOutcome.INSUFFICIENT_DATA, "G2 cannot establish an applicable exposure comparison; do not interpret this as safe.",
                          constraints=(verification, _check("assessable_exposure", None, risk.explanation)))
        if risk.outcome == Outcome.WITHIN_APPLICABLE_LIMIT:
            return finish(DecisionOutcome.NO_INTERVENTION_REQUIRED,
                          "No intervention is triggered by this verified historical G2 result; this is not clearance for future work.",
                          intervention_required=False, requires_supervisor_review=False, constraints=(verification,))
        context.update(intervention_required=True, unresolved_intervention=True)
        if worker.work_status != WorkStatus.WORKING or worker.current_task_id is None:
            return finish(DecisionOutcome.INSUFFICIENT_DATA, "An active assignment is required to evaluate intervention alternatives.",
                          constraints=(verification, _check("active_assignment", False, "Worker is not currently assigned and working.")))
        task = next(t for t in state.tasks if t.task_id == worker.current_task_id)
        supplied = {} if candidate_evidence is None else candidate_evidence
        if not isinstance(supplied, Mapping) or any(not isinstance(k, str) for k in supplied):
            raise ValueError("candidate evidence must be indexed by worker identifier")
        unknown = set(supplied) - {w.worker_id for w in state.workers}
        if unknown:
            raise ValueError("candidate evidence contains an unknown worker")
        plans = {}
        if prospective_plans is not None:
            if not isinstance(prospective_plans, (tuple, list)):
                raise ValueError('prospective plans must be an explicit list')
            for value in prospective_plans:
                plan = _parse(ProspectivePlan, value)
                key = (plan.worker_id, plan.destination_zone_id)
                if (key in plans or plan.worker_id == worker_id or plan.worker_id not in {w.worker_id for w in state.workers}
                    or plan.task_id != task.task_id or plan.destination_zone_id not in {z.zone_id for z in state.zones}):
                    raise ValueError('duplicate or incompatible prospective plan')
                plans[key] = plan
        alternatives = []
        eligible = set()
        feasible = []
        incomplete_eligible = False
        prospective = _check("prospective_exposure_supported", None,
            "An explicit G2 prospective plan is required for replacement; historical results do not establish future or rest clearance.")
        affected_protection = _check("affected_worker_protection", None,
            "Replacing the assignee alone does not establish a safe state for the affected worker.")
        for candidate in sorted(state.workers, key=lambda w: w.worker_id):
            if candidate.worker_id == worker_id:
                continue
            common = (
                _check("qualifications", set(task.required_qualifications) <= set(candidate.qualifications), "All required task qualifications must already exist."),
                _check("availability", candidate.availability_status == AvailabilityStatus.AVAILABLE, "Replacement must be available."),
                _check("idle_not_resting", candidate.work_status == WorkStatus.IDLE, "Working/resting workers are not idle replacements."),
                _check("no_existing_assignment", candidate.current_task_id is None and
                       not any(a.worker_id == candidate.worker_id for a in state.assignments), "No existing assignment may be displaced."),
            )
            verification_candidate, candidate_risk = _verify(state, candidate.worker_id, supplied.get(candidate.worker_id))
            risk_check = _check("candidate_current_exposure", None if candidate_risk is None or candidate_risk.outcome in
                (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE) else candidate_risk.outcome == Outcome.WITHIN_APPLICABLE_LIMIT,
                "Requires an applicable, reproducible current assessment; unsupported or missing assessments are not safe.")
            for zone in sorted(state.zones, key=lambda z: z.zone_id):
                mechanical = common + (
                    _check("work_zone", zone.kind == ZoneKind.WORK, "Task destination must be a work zone."),
                    _check("allowed_task_zone", zone.zone_id in task.allowed_zone_ids, "Task must explicitly permit the destination."),
                )
                if prospective_plans is None:
                    alternative = _alternative("replacement", candidate.worker_id, task.task_id, zone.zone_id, mechanical,
                        (_environment(state, candidate.current_zone_id, "candidate_current"),
                         _environment(state, zone.zone_id, "destination"), verification_candidate, risk_check,
                         prospective, affected_protection), candidate_risk.assessment_id if candidate_risk else None)
                else:
                    forecast = assess_proposed_assignment(state, candidate.worker_id, task.task_id, zone.zone_id,
                        plan=plans.get((candidate.worker_id, zone.zone_id)))
                    acceptable = (None if forecast.outcome in (Outcome.INSUFFICIENT_DATA, Outcome.NOT_ASSESSABLE)
                                  else forecast.outcome == Outcome.WITHIN_APPLICABLE_LIMIT)
                    extra = (verification_candidate, risk_check) if candidate.worker_id in supplied else ()
                    checks = (_environment(state, candidate.current_zone_id, 'candidate_current'),
                        _environment(state, zone.zone_id, 'destination'),
                        _check('prospective_exposure', acceptable, forecast.explanation),
                        _check('affected_assignment_stopped', True,
                            'Proposal stops the affected task and marks worker unavailable; residual exposure still requires human intervention.')) + extra
                    alternative = _alternative('replacement', candidate.worker_id, task.task_id, zone.zone_id,
                        mechanical, checks, forecast.assessment_id)
                    alternative = alternative.model_copy(update={'prospective_assessment': forecast})
                    if all(c.status == 'PASS' for c in alternative.constraints):
                        alternative = alternative.model_copy(update={'feasibility': 'FEASIBLE_FOR_REVIEW'})
                        feasible.append(alternative)
                    if alternative.mechanical_eligibility and acceptable is None:
                        incomplete_eligible = True
                alternatives.append(alternative)
                if alternative.mechanical_eligibility:
                    eligible.add(candidate.worker_id)
        for zone in sorted(state.zones, key=lambda z: z.zone_id):
            if zone.zone_id == worker.current_zone_id:
                continue
            if zone.kind == ZoneKind.REST:
                alternatives.append(_alternative("rest", worker_id, task.task_id, zone.zone_id,
                    (_check("rest_zone", True, "A start_rest releases the assignment and requires a rest zone."),),
                    (_environment(state, zone.zone_id, "destination"), prospective)))
            else:
                alternatives.append(_alternative("relocation", worker_id, task.task_id, zone.zone_id,
                    (_check("allowed_task_zone", zone.zone_id in task.allowed_zone_ids, "Existing task must allow the new zone."),),
                    (_environment(state, zone.zone_id, "destination"), prospective)))
        alternatives.append(_alternative("stop_work", worker_id, task.task_id, worker.current_zone_id,
            (_check("currently_working", True, "A stop_work releases the task without changing the worker's zone."),),
            (_check("heat_resolution", None, "Stopping task execution does not prove that continued exposure in this zone is acceptable."),)))
        reason = f"G3 review-only draft: G2 {risk.assessment_id} exceeds its applicable limit; unresolved exposure requires supervisor review."
        body = CommandRequest(schema_version="1.0", simulation_id=state.simulation_id, instance_id=state.instance_id,
            expected_state_version=state.state_version,
            commands=[SimulationCommand(action="stop_work", worker_id=worker_id, reason=reason)])
        key = "g3-" + sha256(body.model_dump_json().encode()).hexdigest()
        draft = CommandProposal(body=body, idempotency_key=key,
            expected_effect="If separately approved and accepted by A: task becomes pending and worker idle in the same zone. No cooling, recovery or safe-return claim.")
        if feasible:
            # Largest distance below the applicable limit, then stable IDs. This is
            # a screening comparison, not a physiological risk/benefit score.
            selected = min(feasible, key=lambda a: (
                a.prospective_assessment.effective_wbgt_twa_celsius - a.prospective_assessment.reference_limit_celsius,
                a.worker_id, a.destination_zone_id))
            forecast = selected.prospective_assessment
            reason = f'G3 human-review proposal based on {risk.assessment_id} and {forecast.assessment_id}'
            replacement_body = CommandRequest(schema_version='1.0', simulation_id=state.simulation_id,
                instance_id=state.instance_id, expected_state_version=state.state_version, commands=[
                    SimulationCommand(action='stop_work', worker_id=worker_id, reason=reason),
                    SimulationCommand(action='mark_unavailable', worker_id=worker_id, reason=reason),
                    SimulationCommand(action='assign_task', worker_id=selected.worker_id, task_id=task.task_id,
                                      zone_id=selected.destination_zone_id, reason=reason),
                    SimulationCommand(action='start_work', worker_id=selected.worker_id, reason=reason)])
            proposal = CommandProposal(body=replacement_body,
                idempotency_key='g3-' + sha256(replacement_body.model_dump_json().encode()).hexdigest(),
                proposed_replacement_worker_id=selected.worker_id, proposed_task_id=task.task_id,
                proposed_destination_zone_id=selected.destination_zone_id,
                prospective_assessment_reference=forecast.assessment_id, planned_duration_seconds=forecast.duration_seconds,
                expected_effect='After explicit human review and A acceptance: stop affected task, mark affected worker unavailable, start replacement. Affected worker remains in the same zone; residual exposure/recovery requires separate supervised action. A does not auto-stop at the forecast horizon.')
            return finish(DecisionOutcome.ACTION_PROPOSED,
                'Replacement passes hard constraints and explicit prospective G2 screening. Conditional proposal only: human review and affected-worker protection remain required; no command executed.',
                constraints=(verification,), alternatives=tuple(alternatives),
                mechanically_eligible_replacement_ids=tuple(sorted(eligible)),
                prospectively_acceptable_replacement_ids=tuple(sorted({a.worker_id for a in feasible})),
                selected_proposal=proposal, manual_stop_work_proposal=draft)
        if prospective_plans is not None and incomplete_eligible:
            return finish(DecisionOutcome.INSUFFICIENT_DATA,
                'Intervention remains required; missing or unsupported prospective evidence prevents candidate approval.',
                constraints=(verification,), alternatives=tuple(alternatives),
                mechanically_eligible_replacement_ids=tuple(sorted(eligible)), manual_stop_work_proposal=draft)
        return finish(DecisionOutcome.NO_FEASIBLE_ACTION,
            "Intervention is required, but no alternative has verified prospective exposure evidence. Do not continue hazardous work because a replacement is missing; escalate for immediate supervised action.",
            constraints=(verification, prospective), alternatives=tuple(alternatives),
            mechanically_eligible_replacement_ids=tuple(sorted(eligible)), manual_stop_work_proposal=draft)
    except (ValidationError, ValueError, TypeError, OverflowError):
        return finish(DecisionOutcome.INSUFFICIENT_DATA, "Invalid snapshot or decision evidence; no proposal is approved.",
                      constraints=(_check("valid_input", False, "Existing API/domain and evidence contracts must be satisfied."),))
