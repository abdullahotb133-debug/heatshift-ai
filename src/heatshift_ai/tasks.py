from dataclasses import dataclass, field
from .enums import TaskStatus, WorkloadCategory
from .validation import enum_value, finite_number, identifier, nonempty, string_set


@dataclass(frozen=True, kw_only=True)
class Task:
    task_id: str
    task_name: str
    workload_category: WorkloadCategory
    allowed_zone_ids: frozenset[str]
    estimated_metabolic_rate_watts: float | None = None
    required_qualifications: frozenset[str] = field(default_factory=frozenset)
    task_status: TaskStatus = TaskStatus.PENDING
    assigned_worker_id: str | None = None

    def __post_init__(self) -> None:
        identifier(self.task_id, "task_id")
        nonempty(self.task_name, "task_name")
        object.__setattr__(self, "workload_category", enum_value(self.workload_category, WorkloadCategory, "workload_category"))
        object.__setattr__(self, "task_status", enum_value(self.task_status, TaskStatus, "task_status"))
        string_set(self.required_qualifications, "required_qualifications")
        string_set(self.allowed_zone_ids, "allowed_zone_ids", ids=True)
        if not self.allowed_zone_ids:
            raise ValueError("allowed_zone_ids must not be empty")
        if self.assigned_worker_id is not None:
            identifier(self.assigned_worker_id, "assigned_worker_id")
        if self.estimated_metabolic_rate_watts is not None:
            finite_number(self.estimated_metabolic_rate_watts, "estimated_metabolic_rate_watts", positive=True)
