from dataclasses import dataclass
from .validation import identifier, seconds


@dataclass(frozen=True, kw_only=True)
class Assignment:
    """Current assignment only; completed assignments are not retained here."""
    worker_id: str
    task_id: str
    zone_id: str
    started_at_elapsed_seconds: int = 0

    def __post_init__(self) -> None:
        for name in ("worker_id", "task_id", "zone_id"):
            identifier(getattr(self, name), name)
        seconds(self.started_at_elapsed_seconds, "started_at_elapsed_seconds")
