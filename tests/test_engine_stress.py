import pytest
from tow_match import VehicleState, MatchStatus, match, match_travel_trailer, match_fifth_wheel, match_truck_camper


def rv(**kw): return kw

@pytest.mark.parametrize('uvw,expected_allowance',[(3999,500),(4000,750),(5999,750),(6000,1000),(7999,1000),(8000,1250)])
def test_tt_cargo_band_boundaries(uvw,expected_allowance):
    v=VehicleState(payload_lb=10000,tow_rating_lb=30000)
    r=match_travel_trailer(v,rv(uvw_lb=uvw,gvwr_lb=30000,published_hitch_pin_lb=None))
    assert r.calculations['cargo_allowance_lb']==expected_allowance
    assert r.estimated_loaded_lb==uvw+expected_allowance

@pytest.mark.parametrize('uvw,expected_allowance',[(7999,1000),(8000,1250),(10999,1250),(11000,1500),(13999,1500),(14000,1700)])
def test_fw_cargo_band_boundaries(uvw,expected_allowance):
    v=VehicleState(payload_lb=10000,fifth_wheel_tow_rating_lb=30000)
    r=match_fifth_wheel(v,rv(uvw_lb=uvw,gvwr_lb=30000,published_hitch_pin_lb=None))
    assert r.calculations['cargo_allowance_lb']==expected_allowance


def test_tt_gvwr_caps_normal_loaded_weight():
    v=VehicleState(payload_lb=5000,tow_rating_lb=10000)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=5400,published_hitch_pin_lb=500))
    assert r.estimated_loaded_lb==5400


def test_fw_gvwr_caps_normal_loaded_weight():
    v=VehicleState(payload_lb=8000,fifth_wheel_tow_rating_lb=20000)
    r=match_fifth_wheel(v,rv(uvw_lb=10000,gvwr_lb=10500,published_hitch_pin_lb=1800))
    assert r.estimated_loaded_lb==10500


def test_tt_exact_qualification_tongue_passes_payload_gate():
    # loaded=5750, 13%=747.5; available=747.5 exactly
    v=VehicleState(payload_lb=997.5,tow_rating_lb=10000,truck_cargo_lb=150,hitch_hardware_lb=100)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=9000,published_hitch_pin_lb=None))
    assert next(g for g in r.gates if g.name=='Payload').passed is True
    assert r.reserve_lb==pytest.approx(0)
    assert r.status==MatchStatus.PRELIMINARY  # passes 13%, not 15%


def test_tt_one_pound_below_qualification_tongue_fails():
    v=VehicleState(payload_lb=996.5,tow_rating_lb=10000,truck_cargo_lb=150,hitch_hardware_lb=100)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=9000,published_hitch_pin_lb=None))
    assert r.status==MatchStatus.NOT_MATCH


def test_tt_passes_15_percent_without_verification():
    # loaded 5750; upper=862.5; available=900
    v=VehicleState(payload_lb=1150,tow_rating_lb=10000,truck_cargo_lb=150,hitch_hardware_lb=100)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=9000,published_hitch_pin_lb=None))
    assert r.status==MatchStatus.MATCH


def test_tt_known_max_tongue_is_independent_hard_gate():
    v=VehicleState(payload_lb=5000,tow_rating_lb=15000,max_tongue_lb=700)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=9000,published_hitch_pin_lb=None))
    assert r.status==MatchStatus.NOT_MATCH
    g=next(g for g in r.gates if g.name=='Manufacturer max tongue')
    assert g.amount_over_lb==pytest.approx(47.5)


def test_tt_normal_loaded_pass_but_gvwr_over_rating_is_match_with_loading_warning():
    v=VehicleState(payload_lb=5000,tow_rating_lb=7000)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=9000,published_hitch_pin_lb=650))
    assert r.status==MatchStatus.MATCH
    assert any('GVWR exceeds' in x for x in r.advisories)


def test_fw_normal_loaded_pass_but_gvwr_over_rating_is_match_with_loading_warning():
    v=VehicleState(payload_lb=6000,fifth_wheel_tow_rating_lb=12000)
    r=match_fifth_wheel(v,rv(uvw_lb=9000,gvwr_lb=14000,published_hitch_pin_lb=1900))
    assert r.estimated_loaded_lb==10250
    assert r.status==MatchStatus.MATCH
    assert any('GVWR exceeds' in x for x in r.advisories)


