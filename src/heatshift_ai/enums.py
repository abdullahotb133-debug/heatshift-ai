from enum import StrEnum


class AcclimatizationStatus(StrEnum):
    UNKNOWN = "unknown"
    NOT_ACCLIMATIZED = "not_acclimatized"
    PARTIALLY_ACCLIMATIZED = "partially_acclimatized"
    ACCLIMATIZED = "acclimatized"


class WorkStatus(StrEnum):
    IDLE = "idle"
    WORKING = "working"
    RESTING = "resting"


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class TaskStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WorkloadCategory(StrEnum):
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"
    VERY_HEAVY = "very_heavy"


class ZoneKind(StrEnum):
    WORK = "work"
    REST = "rest"


class MeasurementSource(StrEnum):
    SIMULATED = "simulated"
    MEASURED = "measured"
