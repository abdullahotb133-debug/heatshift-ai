"""Seeded, synthetic initial populations. No clock or task generation."""
import logging
from dataclasses import dataclass, field
from random import Random
from typing import TypeVar

from .enums import AcclimatizationStatus, AvailabilityStatus, WorkStatus
from .serialization import to_json
from .validation import enum_value, identifier, nonempty, string_set
from .workers import Worker

logger = logging.getLogger(__name__)
T = TypeVar('T')


@dataclass(frozen=True, kw_only=True)
class InitialWorkerStatus:
    """Eligibility is explicit; resting workers cannot accept work initially."""
    work_status: WorkStatus
    availability_status: AvailabilityStatus

    def __post_init__(self) -> None:
        for name, enum in (("work_status", WorkStatus), ("availability_status", AvailabilityStatus)):
            object.__setattr__(self, name, enum_value(getattr(self, name), enum, name))
        if self.work_status == WorkStatus.WORKING:
            raise ValueError("initial work_status cannot be working without a task assignment")
        if self.work_status == WorkStatus.RESTING and self.availability_status != AvailabilityStatus.UNAVAILABLE:
            raise ValueError("initial resting worker must be unavailable")


@dataclass(frozen=True, kw_only=True)
class WorkerConfig:
    count: int = 10
    work_zone_ids: tuple[str, ...] = ('ZONE_A', 'ZONE_B', 'ZONE_C')
    rest_zone_id: str = 'REST_ZONE'
    qualification_profiles: tuple[frozenset[str], ...] = (
        frozenset({'manual_handling'}),
        frozenset({'manual_handling', 'equipment_operation'}),
        frozenset({'manual_handling', 'rigging'}),
        frozenset({'inspection'}),
        frozenset({'inspection', 'equipment_operation'}),
    )
    acclimatization_statuses: tuple[AcclimatizationStatus, ...] = (
        AcclimatizationStatus.UNKNOWN,
        AcclimatizationStatus.NOT_ACCLIMATIZED,
        AcclimatizationStatus.PARTIALLY_ACCLIMATIZED,
        AcclimatizationStatus.ACCLIMATIZED,
    )
    clothing_profiles: tuple[str, ...] = (
        'standard_workwear', 'long_sleeve_workwear', 'coveralls',
    )
    initial_statuses: tuple[InitialWorkerStatus, ...] = (
        InitialWorkerStatus(work_status=WorkStatus.IDLE, availability_status=AvailabilityStatus.AVAILABLE),
        InitialWorkerStatus(work_status=WorkStatus.IDLE, availability_status=AvailabilityStatus.UNAVAILABLE),
        InitialWorkerStatus(work_status=WorkStatus.RESTING, availability_status=AvailabilityStatus.UNAVAILABLE),
    )

    def __post_init__(self) -> None:
        if type(self.count) is not int or self.count <= 0:
            raise ValueError('count must be a positive integer')
        for name in ('work_zone_ids', 'qualification_profiles', 'acclimatization_statuses',
                     'clothing_profiles', 'initial_statuses'):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not values:
                raise ValueError(f'{name} must be a non-empty tuple')
        identifier(self.rest_zone_id, 'rest_zone_id')
        for zone_id in self.work_zone_ids:
            identifier(zone_id, 'work_zone_ids')
        if len(set(self.work_zone_ids)) != len(self.work_zone_ids) or self.rest_zone_id in self.work_zone_ids:
            raise ValueError('work_zone_ids must be unique and distinct from rest_zone_id')
        for profile in self.qualification_profiles:
            string_set(profile, 'qualification_profiles')
        object.__setattr__(self, 'acclimatization_statuses', tuple(
            enum_value(status, AcclimatizationStatus, 'acclimatization_statuses')
            for status in self.acclimatization_statuses))
        for profile in self.clothing_profiles:
            nonempty(profile, 'clothing_profiles')
        if any(not isinstance(status, InitialWorkerStatus) for status in self.initial_statuses):
            raise ValueError('initial_statuses must contain InitialWorkerStatus models')


def _balanced_choices(options: tuple[T, ...], count: int, rng: Random) -> list[T]:
    """Shuffle each full pool before drawing to provide variation, not prevalence."""
    result: list[T] = []
    while len(result) < count:
        pool = list(options)
        rng.shuffle(pool)
        result.extend(pool[:count - len(result)])
    rng.shuffle(result)
    return result


@dataclass(frozen=True, kw_only=True)
class WorkerSimulator:
    """Generate once on construction; retrieval/export never draws randomness."""
    config: WorkerConfig = field(default_factory=WorkerConfig)
    seed: int = 0
    _workers: tuple[Worker, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.config, WorkerConfig):
            raise ValueError('config must be WorkerConfig')
        if type(self.seed) is not int:
            raise ValueError('seed must be an integer')
        rng = Random(self.seed)
        config = self.config
        qualifications = _balanced_choices(config.qualification_profiles, config.count, rng)
        acclimatization = _balanced_choices(config.acclimatization_statuses, config.count, rng)
        clothing = _balanced_choices(config.clothing_profiles, config.count, rng)
        statuses = _balanced_choices(config.initial_statuses, config.count, rng)
        workers = tuple(
            Worker(
                worker_id=f'W-{index + 1:02d}',
                display_name=f'Fictional Worker {index + 1:02d}',
                qualifications=qualifications[index],
                acclimatization_status=acclimatization[index],
                clothing_profile=clothing[index],
                current_zone_id=(config.rest_zone_id if status.work_status == WorkStatus.RESTING
                                 else rng.choice(config.work_zone_ids)),
                work_status=status.work_status,
                availability_status=status.availability_status,
            )
            for index, status in enumerate(statuses)
        )
        object.__setattr__(self, '_workers', workers)
        logger.debug('Generated %d fictional workers with seed %d', len(workers), self.seed)

    def get_worker(self, worker_id: str) -> Worker:
        identifier(worker_id, 'worker_id')
        for worker in self._workers:
            if worker.worker_id == worker_id:
                return worker
        raise KeyError(f'unknown worker_id: {worker_id}')

    def list_workers(self) -> tuple[Worker, ...]:
        return self._workers

    def export_json(self) -> str:
        return to_json({'data_origin': 'simulated', 'seed': self.seed,
                        'config': self.config, 'workers': self._workers})
