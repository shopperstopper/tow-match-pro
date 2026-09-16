from vehicle_data import VehicleAcquisitionInput, DataSource, acquire_vehicle, to_engine_vehicle_state, normalize_vin, vin_is_valid
from tow_match import match_travel_trailer, MatchStatus

class FakeVpic:
    def __init__(self, data=None, fail=False): self.data=data or {}; self.fail=fail
    def decode(self, vin):
        if self.fail: raise RuntimeError('offline')
        return self.data

def test_normalize_and_validate_known_expedition_vin():
    vin='1FMJU2AT7KEA31907'
    assert normalize_vin(' 1fmju2at7kea31907 ') == vin
    assert vin_is_valid(vin)

def test_bad_vin_does_not_block_payload_acquisition():
    r=acquire_vehicle(VehicleAcquisitionInput(vin='BADVIN',payload_label_lb=1501))
    assert r.fact_value('payload_lb')==1501
    assert r.identity.vin is None
    assert any('continue without VIN' in x for x in r.warnings)

def test_vpic_failure_does_not_block_tow_match():
    inp=VehicleAcquisitionInput(vin='1FMJU2AT7KEA31907',payload_label_lb=1501)
    r=acquire_vehicle(inp,FakeVpic(fail=True))
    assert r.fact_value('payload_lb')==1501
    assert any('lookup unavailable' in x for x in r.warnings)

def test_vpic_identity_is_not_mistaken_for_tow_rating():
    inp=VehicleAcquisitionInput(vin='1FMJU2AT7KEA31907',payload_label_lb=1501)
    r=acquire_vehicle(inp,FakeVpic({'ModelYear':'2019','Make':'FORD','Model':'Expedition','Trim':'Limited','ErrorCode':'0'}))
    assert r.identity.year==2019 and r.identity.make=='FORD' and r.identity.model=='Expedition'
    assert r.fact_value('tow_rating_lb') is None

def test_payload_provenance_is_vehicle_label():
    r=acquire_vehicle(VehicleAcquisitionInput(payload_label_lb=1501))
    assert r.facts['payload_lb'].source==DataSource.VEHICLE_LABEL

def test_known_reliable_tow_rating_flows_to_engine():
    inp=VehicleAcquisitionInput(payload_label_lb=1501,conventional_tow_rating_lb=6000,occupant_weight_lb=400,truck_cargo_lb=150)
    acq=acquire_vehicle(inp)
    v=to_engine_vehicle_state(inp,acq)
    result=match_travel_trailer(v,{'uvw_lb':5900,'gvwr_lb':8000,'published_hitch_pin_lb':600})
    assert result.status==MatchStatus.NOT_MATCH

def test_missing_tow_rating_flows_to_preliminary_not_block():
    inp=VehicleAcquisitionInput(payload_label_lb=1501,occupant_weight_lb=400,truck_cargo_lb=150)
    acq=acquire_vehicle(inp)
    v=to_engine_vehicle_state(inp,acq)
    result=match_travel_trailer(v,{'uvw_lb':4500,'gvwr_lb':7000,'published_hitch_pin_lb':500})
    assert result.status==MatchStatus.PRELIMINARY

def test_optional_manual_bed_size_flows_to_camper_state():
    inp=VehicleAcquisitionInput(payload_label_lb=3000,bed_size='Long',camper_eligible=True)
    r=acquire_vehicle(inp)
    v=to_engine_vehicle_state(inp,r)
    assert v.bed_size=='Long' and v.camper_eligible is True

def test_vpic_bed_length_can_supply_medium_confidence_fit_clue():
    inp=VehicleAcquisitionInput(vin='1FMJU2AT7KEA31907',payload_label_lb=1501)
    r=acquire_vehicle(inp,FakeVpic({'ModelYear':'2019','Make':'FORD','Model':'Expedition','BedLengthIN':'78','ErrorCode':'0'}))
    assert r.fact_value('bed_size')=='78 in'
    assert r.facts['bed_size'].source==DataSource.NHTSA_VPIC

class Rich2026F150Vpic:
    def decode(self, vin):
        return {
            'ModelYear':'2026','Make':'FORD','Model':'F-150','Trim':'XL',
            'DriveType':'RWD/Rear-Wheel Drive','BodyClass':'Pickup - Regular Cab',
            'EngineModel':'3.5L EcoBoost V6','DisplacementL':'3.5',
            'WheelBaseShort':'141.5','BedLengthIN':'96.0','ErrorCode':'0'
        }

def test_vpic_configuration_clues_fill_ford_config_without_salesperson_entry():
    from vehicle_data import FordCapabilityProvider
    # Axle ratio remains the only supplied decisive clue here; engine/cab/drive/wheelbase come from VIN decode.
    inp=VehicleAcquisitionInput(vin='1FTMF1C80TFA00001',payload_label_lb=1800,axle_ratio=3.31)
    # Test VIN checksum validation is orthogonal to configuration extraction; use direct identity path below.
    from vehicle_data.configuration import ford_config_from_vpic
    d=Rich2026F150Vpic().decode('x')
    from vehicle_data.acquisition import _identity_from_vpic
    ident=_identity_from_vpic('TESTVIN',d)
    cfg=ford_config_from_vpic(ident,d)
    assert cfg.drive == '4x2'
    assert cfg.cab == 'REGULAR'
    assert cfg.wheelbase_in == 141.5
    assert round(cfg.box_length_ft,1) == 8.0
    assert '3.5' in cfg.engine

def test_explicit_configuration_overrides_vpic_clue():
    from vehicle_data.configuration import merge_ford_config
    from vehicle_data import FordVehicleConfig
    explicit=FordVehicleConfig(drive='4x4',engine='5.0L V8')
    decoded=FordVehicleConfig(drive='4x2',engine='3.5L EcoBoost V6',cab='REGULAR',wheelbase_in=141.5)
    merged=merge_ford_config(explicit,decoded)
    assert merged.drive == '4x4'
    assert merged.engine == '5.0L V8'
    assert merged.cab == 'REGULAR'

def test_verified_pilot_expedition_vin_resolves_ford_rating_without_manual_tow_entry():
    from vehicle_data.manufacturer_service import ManufacturerCapabilityService
    inp=VehicleAcquisitionInput(vin='1FMJU2AT7KEA31907',payload_label_lb=1501,
        occupant_weight_lb=400,truck_cargo_lb=150,hitch_hardware_lb=100)
    # Even if live vPIC is unavailable, verified vehicle config cache + Ford guide can resolve this known pilot vehicle.
    r=acquire_vehicle(inp,FakeVpic(fail=True),ManufacturerCapabilityService())
    assert r.identity.model == 'Expedition'
    assert r.fact_value('tow_rating_lb') == 6000
    assert r.facts['tow_rating_lb'].source == DataSource.MANUFACTURER
    v=to_engine_vehicle_state(inp,r)
    assert v.tow_rating_lb == 6000
