from pathlib import Path
from adapters.apache_csv import load_apache_scraper_csv
from tow_match.engine import match
from tow_match.models import MatchStatus

DATA=Path(__file__).with_name('apache_full_inventory.csv')

def load_inventory(path=DATA):
    return load_apache_scraper_csv(path)

def length_preference_rank(rv, length_filter):
    """Approximate length is a preference (Rule 68), not an exclusion gate.
    Unknown length is retained but ranks after known in-range units.
    """
    L=rv.get('overall_length_ft')
    if length_filter=='Any': return 0
    if L is None: return 2
    if length_filter=='Under 25 ft': return 0 if L < 25 else 1
    if length_filter=='25–30 ft': return 0 if 25 <= L < 30 else 1
    if length_filter=='30–35 ft': return 0 if 30 <= L < 35 else 1
    if length_filter=='35+ ft': return 0 if L >= 35 else 1
    return 0

def length_matches(rv, length_filter):
    # Backward-compatible helper. Approximate length no longer excludes inventory.
    return True

def evaluate_inventory(inventory, vehicle, category, condition='Any', length_filter='Any', search='', major_type='Any'):
    q=(search or '').strip().lower(); out=[]
    for rv in inventory:
        if rv.get('rv_category') != category: continue
        # Specific-unit search bypasses shopping preferences; compatibility never bypassed.
        if q:
            hay=' '.join(str(rv.get(k) or '') for k in ('display_title','stock_number','source_url')).lower()
            if q not in hay: continue
        elif condition!='Any' and rv.get('condition')!=condition:
            continue
        elif not q and major_type!='Any' and rv.get('major_type')!=major_type:
            continue
        res=match(vehicle,rv)
        if q or res.status != MatchStatus.NOT_MATCH:
            out.append((rv,res))
    return out

def available_lots(inventory, category, condition='Any'):
    """Lots come from sellable inventory, not only from units that happened to match."""
    return sorted({r.get('location') for r in inventory
                   if r.get('rv_category')==category
                   and r.get('inventory_status')=='On Lot'
                   and r.get('sellable',True)
                   and r.get('location')
                   and (condition=='Any' or r.get('condition')==condition)})

def apply_scope(evaluated, scope, lot=None):
    if scope=='This Lot': return [x for x in evaluated if x[0].get('location')==lot and x[0].get('inventory_status')=='On Lot']
    if scope=='All Dealer Locations': return [x for x in evaluated if x[0].get('inventory_status')=='On Lot']
    return list(evaluated)


def available_major_types(inventory, category):
    """Small category-specific selling vocabulary; no amenity checklist."""
    preferred = {
        'Travel Trailer':['Bunkhouse','Toy Hauler','Couples / Non-Bunkhouse'],
        'Fifth Wheel':['Bunkhouse','Toy Hauler','Couples / Non-Bunkhouse'],
        'Truck Camper':['Hard-Side','Pop-Up'],
    }.get(category,[])
    present={r.get('major_type') for r in inventory if r.get('rv_category')==category and r.get('major_type')}
    return ['Any']+[x for x in preferred if x in present]
