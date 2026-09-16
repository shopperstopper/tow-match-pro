from adapters.apache_inventory import parse_feet_inches, normalize_category, parse_title

def test_normal_length():
    assert parse_feet_inches("25 ft 3 in", compact_length_fix=True) == 25.25

def test_interactrv_compact_length():
    assert parse_feet_inches("253 ft", compact_length_fix=True) == 25.25
    assert round(parse_feet_inches("286 ft", compact_length_fix=True), 3) == 28.5
    assert round(parse_feet_inches("402 ft", compact_length_fix=True), 3) == round(40 + 2/12, 3)
    assert round(parse_feet_inches("417 ft", compact_length_fix=True), 3) == round(41 + 7/12, 3)

def test_does_not_divide_arbitrary_values_by_12():
    assert parse_feet_inches("75 ft", compact_length_fix=True) == 75.0

def test_categories():
    assert normalize_category("Travel Trailer") == "Travel Trailer"
    assert normalize_category("Fifth Wheel") == "Fifth Wheel"
    assert normalize_category("Truck Camper") == "Truck Camper"

def test_title_preserves_unknown_boundaries():
    c, y, mfr, brand, model = parse_title("Used 2024 Jayco Jay Flight SLX 183RBW")
    assert (c, y) == ("Used", 2024)
    assert mfr is None and brand is None
    assert model == "Jayco Jay Flight SLX 183RBW"

def test_no_matching_defaults_are_created_by_schema():
    from inventory_schema import InventoryRecord
    r = InventoryRecord()
    assert r.uvw_lb is None
    assert r.gvwr_lb is None
    assert r.published_hitch_pin_lb is None
    assert r.overall_length_ft is None

from pathlib import Path
from adapters.apache_inventory import parse_vdp_html

FIXTURES = Path(__file__).parent / "fixtures"

def _parse_fixture(name):
    return parse_vdp_html((FIXTURES / name).read_bytes(), f"https://www.apachecamping.com/product/{name}")

def test_travel_trailer_vdp_fixture():
    r = _parse_fixture("travel_trailer.html")
    assert r.rv_category == "Travel Trailer"
    assert r.stock_number == "ACCP31232"
    assert r.location == "Portland, OR"
    assert r.overall_length_ft == round(24 + 2/12, 3)
    assert (r.uvw_lb, r.gvwr_lb, r.ccc_lb, r.published_hitch_pin_lb) == (5650, 8250, 2600, 650)
    assert r.fresh_water_gal == 78
    assert r.provenance["uvw_lb"]["raw"] == "5650 lbs"

def test_fifth_wheel_vdp_fixture():
    r = _parse_fixture("fifth_wheel.html")
    assert r.rv_category == "Fifth Wheel"
    assert r.stock_number == "58759"
    assert r.overall_length_ft == 29.75
    assert (r.uvw_lb, r.gvwr_lb, r.published_hitch_pin_lb) == (11025, 13600, 2225)

def test_truck_camper_vdp_fixture_and_cg_alias():
    r = _parse_fixture("truck_camper.html")
    assert r.rv_category == "Truck Camper"
    assert r.stock_number == "ACCP19731"
    assert r.truck_bed_size == "Ultra Short"
    assert r.body_style == "Pop-Up"
    assert r.cg_front_in == 22
    assert r.lp_tank_capacity_lb == 20
    assert r.lp_tank_count == 1
    assert r.uvw_lb is None  # missing stays missing; matching engine handles assumptions later

def test_truck_camper_fit_fields_have_provenance():
    r = _parse_fixture("truck_camper.html")
    assert r.provenance['truck_bed_size']['value'] == 'Ultra Short'
    assert r.provenance['body_style']['value'] == 'Pop-Up'
    assert r.provenance['cg_front_in']['value'] == 22
