from vehicle_data import GMCapabilityProvider, GMVehicleConfig, ManufacturerCapabilityService, VehicleIdentity, VehicleAcquisitionInput, acquire_vehicle, DataSource


def test_2026_silverado_1500_exact_regular_long_4x4_53():
    i=VehicleIdentity(year=2026,make='CHEVROLET',model='Silverado 1500',drive_type='4WD')
    r=GMCapabilityProvider().resolve(i,GMVehicleConfig(engine='5.3L EcoTec3 V8',cab='Regular Cab',bed='Long Bed'))
    assert r.facts['tow_rating_lb'].value == 9800
    assert r.facts['fifth_wheel_tow_rating_lb'].value == 9600


def test_2026_silverado_1500_incomplete_does_not_guess():
    i=VehicleIdentity(year=2026,make='CHEVROLET',model='Silverado 1500',drive_type='4WD')
    r=GMCapabilityProvider().resolve(i,GMVehicleConfig(engine='5.3L V8'))
    assert 'tow_rating_lb' not in r.facts
    assert r.missing


def test_2026_2500hd_exact_row_separates_conventional_and_fifthwheel():
    i=VehicleIdentity(year=2026,make='CHEVROLET',model='Silverado 2500 HD',drive_type='4WD')
    cfg=GMVehicleConfig(engine='6.6L Duramax Diesel',cab='Double Cab',bed='Long Bed',gvwr_lb=11450)
    r=GMCapabilityProvider().resolve(i,cfg)
    assert r.facts['tow_rating_lb'].value == 17600
    assert r.facts['fifth_wheel_tow_rating_lb'].value == 17600


def test_2026_2500hd_requires_gvwr_when_rows_differ():
    i=VehicleIdentity(year=2026,make='CHEVROLET',model='Silverado 2500 HD',drive_type='4WD')
    r=GMCapabilityProvider().resolve(i,GMVehicleConfig(engine='6.6L Duramax Diesel',cab='Double Cab',bed='Long Bed'))
    assert 'tow_rating_lb' not in r.facts
    assert any('GVWR' in x for x in r.missing)


def test_gmc_dispatches_through_manufacturer_service():
    svc=ManufacturerCapabilityService()
    i=VehicleIdentity(year=2026,make='GMC',model='Sierra 1500',drive_type='RWD')
    r=svc.resolve(i,GMVehicleConfig(engine='TurboMax 2.7L',cab='Regular Cab',bed='Long Bed'))
    assert r.facts['tow_rating_lb'].value == 9500


class GMVpic:
    def decode(self, vin):
        return {'ModelYear':'2026','Make':'CHEVROLET','Model':'Silverado 1500','DriveType':'4WD/4-Wheel Drive/4x4',
                'EngineModel':'L84 5.3L V8','CabType':'Regular Cab','BedLengthIN':'98.2','ErrorCode':'0'}


def test_vpic_configuration_can_feed_gm_provider_without_salesperson_engine_cab_bed_entry():
    # Known valid VIN shape/check digit is not important to provider behavior here, so use direct service test via identity config normalization.
    from vehicle_data.configuration import gm_config_from_vpic
    d=GMVpic().decode('x')
    i=VehicleIdentity(year=2026,make='CHEVROLET',model='Silverado 1500',drive_type='4WD',bed_length_in=98.2)
    cfg=gm_config_from_vpic(i,d)
    r=GMCapabilityProvider().resolve(i,cfg)
    assert r.facts['tow_rating_lb'].value == 9800


def test_gm_label_facts_keep_vehicle_label_provenance():
    # Acquisition can retain GM vehicle-specific label values independently of guide enrichment.
    inp=VehicleAcquisitionInput(payload_label_lb=2100,gm_gvwr_lb=7200,gm_gcwr_lb=17000,gm_rear_gawr_lb=3800)
    r=acquire_vehicle(inp)
    assert r.facts['gvwr_lb'].source == DataSource.VEHICLE_LABEL
    assert r.fact_value('gcwr_lb') == 17000

def test_gm_trailering_label_can_supply_payload_and_max_tongue_as_vehicle_label_facts():
    inp=VehicleAcquisitionInput(gm_label_max_payload_lb=2015,gm_label_max_tongue_lb=1250)
    r=acquire_vehicle(inp)
    assert r.fact_value('payload_lb') == 2015
    assert r.fact_value('max_tongue_lb') == 1250
    assert r.facts['max_tongue_lb'].source == DataSource.VEHICLE_LABEL
