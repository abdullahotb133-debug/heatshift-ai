"""Read-only boundary contract; no WBGT calculation or concrete integration."""
from dataclasses import dataclass
from typing import Protocol
from .enums import MeasurementSource
from .validation import enum_value, finite_number, identifier, seconds, nonempty


@dataclass(frozen=True, kw_only=True)
class EnvironmentalCondition:
    name: str
    value: float | None
    unit: str

    def __post_init__(self) -> None:
        nonempty(self.name, "condition name")
        nonempty(self.unit, "condition unit")
        if self.value is not None:
            finite_number(self.value, "condition value")


@dataclass(frozen=True, kw_only=True)
class EnvironmentObservation:
    zone_id: str
    elapsed_seconds: int
    wbgt_celsius: float | None
    source: MeasurementSource
    conditions: tuple[EnvironmentalCondition, ...] = ()
    method: str | None = None
    source_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.conditions, tuple) or any(not isinstance(c, EnvironmentalCondition) for c in self.conditions):
            raise ValueError("conditions must be a tuple of EnvironmentalCondition models")
        if len({c.name for c in self.conditions}) != len(self.conditions):
            raise ValueError("duplicate condition name")
        if self.method is not None:
            nonempty(self.method, "method")
        if not isinstance(self.source_metadata, tuple):
            raise ValueError("source_metadata must be a tuple of string pairs")
        for pair in self.source_metadata:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("source_metadata must contain string pairs")
            nonempty(pair[0], "metadata key")
            nonempty(pair[1], "metadata value")
        if len(dict(self.source_metadata)) != len(self.source_metadata):
            raise ValueError("duplicate metadata key")
        identifier(self.zone_id, "zone_id")
        seconds(self.elapsed_seconds, "elapsed_seconds")
        object.__setattr__(self, "source", enum_value(self.source, MeasurementSource, "source"))
        if self.wbgt_celsius is not None:
            finite_number(self.wbgt_celsius, "wbgt_celsius")


class EnvironmentAdapter(Protocol):
    def observe(self, *, zone_id: str, elapsed_seconds: int) -> EnvironmentObservation:
        """Return a same-zone, same-time reading; raise LookupError if unavailable.

        Implementations must retain provenance, use elapsed integer seconds,
        and raise ValueError for invalid inputs. None means missing WBGT, never zero.
        Reading must not mutate worker/task state or alter upstream WBGT calculations.
        """
        ...
