from vehicle_data import (
    DataSource, FordCapabilityProvider, FordVehicleConfig, VehicleAcquisitionInput,
    VehicleIdentity, acquire_vehicle, to_engine_vehicle_state
)
from tow_match import match_travel_trailer, MatchStatus

VIN='1FMJU2AT7KEA31907'

class ExpeditionVpic:
    def decode(self, vin):
        return {'ModelYear':'2019','Make':'FORD','Model':'Expedition','Trim':'Limited','DriveType':'4WD/4-Wheel Drive/4x4','ErrorCode':'0'}

def test_known_user_expedition_axle_code_15_resolves_6000_rating():
    inp=VehicleAcquisitionInput(vin=VIN,payload_label_lb=1501,axle_code='15',occupant_weight_lb=400,truck_cargo_lb=150)
    r=acquire_vehicle(inp,ExpeditionVpic(),FordCapabilityProvider())
    assert r.fact_value('tow_rating_lb') == 6000
    assert r.facts['tow_rating_lb'].source == DataSource.MANUFACTURER
    assert r.fact_value('axle_ratio') == 3.31

def test_known_expedition_rating_flows_into_engine_automatically():
    inp=VehicleAcquisitionInput(vin=VIN,payload_label_lb=1501,axle_code='15',occupant_weight_lb=400,truck_cargo_lb=150)
    r=acquire_vehicle(inp,ExpeditionVpic(),FordCapabilityProvider())
    v=to_engine_vehicle_state(inp,r)
    result=match_travel_trailer(v,{'uvw_lb':5900,'gvwr_lb':8000,'published_hitch_pin_lb':600})
    assert result.status == MatchStatus.NOT_MATCH
    assert any(g.name=='Tow rating' and g.passed is False for g in result.gates)

def test_2019_expedition_373_hd_4x4_resolves_9200():
    identity=VehicleIdentity(year=2019,make='FORD',model='Expedition',drive_type='4WD')
    r=FordCapabilityProvider().resolve(identity,FordVehicleConfig(axle_code='3L',heavy_duty_trailer_tow=True))
    assert r.facts['tow_rating_lb'].value == 9200

def test_2019_expedition_373_unknown_package_stays_unresolved():
    identity=VehicleIdentity(year=2019,make='FORD',model='Expedition',drive_type='4WD')
    r=FordCapabilityProvider().resolve(identity,FordVehicleConfig(axle_code='3L'))
    assert 'tow_rating_lb' not in r.facts
    assert any('Heavy-Duty Trailer Tow Package' in x for x in r.missing)

def test_2019_expedition_max_331_4x2_resolves_6300():
    identity=VehicleIdentity(year=2019,make='FORD',model='Expedition MAX',drive_type='RWD')
    r=FordCapabilityProvider().resolve(identity,FordVehicleConfig(axle_code='15'))
    assert r.facts['tow_rating_lb'].value == 6300

def test_manual_reliable_rating_wins_over_manufacturer_enrichment():
    inp=VehicleAcquisitionInput(vin=VIN,payload_label_lb=1501,axle_code='15',conventional_tow_rating_lb=5500)
    r=acquire_vehicle(inp,ExpeditionVpic(),FordCapabilityProvider())
    assert r.fact_value('tow_rating_lb') == 5500
    assert r.facts['tow_rating_lb'].source == DataSource.MANUAL_RELIABLE

def test_nonford_is_ignored_by_ford_provider():
    r=FordCapabilityProvider().resolve(VehicleIdentity(year=2019,make='TOYOTA',model='Tundra'),FordVehicleConfig(axle_code='15'))
    assert not r.facts and not r.missing

def test_unknown_ford_model_remains_verify_not_guessed():
    r=FordCapabilityProvider().resolve(VehicleIdentity(year=2020,make='FORD',model='F-150'),FordVehicleConfig())
    assert 'tow_rating_lb' not in r.facts
    assert r.missing

def test_manufacturer_service_dispatches_ford_without_changing_acquisition_contract():
    from vehicle_data import ManufacturerCapabilityService
    inp=VehicleAcquisitionInput(vin=VIN,payload_label_lb=1501,axle_code='15')
    r=acquire_vehicle(inp,ExpeditionVpic(),ManufacturerCapabilityService())
    assert r.fact_value('tow_rating_lb') == 6000

def test_2026_f150_exact_row_resolves_conventional_and_fifth_wheel():
    identity=VehicleIdentity(year=2026,make='FORD',model='F-150',drive_type='4x2')
    cfg=FordVehicleConfig(engine='3.5L EcoBoost V6',axle_ratio=3.31,cab='Regular Cab',wheelbase_in=141.5)
    r=FordCapabilityProvider().resolve(identity,cfg)
    assert r.facts['tow_rating_lb'].value == 10900
    assert r.facts['fifth_wheel_tow_rating_lb'].value == 10800


def test_2026_f150_incomplete_config_does_not_guess():
    identity=VehicleIdentity(year=2026,make='FORD',model='F-150',drive_type='4x4')
    r=FordCapabilityProvider().resolve(identity,FordVehicleConfig(engine='3.5L EcoBoost V6'))
    assert 'tow_rating_lb' not in r.facts
    assert r.missing


def test_2026_super_duty_exact_f250_row_and_receiver_tongue_limit():
    identity=VehicleIdentity(year=2026,make='FORD',model='F-250',drive_type='4x2')
    cfg=FordVehicleConfig(engine='6.7L Power Stroke Turbo Diesel V8',axle_ratio=3.31,cab='Regular Cab',wheelbase_in=141.6)
    r=FordCapabilityProvider().resolve(identity,cfg)
    assert r.facts['tow_rating_lb'].value == 16600
    assert r.facts['max_tongue_lb'].value == 2200


def test_2026_super_duty_unknown_exact_row_stays_unresolved():
    identity=VehicleIdentity(year=2026,make='FORD',model='F-350',drive_type='4x4')
    cfg=FordVehicleConfig(engine='6.7L Power Stroke Turbo Diesel V8',axle_ratio=3.31,cab='Crew Cab',wheelbase_in=176.0)
    r=FordCapabilityProvider().resolve(identity,cfg)
    assert 'tow_rating_lb' not in r.facts
    assert any('not yet installed' in x for x in r.missing)

def test_2026_f150_axle_code_15_means_315_not_expedition_331():
    identity=VehicleIdentity(year=2026,make='FORD',model='F-150',drive_type='4x2')
    cfg=FordVehicleConfig(engine='5.0L V8',axle_code='15',cab='Regular Cab',wheelbase_in=122.8)
    r=FordCapabilityProvider().resolve(identity,cfg)
    assert r.facts['axle_ratio'].value == 3.15
    assert r.facts['tow_rating_lb'].value == 9600
