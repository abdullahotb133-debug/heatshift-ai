from dataclasses import dataclass
from .enums import ZoneKind
from .validation import enum_value, identifier


@dataclass(frozen=True, kw_only=True)
class Zone:
    zone_id: str
    kind: ZoneKind

    def __post_init__(self) -> None:
        identifier(self.zone_id, "zone_id")
        object.__setattr__(self, "kind", enum_value(self.kind, ZoneKind, "kind"))
