"""Deterministic JSON export; optional values remain explicit nulls."""
import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any


def to_json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (set, frozenset)):
        return sorted(to_json_value(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json_value(item) for key, item in value.items()}
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def to_json(value: Any) -> str:
    return json.dumps(to_json_value(value), sort_keys=True, allow_nan=False)