def test_missing_published_hitch_is_assumption_not_missing_rv_data():
    v=VehicleState(payload_lb=3000,tow_rating_lb=12000)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=8000,published_hitch_pin_lb=None))
    assert r.status==MatchStatus.MATCH
    assert any('13%' in a for a in r.assumptions)


def test_unknown_vehicle_payload_is_preliminary_not_unable():
    v=VehicleState(payload_lb=None,tow_rating_lb=12000)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=8000,published_hitch_pin_lb=600))
    assert r.status==MatchStatus.PRELIMINARY


def test_unknown_category_is_unable():
    r=match(VehicleState(payload_lb=2000),rv(rv_category='Motorhome'))
    assert r.status==MatchStatus.UNABLE


def test_all_known_failures_are_reported_tt():
    v=VehicleState(payload_lb=700,tow_rating_lb=4000,max_tongue_lb=500,truck_cargo_lb=150)
    r=match_travel_trailer(v,rv(uvw_lb=6000,gvwr_lb=9000,published_hitch_pin_lb=1000))
    failed={g.name for g in r.gates if g.passed is False}
    assert {'Payload','Tow rating','Manufacturer max tongue'} <= failed


def test_fw_published_pin_floor_can_cause_payload_failure():
    v=VehicleState(payload_lb=2400,fifth_wheel_tow_rating_lb=15000,truck_cargo_lb=0,hitch_hardware_lb=200)
    r=match_fifth_wheel(v,rv(uvw_lb=8000,gvwr_lb=12000,published_hitch_pin_lb=2300))
    assert r.qualification_load_lb==2300
    assert r.status==MatchStatus.NOT_MATCH


def test_fw_exact_20_pass_but_25_requires_verify():
    # loaded=10250; q=2050, upper=2562.5; avail 2200
    v=VehicleState(payload_lb=2400,fifth_wheel_tow_rating_lb=15000,truck_cargo_lb=0,hitch_hardware_lb=200)
    r=match_fifth_wheel(v,rv(uvw_lb=9000,gvwr_lb=13000,published_hitch_pin_lb=None))
    assert r.status==MatchStatus.PRELIMINARY


def test_camper_full_water_known_capacity():
    v=VehicleState(payload_lb=5000,bed_size='Long',camper_eligible=True,truck_cargo_lb=0,occupant_weight_lb=0,hitch_hardware_lb=100)
    r=match_truck_camper(v,rv(uvw_lb=1000,fresh_water_gal=30,lp_tank_capacity_lb=20,lp_tank_count=2,truck_bed_size='Long'),battery_weight_lb=65,personal_cargo_lb=500)
    assert r.calculations['fresh_water_load_lb']==pytest.approx(249)
    assert r.calculations['propane_load_lb']==40


def test_camper_missing_water_uses_250_fallback():
    v=VehicleState(payload_lb=5000,bed_size='Long',camper_eligible=True)
    r=match_truck_camper(v,rv(uvw_lb=1000,fresh_water_gal=None,lp_tank_capacity_lb=20,lp_tank_count=1,truck_bed_size='Long'),battery_weight_lb=65)
    assert r.calculations['fresh_water_load_lb']==250


def test_camper_missing_propane_uses_30_fallback():
    v=VehicleState(payload_lb=5000,bed_size='Long',camper_eligible=True)
    r=match_truck_camper(v,rv(uvw_lb=1000,fresh_water_gal=20,truck_bed_size='Long'),battery_weight_lb=65)
    assert r.calculations['propane_load_lb']==30


def test_camper_battery_default_65():
    v=VehicleState(payload_lb=5000,bed_size='Long',camper_eligible=True)
    r=match_truck_camper(v,rv(uvw_lb=1000,fresh_water_gal=20,lp_tank_capacity_lb=20,lp_tank_count=1,truck_bed_size='Long'))
    assert r.calculations['battery_load_lb']==65


def test_camper_option_allowance_10_percent_capped_300():
    v=VehicleState(payload_lb=10000,bed_size='Long',camper_eligible=True)
    a=match_truck_camper(v,rv(uvw_lb=2000,truck_bed_size='Long'),battery_weight_lb=65)
    b=match_truck_camper(v,rv(uvw_lb=4000,truck_bed_size='Long'),battery_weight_lb=65)
    assert a.calculations['factory_options_allowance_lb']==200
    assert b.calculations['factory_options_allowance_lb']==300


