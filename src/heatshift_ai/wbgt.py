"""WBGT weighting only. No psychrometric substitution or exposure limits.

References: ISO 7243:2017; NIOSH 2016-106, section 9.3.2.
"""
from dataclasses import dataclass
from enum import StrEnum
from .enums import MeasurementSource
from .validation import enum_value, finite_number, identifier, seconds, nonempty


class ReadingQuality(StrEnum):
    GOOD = 'good'
    MISSING = 'missing'
    STALE = 'stale'
    INVALID = 'invalid'


def bounded(value, name, lower, upper):
    if value is not None:
        finite_number(value, name)
        if not lower <= value <= upper:
            raise ValueError(f'{name} outside supported physical input range [{lower}, {upper}]')


@dataclass(frozen=True, kw_only=True)
class EnvironmentalSample:
    zone_id: str
    elapsed_seconds: int
    observed_at_seconds: int
    source: MeasurementSource
    air_temperature_c: float | None
    relative_humidity_percent: float | None
    globe_temperature_c: float | None
    air_velocity_m_s: float | None
    natural_wet_bulb_c: float | None
    solar_exposure: bool | None
    quality: ReadingQuality = ReadingQuality.GOOD
    quality_reason: str = 'valid input'

    def __post_init__(self):
        identifier(self.zone_id, 'zone_id')
        seconds(self.elapsed_seconds, 'elapsed_seconds')
        seconds(self.observed_at_seconds, 'observed_at_seconds')
        if self.observed_at_seconds > self.elapsed_seconds:
            raise ValueError('observation timestamp cannot be in the future')
        object.__setattr__(self, 'source', enum_value(self.source, MeasurementSource, 'source'))
        object.__setattr__(self, 'quality', enum_value(self.quality, ReadingQuality, 'quality'))
        nonempty(self.quality_reason, 'quality_reason')
        if self.solar_exposure is not None and type(self.solar_exposure) is not bool:
            raise ValueError('solar_exposure must be bool or None')
        for field, low, high in (
            ('air_temperature_c', -80, 80), ('relative_humidity_percent', 0, 100),
            ('globe_temperature_c', -80, 150), ('air_velocity_m_s', 0, 100),
            ('natural_wet_bulb_c', -80, 80)):
            bounded(getattr(self, field), field, low, high)
        if self.quality == ReadingQuality.GOOD and self.observed_at_seconds != self.elapsed_seconds:
            raise ValueError('good readings must be current; label older readings stale')
        if self.quality == ReadingQuality.STALE and self.observed_at_seconds >= self.elapsed_seconds:
            raise ValueError('stale reading requires an older observation timestamp')


@dataclass(frozen=True, kw_only=True)
class WBGTResult:
    value_c: float | None
    kind: str  # calculated or unavailable; no estimated method is implemented
    method: str | None
    input_source: MeasurementSource
    reason: str


def calculate_wbgt(sample: EnvironmentalSample) -> WBGTResult:
    if not isinstance(sample, EnvironmentalSample):
        raise ValueError('sample must be EnvironmentalSample')
    missing = (sample.natural_wet_bulb_c is None or sample.globe_temperature_c is None
               or sample.solar_exposure is None or sample.solar_exposure and sample.air_temperature_c is None)
    if sample.quality != ReadingQuality.GOOD or missing:
        return WBGTResult(value_c=None, kind='unavailable', method=None, input_source=sample.source,
                          reason='missing required input or non-good observation quality; no estimate substituted')
    if sample.solar_exposure:
        value = 0.7 * sample.natural_wet_bulb_c + 0.2 * sample.globe_temperature_c + 0.1 * sample.air_temperature_c
        method = 'ISO7243_0.7Tnw+0.2Tg+0.1Ta'
    else:
        value = 0.7 * sample.natural_wet_bulb_c + 0.3 * sample.globe_temperature_c
        method = 'ISO7243_0.7Tnw+0.3Tg'
    return WBGTResult(value_c=value, kind='calculated', method=method, input_source=sample.source,
                      reason='weighted supplied natural wet-bulb/globe inputs; not a heat-risk classification')
