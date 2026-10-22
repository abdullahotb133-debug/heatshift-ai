"""Synthetic correlated channel trajectories, separate from WBGT calculation.

Natural wet-bulb is an explicit simulated sensor channel anchored in config, NOT
estimated from air temperature/RH. Trajectories are plausible demo inputs, not a
validated meteorological/heat-transfer model or calibrated instrument simulator.
"""
from dataclasses import dataclass, replace
from math import sin, cos, pi
from random import Random

from .environment import EnvironmentalCondition, EnvironmentObservation
from .enums import MeasurementSource
from .validation import identifier, seconds, finite_number, nonempty
from .wbgt import EnvironmentalSample, ReadingQuality, calculate_wbgt


@dataclass(frozen=True, kw_only=True)
class ZoneEnvironmentConfig:
    zone_id: str
    air_temperature_c: float = 30.0
    relative_humidity_percent: float = 45.0
    globe_temperature_c: float = 36.0
    air_velocity_m_s: float = 1.2
    natural_wet_bulb_c: float | None = 23.0
    solar_exposure: bool = True
    variability_c: float = 0.3

    def __post_init__(self):
        EnvironmentalSample(zone_id=self.zone_id, elapsed_seconds=0, observed_at_seconds=0,
            source=MeasurementSource.SIMULATED, **{k: getattr(self, k) for k in (
            'air_temperature_c','relative_humidity_percent','globe_temperature_c',
            'air_velocity_m_s','natural_wet_bulb_c','solar_exposure')})
        if any(getattr(self,k) is None for k in ('air_temperature_c','relative_humidity_percent','globe_temperature_c','air_velocity_m_s','solar_exposure')):
            raise ValueError('baseline channels required except optional natural_wet_bulb_c')
        finite_number(self.variability_c, 'variability_c')
        if not 0 <= self.variability_c <= 2:
            raise ValueError('variability_c must be between 0 and 2 for this demo generator')


def default_environment_zones():
    return (
        ZoneEnvironmentConfig(zone_id='ZONE_A'),
        ZoneEnvironmentConfig(zone_id='ZONE_B', air_temperature_c=29, globe_temperature_c=31,
            relative_humidity_percent=48, natural_wet_bulb_c=23, air_velocity_m_s=1.5, solar_exposure=False),
        ZoneEnvironmentConfig(zone_id='ZONE_C', air_temperature_c=31, globe_temperature_c=38,
            relative_humidity_percent=43, natural_wet_bulb_c=24, air_velocity_m_s=0.8),
        ZoneEnvironmentConfig(zone_id='REST_ZONE', air_temperature_c=26, globe_temperature_c=26.5,
            relative_humidity_percent=50, natural_wet_bulb_c=21, air_velocity_m_s=1.8, solar_exposure=False),
    )


@dataclass(frozen=True, kw_only=True)
class EnvironmentalForcing:
    start_seconds: int = 0
    duration_seconds: int = 600
    # Each tuple is (zone_id, initial heat increment, final heat increment).
    zone_heat: tuple[tuple[str, float, float], ...] = ()
    failure_zone_id: str | None = None
    failure_start_seconds: int = 30
    failure_duration_seconds: int = 60
    failure_mode: str = 'missing'
    stopped_at_seconds: int | None = None

    def __post_init__(self):
        seconds(self.start_seconds, 'start_seconds')
        seconds(self.duration_seconds, 'duration_seconds', positive=True)
        seconds(self.failure_start_seconds, 'failure_start_seconds')
        seconds(self.failure_duration_seconds, 'failure_duration_seconds', positive=True)
        if self.stopped_at_seconds is not None:
            seconds(self.stopped_at_seconds, 'stopped_at_seconds')
        if self.failure_mode not in ('missing', 'stale', 'invalid'):
            raise ValueError('failure_mode must be missing, stale or invalid')
        if self.failure_zone_id is not None:
            identifier(self.failure_zone_id, 'failure_zone_id')
        if not isinstance(self.zone_heat, tuple):
            raise ValueError('zone_heat must be immutable tuples')
        seen = set()
        for row in self.zone_heat:
            if not isinstance(row, tuple) or len(row) != 3:
                raise ValueError('zone_heat rows must be (zone_id, initial, final)')
            zone, initial, final = row
            identifier(zone, 'forcing zone_id')
            if zone in seen:
                raise ValueError('duplicate forcing zone')
            seen.add(zone)
            for value in (initial, final):
                finite_number(value, 'heat increment')
                if not 0 <= value <= 15:
                    raise ValueError('heat increment outside supported demo envelope 0..15 C')

    def heat_at(self, zone_id, elapsed_seconds):
        t = min(elapsed_seconds, self.stopped_at_seconds) if self.stopped_at_seconds is not None else elapsed_seconds
        u = min(1.0, max(0.0, (t - self.start_seconds) / self.duration_seconds))
        smooth = u*u*(3-2*u)
        for zone, initial, final in self.zone_heat:
            if zone == zone_id:
                return initial + (final-initial)*smooth
        return 0.0