def test_camper_known_factory_optioned_weight_does_not_add_option_allowance():
    v=VehicleState(payload_lb=10000,bed_size='Long',camper_eligible=True)
    r=match_truck_camper(v,rv(uvw_lb=2500,truck_bed_size='Long',weight_includes_factory_options=True),battery_weight_lb=65)
    assert r.calculations['factory_options_allowance_lb']==0


def test_camper_payload_and_cwr_both_evaluated():
    v=VehicleState(payload_lb=5000,camper_carrying_capacity_lb=2500,bed_size='Long',camper_eligible=True,truck_cargo_lb=0,occupant_weight_lb=0)
    r=match_truck_camper(v,rv(uvw_lb=2000,fresh_water_gal=20,lp_tank_capacity_lb=20,lp_tank_count=1,truck_bed_size='Long'),battery_weight_lb=65,personal_cargo_lb=300)
    assert next(g for g in r.gates if g.name=='Payload').passed is True
    assert next(g for g in r.gates if g.name=='Manufacturer camper carrying capacity').passed is False
    assert r.status==MatchStatus.NOT_MATCH


def test_camper_known_cg_outside_range_is_not_match():
    v=VehicleState(payload_lb=6000,bed_size='Long',camper_eligible=True,camper_cg_min_in=20,camper_cg_max_in=40)
    r=match_truck_camper(v,rv(uvw_lb=1500,truck_bed_size='Long',cg_front_in=45),battery_weight_lb=65)
    assert r.status==MatchStatus.NOT_MATCH


def test_camper_missing_cg_when_truck_has_range_is_preliminary():
    v=VehicleState(payload_lb=6000,bed_size='Long',camper_eligible=True,camper_cg_min_in=20,camper_cg_max_in=40)
    r=match_truck_camper(v,rv(uvw_lb=1500,truck_bed_size='Long',cg_front_in=None),battery_weight_lb=65)
    assert r.status==MatchStatus.PRELIMINARY


def test_camper_no_truck_cg_range_does_not_require_camper_cg():
    v=VehicleState(payload_lb=6000,bed_size='Long',camper_eligible=True)
    r=match_truck_camper(v,rv(uvw_lb=1500,truck_bed_size='Long',cg_front_in=None),battery_weight_lb=65)
    assert not any(g.name=='Center of gravity' for g in r.gates)


def test_camper_known_rear_gawr_failure_is_not_match():
    v=VehicleState(payload_lb=6000,bed_size='Long',camper_eligible=True,rear_gawr_remaining_lb=1000)
    r=match_truck_camper(v,rv(uvw_lb=1500,truck_bed_size='Long'),battery_weight_lb=65)
    assert r.status==MatchStatus.NOT_MATCH
    assert next(g for g in r.gates if g.name=='Rear GAWR').passed is False


def test_camper_known_tire_failure_is_not_match():
    v=VehicleState(payload_lb=6000,bed_size='Long',camper_eligible=True,tire_capacity_remaining_lb=1000)
    r=match_truck_camper(v,rv(uvw_lb=1500,truck_bed_size='Long'),battery_weight_lb=65)
    assert r.status==MatchStatus.NOT_MATCH


def test_camper_missing_bed_data_is_preliminary_not_fail():
    v=VehicleState(payload_lb=6000,camper_eligible=True)
    r=match_truck_camper(v,rv(uvw_lb=1500,truck_bed_size=None),battery_weight_lb=65)
    assert r.status==MatchStatus.PRELIMINARY


def test_camper_explicit_ineligible_is_not_match_even_if_weight_passes():
    v=VehicleState(payload_lb=10000,bed_size='Long',camper_eligible=False)
    r=match_truck_camper(v,rv(uvw_lb=1000,truck_bed_size='Long'),battery_weight_lb=65)
    assert r.status==MatchStatus.NOT_MATCH


def test_camper_negative_payload_reserve_is_not_match():
    v=VehicleState(payload_lb=2000,bed_size='Long',camper_eligible=True)
    r=match_truck_camper(v,rv(uvw_lb=1800,truck_bed_size='Long'),battery_weight_lb=65)
    assert r.reserve_lb < 0
    assert r.reserve_label=='Not Match'
    assert r.status==MatchStatus.NOT_MATCH


