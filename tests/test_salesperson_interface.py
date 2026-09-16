from collections import Counter
from interface_logic import load_inventory, evaluate_inventory, apply_scope
from adapters.apache_csv import normalize_category
from tow_match.engine import match
from tow_match.models import VehicleState, MatchStatus

def test_legacy_inventory_loader_is_nonempty():
    rows=load_inventory(); assert len(rows)>200
    assert all(r['rv_category'] in {'Travel Trailer','Fifth Wheel','Truck Camper'} for r in rows)

def test_legacy_classifier_finds_all_three_categories():
    c=Counter(r['rv_category'] for r in load_inventory())
    assert c['Travel Trailer']>0 and c['Fifth Wheel']>0 and c['Truck Camper']>0
    assert normalize_category('New 2027 Outdoors RV Glacier Peak Titanium Series F27MKS', 'Travel Trailer')=='Fifth Wheel'
    assert normalize_category('New 2026 Host Industries Host Campers Mammoth 11.6', 'Truck Camper')=='Truck Camper'

def test_expedition_produces_tow_matches():
    v=VehicleState(payload_lb=1501,tow_rating_lb=6000,occupant_weight_lb=400,truck_cargo_lb=150,hitch_hardware_lb=100)
    rows=[r for r in load_inventory() if r['rv_category']=='Travel Trailer']
    results=[match(v,r) for r in rows]
    assert any(r.status==MatchStatus.MATCH for r in results)
    assert any(r.status==MatchStatus.NOT_MATCH for r in results)

def test_unknown_tow_rating_keeps_payload_qualified_as_verify():
    v=VehicleState(payload_lb=1501,occupant_weight_lb=400,truck_cargo_lb=150,hitch_hardware_lb=100)
    rv={'rv_category':'Travel Trailer','uvw_lb':3000,'gvwr_lb':4500,'published_hitch_pin_lb':400}
    assert match(v,rv).status==MatchStatus.PRELIMINARY

def test_specific_search_keeps_failed_unit_for_explanation():
    rows=load_inventory()
    target=next(r for r in rows if r['rv_category']=='Travel Trailer' and (r['gvwr_lb'] or 0)>7000)
    v=VehicleState(payload_lb=1000,tow_rating_lb=3000,occupant_weight_lb=400,truck_cargo_lb=150,hitch_hardware_lb=100)
    found=evaluate_inventory(rows,v,'Travel Trailer','Any','Any',target['display_title'])
    assert found and any(res.status==MatchStatus.NOT_MATCH for _,res in found)

def test_normal_browse_hides_failed_units():
    v=VehicleState(payload_lb=1000,tow_rating_lb=3000,occupant_weight_lb=400,truck_cargo_lb=150,hitch_hardware_lb=100)
    found=evaluate_inventory(load_inventory(),v,'Travel Trailer')
    assert found and all(res.status!=MatchStatus.NOT_MATCH for _,res in found)

def test_scope_is_progressive():
    v=VehicleState(payload_lb=5000,tow_rating_lb=20000,occupant_weight_lb=0,truck_cargo_lb=0,hitch_hardware_lb=100)
    ev=evaluate_inventory(load_inventory(),v,'Travel Trailer')
    lots=sorted({r['location'] for r,_ in ev if r['location']})
    assert lots
    this=apply_scope(ev,'This Lot',lots[0]); all_lots=apply_scope(ev,'All Dealer Locations'); pipeline=apply_scope(ev,'Pipeline')
    assert len(this)<=len(all_lots)<=len(pipeline)

def test_legacy_compact_lengths_are_normalized_for_ui_filters():
    rows=load_inventory()
    target=next(r for r in rows if 'Jay Flight SLX 183RBW' in r['display_title'])
    assert abs(target['overall_length_ft']-25.25)<0.001
    assert not any((r['overall_length_ft'] or 0)>60 for r in rows)

def test_approximate_length_is_preference_not_exclusion():
    from interface_logic import length_preference_rank
    v=VehicleState(payload_lb=5000,tow_rating_lb=20000,occupant_weight_lb=0,truck_cargo_lb=0,hitch_hardware_lb=100)
    all_any=evaluate_inventory(load_inventory(),v,'Travel Trailer','Any','Any','')
    preferred=evaluate_inventory(load_inventory(),v,'Travel Trailer','Any','Under 25 ft','')
    assert len(preferred)==len(all_any)
    assert any(length_preference_rank(rv,'Under 25 ft')==0 for rv,_ in preferred)
    assert any(length_preference_rank(rv,'Under 25 ft')>0 for rv,_ in preferred)

def test_specific_search_bypasses_condition_preference():
    rows=load_inventory()
    target=next(r for r in rows if r['rv_category']=='Travel Trailer' and r['condition']=='Used')
    v=VehicleState(payload_lb=5000,tow_rating_lb=20000,occupant_weight_lb=0,truck_cargo_lb=0,hitch_hardware_lb=100)
    found=evaluate_inventory(rows,v,'Travel Trailer','New','Under 25 ft',target['display_title'])
    assert found

def test_lot_selector_does_not_depend_on_compatible_results():
    from interface_logic import available_lots
    rows=load_inventory()
    lots=available_lots(rows,'Travel Trailer','Any')
    assert {'Everett, WA','Portland, OR','Poulsbo, WA','Tacoma, WA'}.issubset(set(lots))

def test_home_lot_is_explicitly_configured_and_available():
    from dealer_config import HOME_LOT
    from interface_logic import available_lots
    assert HOME_LOT == 'Portland, OR'
    assert HOME_LOT in available_lots(load_inventory(),'Travel Trailer','Any')

def test_major_type_vocabulary_and_filtering():
    from interface_logic import available_major_types
    rows=load_inventory()
    types=available_major_types(rows,'Travel Trailer')
    assert 'Any' in types and 'Bunkhouse' in types and 'Couples / Non-Bunkhouse' in types
    v=VehicleState(payload_lb=5000,tow_rating_lb=20000,occupant_weight_lb=0,truck_cargo_lb=0,hitch_hardware_lb=100)
    bunk=evaluate_inventory(rows,v,'Travel Trailer','Any','Any','',major_type='Bunkhouse')
    assert bunk and all(rv.get('major_type')=='Bunkhouse' for rv,_ in bunk)

def test_specific_search_bypasses_major_type_preference():
    rows=load_inventory()
    target=next(r for r in rows if r['rv_category']=='Travel Trailer' and r.get('major_type')=='Couples / Non-Bunkhouse')
    v=VehicleState(payload_lb=5000,tow_rating_lb=20000,occupant_weight_lb=0,truck_cargo_lb=0,hitch_hardware_lb=100)
    found=evaluate_inventory(rows,v,'Travel Trailer','Any','Any',target['display_title'],major_type='Bunkhouse')
    assert found
