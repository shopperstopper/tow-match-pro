from vehicle_data import RamCapabilityProvider, RamVehicleConfig, ManufacturerCapabilityService, VehicleIdentity, DataSource


def test_2026_ram_1500_hurricane_exact_row():
    i=VehicleIdentity(year=2026,make='RAM',model='1500',drive_type='4WD')
    cfg=RamVehicleConfig(engine='3.0L I6 Twin Turbo Hurricane SO',cab='Crew Cab',bed="5'7\"",axle_ratio=3.92)
    r=RamCapabilityProvider().resolve(i,cfg)
    assert r.facts['tow_rating_lb'].value == 11200
    assert r.facts['max_tongue_lb'].value == 1100
    assert r.facts['tow_rating_lb'].source == DataSource.MANUFACTURER


def test_2026_ram_1500_pentastar_exact_row():
    i=VehicleIdentity(year=2026,make='RAM',model='1500',drive_type='RWD')
    cfg=RamVehicleConfig(engine='3.6L Pentastar V6',cab='Quad Cab',bed="6'4\"",axle_ratio=3.55)
    r=RamCapabilityProvider().resolve(i,cfg)
    assert r.facts['tow_rating_lb'].value == 7660


def test_2026_ram_1500_requires_axle_ratio_and_does_not_use_advertised_max():
    i=VehicleIdentity(year=2026,make='RAM',model='1500',drive_type='4WD')
    r=RamCapabilityProvider().resolve(i,RamVehicleConfig(engine='3.0L Hurricane',cab='Crew Cab',bed="5'7\""))
    assert 'tow_rating_lb' not in r.facts
    assert any('axle ratio' in x.lower() for x in r.missing)


def test_2026_ram_hd_does_not_substitute_engine_maximum_for_exact_rating():
    i=VehicleIdentity(year=2026,make='RAM',model='3500',drive_type='4WD')
    r=RamCapabilityProvider().resolve(i,RamVehicleConfig(engine='6.7L Cummins HO'))
    assert 'tow_rating_lb' not in r.facts
    assert any('advertised maximum' in x.lower() for x in r.missing)


def test_ram_dispatches_through_manufacturer_service():
    i=VehicleIdentity(year=2026,make='RAM',model='1500',drive_type='RWD')
    cfg=RamVehicleConfig(engine='3.0L Hurricane SO',cab='Quad Cab',bed="6'4\"",axle_ratio=3.92)
    r=ManufacturerCapabilityService().resolve(i,cfg)
    assert r.facts['tow_rating_lb'].value == 11610


def test_vpic_can_fill_ram_engine_drive_cab_bed_but_not_axle_ratio():
    from vehicle_data.configuration import ram_config_from_vpic
    d={'EngineModel':'3.0L Hurricane SO','DriveType':'4WD/4-Wheel Drive/4x4','CabType':'Crew Cab','BedLengthIN':'67.4'}
    i=VehicleIdentity(year=2026,make='RAM',model='1500')
    cfg=ram_config_from_vpic(i,d)
    assert cfg.drive == '4x4'
    assert cfg.cab == 'CREW'
    assert cfg.bed == '5-7'
    assert cfg.axle_ratio is None
