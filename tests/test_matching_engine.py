from tow_match import VehicleState, MatchStatus, match_travel_trailer, match_fifth_wheel, match_truck_camper

def rv(**kw): return kw

def test_expedition_tt_known_tow_rating_rejects_over_6000():
    v=VehicleState(payload_lb=1501,tow_rating_lb=6000,occupant_weight_lb=400,truck_cargo_lb=150)
    r=match_travel_trailer(v,rv(uvw_lb=5900,gvwr_lb=8000,published_hitch_pin_lb=600))
    assert r.estimated_loaded_lb==6650
    assert r.status==MatchStatus.NOT_MATCH
    assert any(g.name=='Tow rating' and g.passed is False for g in r.gates)

def test_expedition_tt_under_6000_can_match():
    v=VehicleState(payload_lb=1501,tow_rating_lb=6000,occupant_weight_lb=400,truck_cargo_lb=150)
    r=match_travel_trailer(v,rv(uvw_lb=4500,gvwr_lb=5800,published_hitch_pin_lb=500))
    assert r.estimated_loaded_lb==5250
    assert r.qualification_load_lb==682.5
    assert r.status==MatchStatus.MATCH

def test_unknown_tow_rating_is_preliminary_not_failure():
    v=VehicleState(payload_lb=1501,occupant_weight_lb=400,truck_cargo_lb=150)
    r=match_travel_trailer(v,rv(uvw_lb=4500,gvwr_lb=7000,published_hitch_pin_lb=500))
    assert r.status==MatchStatus.PRELIMINARY
    assert 'Vehicle-specific conventional tow rating' in r.missing_information

def test_missing_rv_weight_is_unable_not_fail():
    v=VehicleState(payload_lb=2000,tow_rating_lb=8000)
    r=match_travel_trailer(v,rv(uvw_lb=None,gvwr_lb=7000,published_hitch_pin_lb=600))
    assert r.status==MatchStatus.UNABLE
    assert 'RV dry/UVW weight' in r.missing_information

def test_tt_published_hitch_is_floor():
    v=VehicleState(payload_lb=2500,tow_rating_lb=10000)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=8000,published_hitch_pin_lb=900))
    assert r.qualification_load_lb==900

def test_tt_gvwr_over_tow_rating_does_not_alone_reject():
    v=VehicleState(payload_lb=2500,tow_rating_lb=7000)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=9000,published_hitch_pin_lb=650))
    assert r.estimated_loaded_lb==5750
    assert r.status==MatchStatus.MATCH
    assert any('GVWR exceeds' in x for x in r.advisories)

def test_fifth_wheel_does_not_use_conventional_rating():
    v=VehicleState(payload_lb=5000,tow_rating_lb=20000)
    r=match_fifth_wheel(v,rv(uvw_lb=9000,gvwr_lb=12000,published_hitch_pin_lb=1800))
    assert r.status==MatchStatus.PRELIMINARY
    assert any(g.name=='Fifth-wheel tow rating' and g.passed is None for g in r.gates)

def test_fifth_wheel_20_percent_pin_floor():
    v=VehicleState(payload_lb=5000,fifth_wheel_tow_rating_lb=16000)
    r=match_fifth_wheel(v,rv(uvw_lb=10000,gvwr_lb=13000,published_hitch_pin_lb=1500))
    assert r.estimated_loaded_lb==11250
    assert r.qualification_load_lb==2250

def test_camper_known_bed_mismatch_is_not_match():
    v=VehicleState(payload_lb=4000,bed_size='Long',camper_eligible=True)
    r=match_truck_camper(v,rv(uvw_lb=1800,fresh_water_gal=20,lp_tank_capacity_lb=20,lp_tank_count=1,truck_bed_size='Ultra Short',cg_front_in=22),battery_weight_lb=65)
    assert r.status==MatchStatus.NOT_MATCH
    assert any(g.name=='Bed compatibility' and g.passed is False for g in r.gates)

def test_camper_missing_dry_weight_is_unable():
    v=VehicleState(payload_lb=4000,bed_size='Ultra Short',camper_eligible=True)
    r=match_truck_camper(v,rv(uvw_lb=None,truck_bed_size='Ultra Short'))
    assert r.status==MatchStatus.UNABLE

def test_camper_unknown_eligibility_is_preliminary():
    v=VehicleState(payload_lb=5000,bed_size='Ultra Short')
    r=match_truck_camper(v,rv(uvw_lb=1200,fresh_water_gal=20,lp_tank_capacity_lb=20,lp_tank_count=1,truck_bed_size='Ultra Short'),battery_weight_lb=65)
    assert r.status==MatchStatus.PRELIMINARY
    assert 'Manufacturer camper eligibility' in r.missing_information
