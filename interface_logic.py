from pathlib import Path
from adapters.apache_csv import load_apache_scraper_csv
from tow_match.engine import match
from tow_match.models import MatchStatus

DATA=Path(__file__).with_name('apache_full_inventory.csv')

def load_inventory(path=DATA):
    return load_apache_scraper_csv(path)

def length_filter_matches(rv, length_filter):
    """Post-match shopping filter. It never participates in qualification."""
    L=rv.get('overall_length_ft')
    if length_filter=='Any': return True
    if L is None: return False
    if length_filter=='Under 20 ft': return L < 20
    if length_filter=='20–25 ft': return 20 <= L < 25
    if length_filter=='25–30 ft': return 25 <= L < 30
    if length_filter=='30–35 ft': return 30 <= L < 35
    if length_filter=='35+ ft': return L >= 35
    return True

def evaluate_inventory(inventory, vehicle, category):
    """Qualify the entire category first. No shopping preferences are applied here."""
    out=[]
    for rv in inventory:
        if rv.get('rv_category') != category: continue
        if not rv.get('sellable', True): continue
        res=match(vehicle,rv)
        if res.status != MatchStatus.NOT_MATCH:
            out.append((rv,res))
    return out

def filter_matches(evaluated, condition='Any', length_filter='Any', major_type='Any', brand='Any', search=''):
    """Filter an already-qualified Tow Match set. Never calls the matching engine."""
    q=(search or '').strip().lower(); out=[]
    for rv,res in evaluated:
        if condition!='Any' and rv.get('condition')!=condition: continue
        if major_type!='Any' and rv.get('major_type')!=major_type: continue
        if brand!='Any' and (rv.get('manufacturer') or '')!=brand: continue
        if not length_filter_matches(rv,length_filter): continue
        if q:
            hay=' '.join(str(rv.get(k) or '') for k in ('display_title','stock_number','source_url')).lower()
            if q not in hay: continue
        out.append((rv,res))
    return out

def search_specific_unit(inventory, vehicle, category, search):
    """Specific unit search is separate from shopping filters and may return Not Match."""
    q=(search or '').strip().lower()
    if not q: return []
    out=[]
    for rv in inventory:
        if rv.get('rv_category') != category: continue
        hay=' '.join(str(rv.get(k) or '') for k in ('display_title','stock_number','source_url')).lower()
        if q in hay: out.append((rv,match(vehicle,rv)))
    return out

def available_lots(inventory, category, condition='Any'):
    return sorted({r.get('location') for r in inventory
                   if r.get('rv_category')==category and r.get('inventory_status')=='On Lot'
                   and r.get('sellable',True) and r.get('location')
                   and (condition=='Any' or r.get('condition')==condition)})

def apply_scope(evaluated, scope, lot=None):
    if scope=='This Lot': return [x for x in evaluated if x[0].get('location')==lot and x[0].get('inventory_status')=='On Lot']
    if scope=='All Dealer Locations': return [x for x in evaluated if x[0].get('inventory_status')=='On Lot']
    return list(evaluated)

def available_major_types(inventory, category):
    preferred={'Travel Trailer':['Bunkhouse','Toy Hauler','Couples / Non-Bunkhouse'],
               'Fifth Wheel':['Bunkhouse','Toy Hauler','Couples / Non-Bunkhouse'],
               'Truck Camper':['Hard-Side','Pop-Up']}.get(category,[])
    present={r.get('major_type') for r in inventory if r.get('rv_category')==category and r.get('major_type')}
    return ['Any']+[x for x in preferred if x in present]

def available_brands(evaluated):
    return ['Any']+sorted({rv.get('manufacturer') for rv,_ in evaluated if rv.get('manufacturer')})