class EnvironmentalSimulator:
    def __init__(self, *, seed=0, zones=None, forcing=None):
        if type(seed) is not int:
            raise ValueError('seed must be integer')
        zones = default_environment_zones() if zones is None else zones
        if not isinstance(zones, tuple) or not zones or any(not isinstance(z, ZoneEnvironmentConfig) for z in zones):
            raise ValueError('zones must be a non-empty tuple of ZoneEnvironmentConfig')
        if len({z.zone_id for z in zones}) != len(zones):
            raise ValueError('duplicate environment zone')
        self.seed, self.zones = seed, zones
        self._forcing = EnvironmentalForcing() if forcing is None else forcing
        self._validate_forcing(self._forcing)
        # Sorted per-zone phases make lookups and input zone ordering reproducible.
        rng = Random(seed)
        self._phases = {z.zone_id:rng.uniform(0, 2*pi) for z in sorted(zones, key=lambda z:z.zone_id)}

    def _validate_forcing(self, forcing):
        if not isinstance(forcing, EnvironmentalForcing):
            raise ValueError('forcing must be EnvironmentalForcing')
        known={z.zone_id for z in self.zones}
        if any(z not in known for z,_,_ in forcing.zone_heat) or forcing.failure_zone_id is not None and forcing.failure_zone_id not in known:
            raise ValueError('forcing references unknown environment zone')

    def request_scenario(self, request):
        # Compatibility with existing ScenarioEnvironmentAdapter; no silent fallback.
        from .scenarios import EnvironmentScenarioRequest, ScenarioName
        if not isinstance(request, EnvironmentScenarioRequest):
            raise ValueError('request must be EnvironmentScenarioRequest')
        if request.seed != self.seed or set(request.zone_ids) != {z.zone_id for z in self.zones}:
            raise ValueError('request seed/zones must match environment configuration')
        initial, final = {ScenarioName.NORMAL:(0,0), ScenarioName.HEATWAVE:(0,6), ScenarioName.RECOVERY:(6,0)}[request.scenario]
        candidate=EnvironmentalForcing(start_seconds=request.elapsed_seconds,
            zone_heat=tuple((z,initial,final) for z in request.zone_ids))
        self._validate_forcing(candidate)
        self._forcing=candidate

    def _channels(self, zone, t):
        phase=self._phases[zone.zone_id]
        common=0.65*sin(t/900)+0.35*sin(t/1700)
        local=sin(phase+t/700)-sin(phase)
        drift=zone.variability_c*(0.8*common+0.2*local)
        heat=self._forcing.heat_at(zone.zone_id,t)
        wind=max(0.0,zone.air_velocity_m_s+0.05*zone.variability_c*(cos(t/800+phase)-cos(phase))-0.02*heat)
        return dict(air_temperature_c=zone.air_temperature_c+heat+drift,
            relative_humidity_percent=min(100.0,max(0.0,zone.relative_humidity_percent-1.2*heat-0.8*drift)),
            globe_temperature_c=zone.globe_temperature_c+(1.4 if zone.solar_exposure else 1.05)*heat+1.2*drift,
            air_velocity_m_s=wind,
            natural_wet_bulb_c=None if zone.natural_wet_bulb_c is None else zone.natural_wet_bulb_c+0.55*heat+0.5*drift,
            solar_exposure=zone.solar_exposure)

    def sample(self, *, zone_id, elapsed_seconds):
        identifier(zone_id,'zone_id'); seconds(elapsed_seconds,'elapsed_seconds')
        zone=next((z for z in self.zones if z.zone_id==zone_id),None)
        if zone is None:
            raise LookupError(f'unknown environment zone: {zone_id}')
        f=self._forcing
        failure_end=f.failure_start_seconds+f.failure_duration_seconds
        if f.stopped_at_seconds is not None:
            failure_end=min(failure_end,f.stopped_at_seconds)
        failed=zone_id==f.failure_zone_id and f.failure_start_seconds <= elapsed_seconds < failure_end
        quality=ReadingQuality.GOOD
        observed_at=elapsed_seconds
        if failed and f.failure_mode=='stale' and f.failure_start_seconds>0:
            quality=ReadingQuality.STALE
            observed_at=f.failure_start_seconds-1
            values=self._channels(zone,observed_at)
        elif failed:
            quality=ReadingQuality.INVALID if f.failure_mode=='invalid' else ReadingQuality.MISSING
            values={k:None for k in self._channels(zone,elapsed_seconds)}
        else:
            values=self._channels(zone,elapsed_seconds)
        if quality==ReadingQuality.GOOD and values['natural_wet_bulb_c'] is None:
            quality=ReadingQuality.MISSING
        return EnvironmentalSample(zone_id=zone_id,elapsed_seconds=elapsed_seconds,observed_at_seconds=observed_at,
            source=MeasurementSource.SIMULATED,quality=quality,
            quality_reason='synthetic channel trajectory' if quality==ReadingQuality.GOOD else f'explicit {quality.value} channel data; no substitute',**values)

    def observe(self, *, zone_id, elapsed_seconds):
        sample=self.sample(zone_id=zone_id,elapsed_seconds=elapsed_seconds)
        result=calculate_wbgt(sample)
        conditions=tuple(EnvironmentalCondition(name=name,value=getattr(sample,name),unit=unit) for name,unit in (
            ('air_temperature_c','degC'),('relative_humidity_percent','percent'),('globe_temperature_c','degC'),
            ('air_velocity_m_s','m/s'),('natural_wet_bulb_c','degC')))
        return EnvironmentObservation(zone_id=zone_id,elapsed_seconds=elapsed_seconds,wbgt_celsius=result.value_c,
            source=sample.source,conditions=conditions,method=result.method,
            source_metadata=(('provider','EnvironmentalSimulator'),('generator_version','1'),
                ('observation_provenance','simulated_sensor_observations'),('quality',sample.quality.value),
                ('quality_reason',sample.quality_reason),('observed_at_seconds',str(sample.observed_at_seconds)),
                ('solar_exposure','unknown' if sample.solar_exposure is None else str(sample.solar_exposure).lower()),
                ('wbgt_kind',result.kind),('wbgt_input_source',result.input_source.value),
                ('natural_wet_bulb_method','explicit_simulated_channel_not_psychrometric_estimate'),
                ('model_validation','engineering_demo_not_field_validated')))
