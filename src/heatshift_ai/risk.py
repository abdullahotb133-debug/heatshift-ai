"""Deterministic NIOSH screening of simulated, continuous-work one-hour histories.

No HTTP, persistence, dispatch, clinical inference or implicit input substitution.
See COMPONENT_B_RISK_METHOD.md for applicability and sampling limitations.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .api_contracts import SimulationSnapshot, SIMULATION_EPOCH, simulation_timestamp
from .assignments import Assignment
from .enums import AcclimatizationStatus, WorkStatus
from .state import SimulationState
from .tasks import Task
from .time import SimulationTime
from .wbgt import EnvironmentalSample, calculate_wbgt
from .workers import Worker
from .zones import Zone

METHOD = "NIOSH 2016-106 continuous-work WBGT screening"
VERSION = "1.0.0"
SOURCE = "https://www.cdc.gov/niosh/docs/2016-106/pdfs/2016-106.pdf"
WINDOW_SECONDS = 3600
# Deliberately limited to the plotted metabolic-rate range, not extrapolated.
MIN_WATTS, MAX_WATTS = 116.0, 580.0
# Subset of the 2006 column reproduced in NIOSH Table 3-2 (printed p.19).
CLOTHING_ADJUSTMENTS = {
    "conventional_one_layer": 0.0,
    "cloth_coveralls": 0.0,
    "double_layer_cloth": 3.0,
}
LIMITATIONS = (
    "Simulation-based screening; not a medical diagnosis or authorization to work.",
    "Within-limit does not guarantee safety or validate synthetic inputs.",
    "One continuous task/zone for one hour only; no work/rest scheduling assessment.",
    "WBGT TWA uses trapezoidal interpolation between supplied tick samples; "
    "unobserved between-sample peaks are not excluded.",
    "Reference-person/population and clothing applicability are supplied scenario "
    "assumptions, not independently established worker health facts.",
)


class Outcome(StrEnum):
    WITHIN_APPLICABLE_LIMIT = "WITHIN_APPLICABLE_LIMIT"
    EXCEEDS_APPLICABLE_LIMIT = "EXCEEDS_APPLICABLE_LIMIT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


class RiskModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


Text = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]


class AssessmentBasis(RiskModel):
    """Explicit external evidence bound to the worker, task and clothing profile.

    Does not override measurements or change Component A. No defaults assert that
    generic clothing labels or illustrative workload categories are validated.
    """
    worker_id: Text
    task_id: Text
    clothing_profile: Text
    clothing_ensemble: Text
    clothing_basis: Text
    metabolic_rate_basis: Text
    population_basis: Text
    reference_person_applicable: bool = False


class Issue(RiskModel):
    code: str
    message: str


class RiskAssessment(RiskModel):
    assessment_id: str
    simulation_id: str | None = None
    instance_id: str | None = None
    state_version: int | None = None
    worker_id: str | None = None
    task_id: str | None = None
    zone_id: str | None = None
    assessment_timestamp: datetime | None = None
    time_basis: Literal["simulation_epoch"] = "simulation_epoch"
    simulation_based: bool | None = None
    outcome: Outcome
    methodology: str = METHOD
    methodology_version: str = VERSION
    source_url: str = SOURCE
    window_start_seconds: int | None = None
    window_end_seconds: int | None = None
    sample_count: int = 0
    wbgt_celsius: float | None = None
    wbgt_quality: str | None = None
    wbgt_source: str | None = None
    wbgt_method: str | None = None
    wbgt_twa_celsius: float | None = None
    effective_wbgt_twa_celsius: float | None = None
    metabolic_rate_watts: float | None = None
    workload_category: str | None = None
    clothing_profile: str | None = None
    clothing_adjustment_celsius: float | None = None
    acclimatization_status: str | None = None
    exposure_elapsed_seconds: int | None = None
    rest_elapsed_seconds: int | None = None
    current_work_period_seconds: int | None = None
    reference_limit_kind: Literal["RAL", "REL"] | None = None
    reference_limit_celsius: float | None = None
    evidence: AssessmentBasis | None = None
    issues: tuple[Issue, ...] = ()
    explanation: str
    limitations: tuple[str, ...] = LIMITATIONS


class _Problem(Exception):
    def __init__(self, code: str, message: str, *, unsupported: bool = False):
        self.issue = Issue(code=code, message=message)
        self.outcome = Outcome.NOT_ASSESSABLE if unsupported else Outcome.INSUFFICIENT_DATA


def _require(condition: bool, code: str, message: str, *, unsupported: bool = False) -> None:
    if not condition:
        raise _Problem(code, message, unsupported=unsupported)


def _snapshot(value: SimulationSnapshot | Mapping) -> SimulationSnapshot:
    # Round-trip even existing models: model_copy/model_construct can bypass validation.
    payload = value.model_dump_json() if isinstance(value, SimulationSnapshot) else json.dumps(value, allow_nan=False)
    snapshot = SimulationSnapshot.model_validate_json(payload, strict=True)
    # Reuse domain invariants; API projections alone do not enforce cross-entity rules.
    SimulationState(
        workers=tuple(Worker(**{**w.model_dump(), "qualifications": frozenset(w.qualifications)}) for w in snapshot.workers),
        tasks=tuple(Task(**{**t.model_dump(), "required_qualifications": frozenset(t.required_qualifications),
                           "allowed_zone_ids": frozenset(t.allowed_zone_ids)}) for t in snapshot.tasks),
        zones=tuple(Zone(zone_id=z.zone_id, kind=z.kind) for z in snapshot.zones),
        assignments=tuple(Assignment(**a.model_dump()) for a in snapshot.assignments),
        time=SimulationTime(elapsed_seconds=snapshot.elapsed_seconds, tick_seconds=snapshot.tick_seconds),
        random_seed=snapshot.random_seed,
    )
    _require(snapshot.simulation_epoch == SIMULATION_EPOCH and
             snapshot.simulated_at == simulation_timestamp(snapshot.elapsed_seconds),
             "timestamp_mismatch", "Snapshot time must match the Component A simulation epoch.")
    return snapshot


def _wbgt(snapshot: SimulationSnapshot, zone_id: str) -> float:
    observation = next(z.environment for z in snapshot.zones if z.zone_id == zone_id)
    return _validated_wbgt(observation, zone_id, snapshot.elapsed_seconds, snapshot.simulated_at)


def _validated_wbgt(observation, zone_id: str, elapsed_seconds: int, simulated_at: datetime) -> float:
    """Shared channel/provenance validation for observed and explicit forecast samples."""
    _require(observation.zone_id == zone_id, "zone_mismatch", "Observation zone does not match its container.")
    _require(observation.source.value == "simulated", "unsupported_provenance",
             "This version assesses synthetic Component A histories only.", unsupported=True)
    _require(observation.quality == "good" and observation.wbgt_celsius is not None,
             "unavailable_wbgt", "Missing, stale or invalid WBGT cannot establish a within-limit result.")
    _require(observation.elapsed_seconds == elapsed_seconds == observation.observed_at_seconds and
             observation.observed_at == simulated_at,
             "stale_observation", "Observation must be current in simulation time.")
    _require(observation.wbgt_unit == "degC" and observation.wbgt_kind == "calculated",
             "unsupported_wbgt", "Only calculated WBGT in degC is supported.", unsupported=True)
    conditions = {c.name: c for c in observation.conditions}
    _require(len(conditions) == len(observation.conditions), "duplicate_channel", "Environmental channel names must be unique.")
    required_units = {"air_temperature_c": "degC", "globe_temperature_c": "degC",
                      "natural_wet_bulb_c": "degC", "relative_humidity_percent": "percent",
                      "air_velocity_m_s": "m/s"}
    for name, unit in required_units.items():
        _require(name in conditions and conditions[name].unit == unit,
                 "missing_or_invalid_channel", f"Expected environmental channel {name} with unit {unit}.")
    solar = observation.source_metadata.get("solar_exposure")
    _require(solar in ("true", "false"), "missing_solar_basis", "Explicit solar-exposure metadata is required.")
    expected_metadata = {"quality": "good", "wbgt_kind": "calculated", "wbgt_input_source": "simulated",
                         "observed_at_seconds": str(elapsed_seconds)}
    _require(all(observation.source_metadata.get(k) == v for k, v in expected_metadata.items()),
             "provenance_mismatch", "Observation metadata disagrees with quality, provenance or time.")
    sample = EnvironmentalSample(zone_id=zone_id, elapsed_seconds=elapsed_seconds,
        observed_at_seconds=observation.observed_at_seconds, source=observation.source,
        solar_exposure=solar == "true", **{k: conditions[k].value for k in required_units})
    calculated = calculate_wbgt(sample)
    _require(calculated.value_c is not None and calculated.method == observation.method and
             math.isclose(calculated.value_c, observation.wbgt_celsius, rel_tol=0, abs_tol=1e-9),
             "wbgt_mismatch", "WBGT must agree with Component A's required channels and calculation method.")
    return observation.wbgt_celsius


def reference_limit_celsius(metabolic_rate_watts: float, acclimatization: AcclimatizationStatus) -> float:
    """NIOSH 2016-106 p.93 equations; restricted to figures' 116–580 W domain."""
    if isinstance(metabolic_rate_watts, bool) or not isinstance(metabolic_rate_watts, (int, float)):
        raise ValueError("metabolic rate must be a finite number in watts")
    if not math.isfinite(metabolic_rate_watts) or not MIN_WATTS <= metabolic_rate_watts <= MAX_WATTS:
        raise ValueError("metabolic rate outside supported 116–580 W range")
    if acclimatization == AcclimatizationStatus.ACCLIMATIZED:
        return 56.7 - 11.5 * math.log10(metabolic_rate_watts)
    if acclimatization == AcclimatizationStatus.NOT_ACCLIMATIZED:
        return 59.9 - 14.1 * math.log10(metabolic_rate_watts)
    raise ValueError("unknown or partial acclimatization is not assessable by this implementation")