def test_camper_minimal_reserve_plus_estimates_is_preliminary():
    # Tune payload to total load + 100 reserve, with estimated water/propane/options.
    base_v=VehicleState(payload_lb=10000,bed_size='Long',camper_eligible=True,occupant_weight_lb=0,pets_weight_lb=0,truck_cargo_lb=0,hitch_hardware_lb=100)
    base=match_truck_camper(base_v,rv(uvw_lb=1000,truck_bed_size='Long'),battery_weight_lb=65,personal_cargo_lb=300)
    total=base.calculations['total_vehicle_load_lb']
    v=VehicleState(payload_lb=total+100,bed_size='Long',camper_eligible=True,occupant_weight_lb=0,pets_weight_lb=0,truck_cargo_lb=0,hitch_hardware_lb=100)
    r=match_truck_camper(v,rv(uvw_lb=1000,truck_bed_size='Long'),battery_weight_lb=65,personal_cargo_lb=300)
    assert 0 <= r.reserve_lb < 200
    assert r.status==MatchStatus.PRELIMINARY


def test_custom_hitch_hardware_replaces_tt_default():
    v=VehicleState(payload_lb=2000,tow_rating_lb=12000,hitch_hardware_lb=50,truck_cargo_lb=0)
    r=match_travel_trailer(v,rv(uvw_lb=5000,gvwr_lb=8000,published_hitch_pin_lb=600))
    assert r.available_payload_lb==1950


def test_people_pets_and_truck_cargo_all_reduce_payload():
    v=VehicleState(payload_lb=2000,tow_rating_lb=12000,occupant_weight_lb=400,pets_weight_lb=75,truck_cargo_lb=150,hitch_hardware_lb=100)
    r=match_travel_trailer(v,rv(uvw_lb=3000,gvwr_lb=5000,published_hitch_pin_lb=400))
    assert r.available_payload_lb==1275

def test_tt_gvwr_below_uvw_is_unable_not_fake_lighter_loaded_weight():
    v=VehicleState(payload_lb=5000,tow_rating_lb=15000)
    r=match_travel_trailer(v,rv(uvw_lb=7000,gvwr_lb=6000,published_hitch_pin_lb=700))
    assert r.status==MatchStatus.UNABLE
    assert r.estimated_loaded_lb is None
    assert any('GVWR is below UVW' in x for x in r.missing_information)


def test_fw_gvwr_below_uvw_is_unable():
    v=VehicleState(payload_lb=8000,fifth_wheel_tow_rating_lb=20000)
    r=match_fifth_wheel(v,rv(uvw_lb=12000,gvwr_lb=11000,published_hitch_pin_lb=2400))
    assert r.status==MatchStatus.UNABLE
    assert r.estimated_loaded_lb is None


def test_randomized_tt_invariants_do_not_crash_or_false_pass_known_failures():
    import random
    rng=random.Random(20260914)
    for _ in range(1000):
        uvw=rng.randint(1500,12000)
        gvwr=uvw+rng.randint(0,5000)
        payload=rng.randint(500,5000)
        tow=rng.randint(2500,18000)
        v=VehicleState(payload_lb=payload,tow_rating_lb=tow,occupant_weight_lb=rng.randint(0,800),pets_weight_lb=rng.randint(0,200),truck_cargo_lb=rng.randint(0,500))
        r=match_travel_trailer(v,rv(uvw_lb=uvw,gvwr_lb=gvwr,published_hitch_pin_lb=None))
        assert r.estimated_loaded_lb >= uvw
        assert r.estimated_loaded_lb <= gvwr
        payload_gate=next(g for g in r.gates if g.name=='Payload')
        tow_gate=next(g for g in r.gates if g.name=='Tow rating')
        if payload_gate.passed is False or tow_gate.passed is False:
            assert r.status==MatchStatus.NOT_MATCH


def test_randomized_fw_invariants_do_not_crash_or_false_pass_known_failures():
    import random
    rng=random.Random(110)
    for _ in range(1000):
        uvw=rng.randint(5000,18000)
        gvwr=uvw+rng.randint(0,6000)
        v=VehicleState(payload_lb=rng.randint(1500,9000),fifth_wheel_tow_rating_lb=rng.randint(7000,30000),occupant_weight_lb=rng.randint(0,800),truck_cargo_lb=rng.randint(0,500))
        r=match_fifth_wheel(v,rv(uvw_lb=uvw,gvwr_lb=gvwr,published_hitch_pin_lb=None))
        assert uvw <= r.estimated_loaded_lb <= gvwr
        if any(g.passed is False and g.required for g in r.gates):
            assert r.status==MatchStatus.NOT_MATCH
