from collections import Counter
from adapters.apache_csv import load_apache_scraper_csv, normalize_length, normalize_price
from interface_logic import DATA, load_inventory

def test_current_sample_loads_all_rows():
    rows=load_inventory(); assert len(rows)==276

def test_current_sample_recovers_all_three_categories():
    c=Counter(r['rv_category'] for r in load_inventory())
    assert c['Travel Trailer']>0 and c['Fifth Wheel']>0 and c['Truck Camper']>0

def test_compact_lengths_repaired_and_no_absurd_lengths():
    rows=load_inventory(); assert normalize_length(253)==25.25; assert abs(normalize_length(417)-(41+7/12))<0.001
    assert not any((r['overall_length_ft'] or 0)>60 for r in rows)

def test_bad_199_price_is_not_presented_as_rv_price():
    assert normalize_price('$199') is None
    assert all(r['price_usd'] is None for r in load_inventory())

def test_missing_weights_remain_missing():
    rows=load_inventory()
    assert any(r['gvwr_lb'] is None for r in rows)
    assert any(r['uvw_lb'] is None for r in rows)
    assert any(r['published_hitch_pin_lb'] is None for r in rows)

def test_locations_and_pipeline_are_normalized():
    rows=load_inventory()
    assert any(r['location']=='Portland, OR' for r in rows)
    assert any(r['inventory_status']=='Pipeline' for r in rows)
