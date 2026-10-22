import math
import re
from enum import Enum
from typing import TypeVar

E = TypeVar("E", bound=Enum)


def identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value) is None:
        raise ValueError(f"{field} must be an ID starting with a letter, containing only letters, digits, _ or -")


def nonempty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def seconds(value: int, field: str, positive: bool = False) -> None:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{field} must be a {'positive' if positive else 'non-negative'} integer in seconds")


def enum_value(value: E | str, enum: type[E], field: str) -> E:
    if not isinstance(value, (str, enum)) or isinstance(value, Enum) and not isinstance(value, enum):
        raise ValueError(f"{field} must be a valid {enum.__name__}")
    try:
        return enum(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be one of: {', '.join(x.value for x in enum)}") from exc


def string_set(value: frozenset[str], field: str, ids: bool = False) -> None:
    if not isinstance(value, frozenset):
        raise ValueError(f"{field} must be a frozenset of strings")
    for item in value:
        (identifier if ids else nonempty)(item, field)


def finite_number(value: float, field: str, positive: bool = False) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or positive and value <= 0:
        raise ValueError(f"{field} must be a finite {'positive ' if positive else ''}number")