def _hour_comparison(values, times, watts, ensemble, acclimatization) -> dict:
    """One scientific calculation shared by retrospective and prospective G2 paths."""
    twa = math.fsum((values[i-1]+values[i])/2 * (times[i]-times[i-1])
                    for i in range(1, len(values))) / WINDOW_SECONDS
    adjustment = CLOTHING_ADJUSTMENTS[ensemble]
    return dict(wbgt_twa_celsius=twa, effective_wbgt_twa_celsius=twa + adjustment,
                clothing_adjustment_celsius=adjustment,
                reference_limit_celsius=reference_limit_celsius(watts, acclimatization),
                reference_limit_kind="REL" if acclimatization == AcclimatizationStatus.ACCLIMATIZED else "RAL")


def assess_worker(snapshot: SimulationSnapshot | Mapping, worker_id: str, *,
                  history: Sequence[SimulationSnapshot | Mapping] = (),
                  basis: AssessmentBasis | Mapping | None = None) -> RiskAssessment:
    """Assess current worker using exactly the preceding hour plus current snapshot.

    History excludes the current snapshot, must be strictly ordered and contain
    no gap larger than the declared simulation tick. Missing inputs fail closed.
    """
    context: dict = {"worker_id": worker_id if isinstance(worker_id, str) else None}
    digest_input: dict = {"worker_id": context["worker_id"], "method_version": VERSION}
    issues: tuple[Issue, ...] = ()
    try:
        current = _snapshot(snapshot)
        digest_input["current"] = current.model_dump(mode="json")
        context.update(simulation_id=current.simulation_id, instance_id=current.instance_id,
                       state_version=current.state_version, assessment_timestamp=current.simulated_at,
                       window_end_seconds=current.elapsed_seconds)
        worker = next((w for w in current.workers if w.worker_id == worker_id), None)
        _require(worker is not None, "unknown_worker", "Worker is not present in this snapshot.")
        context.update(task_id=worker.current_task_id, zone_id=worker.current_zone_id,
            clothing_profile=worker.clothing_profile, acclimatization_status=worker.acclimatization_status.value,
            exposure_elapsed_seconds=worker.exposure_elapsed_seconds, rest_elapsed_seconds=worker.rest_elapsed_seconds,
            current_work_period_seconds=worker.current_work_period_seconds)
        obs = next(z.environment for z in current.zones if z.zone_id == worker.current_zone_id)
        context.update(wbgt_celsius=obs.wbgt_celsius, wbgt_quality=obs.quality,
                       wbgt_source=obs.source.value, wbgt_method=obs.method,
                       simulation_based=obs.source.value == "simulated")
        _wbgt(current, worker.current_zone_id)
        _require(worker.work_status == WorkStatus.WORKING and worker.current_task_id is not None,
                 "unsupported_work_state", "Only currently working, assigned workers are in scope.", unsupported=True)
        task = next(t for t in current.tasks if t.task_id == worker.current_task_id)
        context.update(workload_category=task.workload_category.value, metabolic_rate_watts=task.estimated_metabolic_rate_watts)
        _require(task.estimated_metabolic_rate_watts is not None, "missing_metabolic_rate",
                 "Task workload labels are not substituted for an evidenced numeric metabolic rate.")
        _require(MIN_WATTS <= task.estimated_metabolic_rate_watts <= MAX_WATTS,
                 "unsupported_metabolic_rate", "Metabolic rate is outside the implemented reference range.", unsupported=True)
        _require(basis is not None, "missing_assessment_basis", "Explicit workload, clothing and population evidence is required.")
        basis = AssessmentBasis.model_validate_json(basis.model_dump_json() if isinstance(basis, AssessmentBasis)
                                                   else json.dumps(basis, allow_nan=False), strict=True)
        context["evidence"] = basis
        digest_input["basis"] = basis.model_dump(mode="json")
        _require((basis.worker_id, basis.task_id, basis.clothing_profile) ==
                 (worker.worker_id, task.task_id, worker.clothing_profile),
                 "basis_mismatch", "Evidence must identify this worker, task and clothing profile.")
        _require(basis.reference_person_applicable, "unsupported_population",
                 "Reference-person applicability must be explicitly supported for this simulation.", unsupported=True)
        _require(basis.clothing_ensemble in CLOTHING_ADJUSTMENTS, "unsupported_clothing",
                 "Clothing is outside the implemented NIOSH adjustment subset.", unsupported=True)
        _require(worker.acclimatization_status != AcclimatizationStatus.UNKNOWN,
                 "unknown_acclimatization", "Acclimatization is unknown.")
        _require(worker.acclimatization_status in (AcclimatizationStatus.ACCLIMATIZED, AcclimatizationStatus.NOT_ACCLIMATIZED),
                 "unsupported_acclimatization", "Partial acclimatization is not interpolated.", unsupported=True)
        _require(isinstance(history, (tuple, list)) and 1 <= len(history) <= WINDOW_SECONDS,
                 "missing_history", "Provide an ordered, complete one-hour snapshot history excluding current.")
        _require(1 <= current.tick_seconds <= 10, "unsupported_sampling",
                 "This implementation requires a configured sampling tick of at most 10 seconds.", unsupported=True)
        samples = tuple(_snapshot(s) for s in history) + (current,)
        digest_input["history"] = [s.model_dump(mode="json") for s in samples[:-1]]
        context.update(window_start_seconds=samples[0].elapsed_seconds, sample_count=len(samples))
        _require(current.elapsed_seconds - samples[0].elapsed_seconds == WINDOW_SECONDS,
                 "incomplete_window", "Assessment requires exactly 3600 seconds; cumulative work counters are not a history.")
        _require(worker.current_work_period_seconds >= WINDOW_SECONDS,
                 "interrupted_work", "Current continuous work period is shorter than the assessment window.", unsupported=True)
        values = []
        first_worker = None
        for index, s in enumerate(samples):
            _require((s.simulation_id, s.instance_id, s.random_seed, s.tick_seconds) ==
                     (current.simulation_id, current.instance_id, current.random_seed, current.tick_seconds),
                     "mixed_history", "All samples must belong to one simulation instance and configuration.")
            _require(not s.paused, "paused_history", "Paused windows are outside the supported sampling contract.", unsupported=True)
            w = next((w for w in s.workers if w.worker_id == worker_id), None)
            _require(w is not None and (w.current_task_id, w.current_zone_id, w.work_status, w.clothing_profile,
                     w.acclimatization_status) == (worker.current_task_id, worker.current_zone_id,
                     WorkStatus.WORKING, worker.clothing_profile, worker.acclimatization_status),
                     "changing_exposure_context", "Task, zone, work state, clothing and acclimatization must be unchanged.", unsupported=True)
            t = next(t for t in s.tasks if t.task_id == w.current_task_id)
            _require((t.estimated_metabolic_rate_watts, t.workload_category) ==
                     (task.estimated_metabolic_rate_watts, task.workload_category),
                     "changing_workload", "Changing metabolic workload is outside this continuous-task scope.", unsupported=True)
            if first_worker is None:
                first_worker = w
            offset = s.elapsed_seconds - samples[0].elapsed_seconds
            _require(w.exposure_elapsed_seconds - first_worker.exposure_elapsed_seconds == offset and
                     w.current_work_period_seconds - first_worker.current_work_period_seconds == offset and
                     w.rest_elapsed_seconds == first_worker.rest_elapsed_seconds,
                     "counter_discontinuity", "Work/rest counters do not support continuous work throughout the window.")
            if index:
                previous = samples[index-1]
                _require(0 < s.elapsed_seconds - previous.elapsed_seconds <= current.tick_seconds and
                         s.state_version > previous.state_version,
                         "history_gap_or_order", "History must advance in time and version with no missing tick interval.")
            _require(not any(e.worker_id == worker_id and samples[0].elapsed_seconds < e.elapsed_seconds <= current.elapsed_seconds
                             for e in s.events), "intervening_transition",
                     "Worker transitions inside the hour require an unsupported multi-activity assessment.", unsupported=True)
            values.append(_wbgt(s, w.current_zone_id))
        context.update(_hour_comparison(values, [s.elapsed_seconds for s in samples],
            task.estimated_metabolic_rate_watts, basis.clothing_ensemble, worker.acclimatization_status))
        limit, effective = context['reference_limit_celsius'], context['effective_wbgt_twa_celsius']
        outcome = Outcome.EXCEEDS_APPLICABLE_LIMIT if effective > limit else Outcome.WITHIN_APPLICABLE_LIMIT
        explanation = f"One-hour effective WBGT {effective:.6f} degC {'exceeds' if effective > limit else 'does not exceed'} " \
                      f"the applicable {context['reference_limit_kind']} {limit:.6f} degC; simulation screening only."
    except _Problem as exc:
        outcome, issues, explanation = exc.outcome, (exc.issue,), exc.issue.message
    except (ValidationError, ValueError, TypeError, OverflowError):
        outcome = Outcome.INSUFFICIENT_DATA
        issues = (Issue(code="invalid_input", message="Input violates the existing snapshot/domain or assessment evidence contract."),)
        explanation = issues[0].message
    digest_input["issues"] = [i.model_dump() for i in issues]
    fingerprint = sha256(json.dumps(digest_input, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return RiskAssessment(assessment_id="risk-" + fingerprint, outcome=outcome, issues=issues,
                          explanation=explanation, **context)
