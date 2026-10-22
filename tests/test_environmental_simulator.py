from dataclasses import replace
import json
import pytest
from heatshift_ai.environmental_simulator import EnvironmentalSimulator, EnvironmentalForcing, ZoneEnvironmentConfig
from heatshift_ai.wbgt import EnvironmentalSample, calculate_wbgt
from heatshift_ai import to_json, ScenarioController


def sample(**changes):
    return EnvironmentalSample(**(dict(zone_id='ZONE_A',elapsed_seconds=10,observed_at_seconds=10,
        source='simulated',air_temperature_c=30,relative_humidity_percent=50,globe_temperature_c=40,
        air_velocity_m_s=1,natural_wet_bulb_c=24,solar_exposure=True)|changes))


def test_wbgt_formulas_and_provenance():
    for source in ('measured','simulated'):
        result=calculate_wbgt(sample(source=source))
        assert result.value_c==pytest.approx(27.8)
        assert result.input_source==source and result.kind=='calculated'
        result=calculate_wbgt(sample(source=source,solar_exposure=False,air_temperature_c=None))
        assert result.value_c==pytest.approx(28.8)
        assert result.method=='ISO7243_0.7Tnw+0.3Tg'


@pytest.mark.parametrize('changes',[{'natural_wet_bulb_c':None},{'globe_temperature_c':None},
    {'air_temperature_c':None},{'solar_exposure':None},{'quality':'invalid'}, {'quality':'missing'},
    {'quality':'stale','observed_at_seconds':9}])
def test_no_estimates_or_stale_wbgt(changes):
    result=calculate_wbgt(sample(**changes))
    assert result.value_c is None and result.kind=='unavailable'


@pytest.mark.parametrize('changes',[{'relative_humidity_percent':-1},{'relative_humidity_percent':101},
    {'air_velocity_m_s':-1},{'air_temperature_c':float('nan')},{'globe_temperature_c':151},
    {'natural_wet_bulb_c':81},{'solar_exposure':'yes'},{'source':'calculated'},
    {'elapsed_seconds':-1},{'elapsed_seconds':True},{'zone_id':''},
    {'observed_at_seconds':11},{'observed_at_seconds':9},{'quality':'stale'},{'quality':'bad'}])
def test_physical_input_and_quality_validation(changes):
    with pytest.raises(ValueError): sample(**changes)


def test_seed_zone_time_and_continuity():
    a,b=EnvironmentalSimulator(seed=42),EnvironmentalSimulator(seed=42)
    for t in (0,10,1000):
        assert a.observe(zone_id='ZONE_A',elapsed_seconds=t)==b.observe(zone_id='ZONE_A',elapsed_seconds=t)
    assert a.observe(zone_id='ZONE_A',elapsed_seconds=100)!=EnvironmentalSimulator(seed=43).observe(zone_id='ZONE_A',elapsed_seconds=100)
    before=a.sample(zone_id='ZONE_A',elapsed_seconds=100)
    after=a.sample(zone_id='ZONE_A',elapsed_seconds=101)
    assert abs(after.air_temperature_c-before.air_temperature_c)<0.01
    assert a.sample(zone_id='REST_ZONE',elapsed_seconds=100).air_temperature_c<before.air_temperature_c
    a.observe(zone_id='ZONE_B',elapsed_seconds=5000)
    assert a.sample(zone_id='ZONE_A',elapsed_seconds=100)==before
    with pytest.raises(LookupError): a.observe(zone_id='NO',elapsed_seconds=0)
    with pytest.raises(ValueError): a.observe(zone_id='ZONE_A',elapsed_seconds=1.5)


def test_correlated_escalation_and_missing_config():
    simulator=EnvironmentalSimulator(forcing=EnvironmentalForcing(zone_heat=(('ZONE_A',0,6),)))
    a=simulator.sample(zone_id='ZONE_A',elapsed_seconds=0)
    b=simulator.sample(zone_id='ZONE_A',elapsed_seconds=600)
    assert b.air_temperature_c>a.air_temperature_c and b.globe_temperature_c>a.globe_temperature_c
    assert b.relative_humidity_percent<a.relative_humidity_percent
    simulator=EnvironmentalSimulator(zones=(ZoneEnvironmentConfig(zone_id='CUSTOM',natural_wet_bulb_c=None),))
    obs=simulator.observe(zone_id='CUSTOM',elapsed_seconds=0)
    assert obs.wbgt_celsius is None and dict(obs.source_metadata)['quality']=='missing'


@pytest.mark.parametrize('mode',['missing','invalid','stale'])
def test_sensor_failure_preserves_quality(mode):
    simulator=EnvironmentalSimulator(forcing=EnvironmentalForcing(failure_zone_id='ZONE_A',failure_mode=mode))
    obs=simulator.observe(zone_id='ZONE_A',elapsed_seconds=40)
    assert dict(obs.source_metadata)['quality']==mode
    assert obs.wbgt_celsius is None
    if mode=='stale': assert dict(obs.source_metadata)['observed_at_seconds']=='29'
    else: assert all(c.value is None for c in obs.conditions)
    assert dict(simulator.observe(zone_id='ZONE_A',elapsed_seconds=90).source_metadata)['quality']=='good'


def test_adapter_legacy_scenario_compatibility_and_json():
    c=ScenarioController('HEATWAVE',seed=42,adapter_factory=lambda:EnvironmentalSimulator(seed=42))
    c.run(10)
    obs=c.read_environment()[0]
    data=json.loads(to_json(obs))
    assert data['source']=='simulated' and len(data['conditions'])==5
    assert data['method'].startswith('ISO7243')
    original=c.export_json(); c.reset(); c.run(10)
    assert c.export_json()==original


@pytest.mark.parametrize('kwargs',[{'seed':True},{'zones':()}, {'forcing':EnvironmentalForcing(zone_heat=(('UNKNOWN',0,5),))}])
def test_bad_configuration(kwargs):
    with pytest.raises(ValueError): EnvironmentalSimulator(**kwargs)
