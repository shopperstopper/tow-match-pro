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
    out=[]
    for rv in inventory:
        if rv.get('rv_category') != category or not rv.get('sellable', True): continue
        res=match(vehicle,rv)
        if res.status != MatchStatus.NOT_MATCH: out.append((rv,res))
    return out

def filter_matches(evaluated, condition='Any', length_filter='Any', major_type='Any', brand='Any', search='', status='All'):
    """Filter an already-qualified Tow Match set. Never calls the matching engine."""
    q=(search or '').strip().lower(); out=[]
    status_map={'Match':MatchStatus.MATCH,'Verify':MatchStatus.PRELIMINARY,'Unable':MatchStatus.UNABLE}
    for rv,res in evaluated:
        if status!='All' and res.status != status_map.get(status): continue
        if condition!='Any' and rv.get('condition')!=condition: continue
        if major_type!='Any' and rv.get('major_type')!=major_type: continue
        if brand!='Any' and (rv.get('manufacturer') or '')!=brand: continue
        if not length_filter_matches(rv,length_filter): continue
        if q:
            hay=' '.join(str(rv.get(k) or '') for k in ('display_title','stock_number','source_url')).lower()
            if q not in hay: continue
        out.append((rv,res))
    return out

def sort_matches(items, sort_by='Recommended'):
    status_order={MatchStatus.MATCH:0,MatchStatus.PRELIMINARY:1,MatchStatus.UNABLE:2,MatchStatus.NOT_MATCH:3}
    title=lambda x:(x[0].get('display_title') or '')
    if sort_by=='Heaviest first': return sorted(items,key=lambda x:(x[1].estimated_loaded_lb is None,-(x[1].estimated_loaded_lb or 0),title(x)))
    if sort_by=='Lightest first': return sorted(items,key=lambda x:(x[1].estimated_loaded_lb is None,(x[1].estimated_loaded_lb or 0),title(x)))
    if sort_by=='Longest first': return sorted(items,key=lambda x:(x[0].get('overall_length_ft') is None,-(x[0].get('overall_length_ft') or 0),title(x)))
    if sort_by=='Shortest first': return sorted(items,key=lambda x:(x[0].get('overall_length_ft') is None,(x[0].get('overall_length_ft') or 0),title(x)))
    if sort_by=='Price low to high': return sorted(items,key=lambda x:(x[0].get('price_usd') is None,(x[0].get('price_usd') or 0),title(x)))
    if sort_by=='Price high to low': return sorted(items,key=lambda x:(x[0].get('price_usd') is None,-(x[0].get('price_usd') or 0),title(x)))
    return sorted(items,key=lambda x:(status_order.get(x[1].status,9),title(x)))

def search_specific_unit(inventory, vehicle, category, search):
    q=(search or '').strip().lower()
    if not q: return []
    out=[]
    for rv in inventory:
        if rv.get('rv_category') != category: continue
        hay=' '.join(str(rv.get(k) or '') for k in ('display_title','stock_number','source_url')).lower()
        if q in hay: out.append((rv,match(vehicle,rv)))
    return out

def available_lots(inventory, category, condition='Any'):
    return sorted({r.get('location') for r in inventory if r.get('rv_category')==category and r.get('inventory_status')=='On Lot' and r.get('sellable',True) and r.get('location') and (condition=='Any' or r.get('condition')==condition)})

def apply_scope(evaluated, scope, lot=None):
    if scope=='This Lot': return [x for x in evaluated if x[0].get('location')==lot and x[0].get('inventory_status')=='On Lot']
    if scope=='All Dealer Locations': return [x for x in evaluated if x[0].get('inventory_status')=='On Lot']
    return list(evaluated)

def available_major_types(inventory, category):
    preferred={'Travel Trailer':['Bunkhouse','Toy Hauler','Rear Living','Rear Kitchen','Front Kitchen','Front Living','Mid-Bunk','Couples / Non-Bunkhouse'],
               'Fifth Wheel':['Bunkhouse','Toy Hauler','Rear Living','Rear Kitchen','Front Kitchen','Front Living','Mid-Bunk','Couples / Non-Bunkhouse'],
               'Truck Camper':['Hard-Side','Pop-Up']}.get(category,[])
    # Show the dealer's useful filter vocabulary even when the current scope has zero units of a type.
    # This keeps Toy Hauler and other expected choices from disappearing between lots.
    return ['Any']+preferred

def available_brands(evaluated):
    return ['Any']+sorted({rv.get('manufacturer') for rv,_ in evaluated if rv.get('manufacturer')})
