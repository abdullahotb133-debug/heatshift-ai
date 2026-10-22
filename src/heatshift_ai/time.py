from dataclasses import dataclass
from .validation import seconds


@dataclass(frozen=True, kw_only=True)
class SimulationTime:
    elapsed_seconds: int = 0
    tick_seconds: int = 10

    def __post_init__(self) -> None:
        seconds(self.elapsed_seconds, "elapsed_seconds")
        seconds(self.tick_seconds, "tick_seconds", positive=True)
