from dataclasses import dataclass, field
from .enums import AcclimatizationStatus, AvailabilityStatus, WorkStatus
from .validation import enum_value, identifier, nonempty, seconds, string_set


@dataclass(frozen=True, kw_only=True)
class Worker:
    """Synthetic worker; display_name must be fictional. No physiological model."""
    worker_id: str
    display_name: str
    current_zone_id: str
    qualifications: frozenset[str] = field(default_factory=frozenset)
    acclimatization_status: AcclimatizationStatus = AcclimatizationStatus.UNKNOWN
    clothing_profile: str = "unspecified"
    current_task_id: str | None = None
    work_status: WorkStatus = WorkStatus.IDLE
    availability_status: AvailabilityStatus = AvailabilityStatus.AVAILABLE
    exposure_elapsed_seconds: int = 0
    rest_elapsed_seconds: int = 0

    current_work_period_seconds: int = 0
    current_rest_period_seconds: int = 0

    @property
    def work_elapsed_seconds(self) -> int:
        """Cumulative working time equals tracked exposure time in this model."""
        return self.exposure_elapsed_seconds

    def __post_init__(self) -> None:
        identifier(self.worker_id, "worker_id")
        identifier(self.current_zone_id, "current_zone_id")
        if self.current_task_id is not None:
            identifier(self.current_task_id, "current_task_id")
        nonempty(self.display_name, "display_name")
        nonempty(self.clothing_profile, "clothing_profile")
        string_set(self.qualifications, "qualifications")
        for name, enum in (("acclimatization_status", AcclimatizationStatus),
                           ("work_status", WorkStatus), ("availability_status", AvailabilityStatus)):
            object.__setattr__(self, name, enum_value(getattr(self, name), enum, name))
        seconds(self.exposure_elapsed_seconds, "exposure_elapsed_seconds")
        seconds(self.rest_elapsed_seconds, "rest_elapsed_seconds")
        seconds(self.current_work_period_seconds, "current_work_period_seconds")
        seconds(self.current_rest_period_seconds, "current_rest_period_seconds")
        if self.current_work_period_seconds > self.exposure_elapsed_seconds:
            raise ValueError("current_work_period_seconds exceeds cumulative exposure")
        if self.current_rest_period_seconds > self.rest_elapsed_seconds:
            raise ValueError("current_rest_period_seconds exceeds cumulative rest")
        if self.work_status != WorkStatus.WORKING and self.current_work_period_seconds:
            raise ValueError("current_work_period_seconds requires working status")
        if self.work_status != WorkStatus.RESTING and self.current_rest_period_seconds:
            raise ValueError("current_rest_period_seconds requires resting status")
