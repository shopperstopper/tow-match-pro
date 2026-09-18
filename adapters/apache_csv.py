"""Normalize the current Apache scraper CSV into Tow Match Pro inventory records.

This importer is intentionally conservative: it repairs representation problems but never
manufactures missing RV specifications. The VDP adapter remains the preferred acquisition path.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
import pandas as pd

# Temporary title hints for the sample scraper, whose catalog-link category detection can miss
# fifth wheels. The live VDP adapter identifies category from the VDP itself.
FIFTH_HINTS=(
    'grande ronde','glacier peak','seismic 4125','reflection 3','solitude','influence',
    'alliance avenue','paradigm','valor 3','cougar 2','cougar 3','triton 3451',
    'arctic fox rapid','arctic fox nxt 295','arctic fox nxt 325','arctic fox nxt 365',
    'flagstaff classic 290',
)

MANUFACTURER_PREFIXES=(
    'Adventurer Manufacturing Inc.','Forest River RV','Winnebago Industries Towables','Keystone RV',
    'Coachmen RV','Grand Design','Outdoors RV','Northwood','nuCamp RV','Dutchmen RV','CrossRoads RV',
    'Heartland','Jayco','Lance','TAXA Outdoors','Bigfoot Industries','Northern Lite','Host Campers',
)

def infer_manufacturer(title):
    s=re.sub(r'^(?:New|Used)\s+(?:19|20)\d{2}\s+','',str(title or ''),flags=re.I)
    low=s.lower()
    for name in MANUFACTURER_PREFIXES:
        if low.startswith(name.lower()+' ') or low==name.lower(): return name
    return None

CAMPER_HINTS=(
    'truck camper','lance truck campers','squire truck campers','cirrus ','adventurer 65',
    'adventurer 80','scout tuktut','scout yoho','scout olympic','scout kenai',
    'arctic fox camper','northern lite ','bigfoot 1500 series','host campers',
)

def _num(v):
    if v is None or (isinstance(v,float) and pd.isna(v)): return None
    try: return float(v)
    except (TypeError,ValueError):
        m=re.search(r'-?[\d,.]+',str(v))
        return float(m.group(0).replace(',','')) if m else None

def normalize_length(v)->Optional[float]:
    x=_num(v)
    if x is None: return None
    if x > 80 and float(x).is_integer():
        digits=str(int(x))
        if len(digits)==3:
            ft,inch=int(digits[:2]),int(digits[2])
            if 10<=ft<=60 and 0<=inch<=11: return round(ft+inch/12,3)
        if len(digits)==4:
            ft,inch=int(digits[:2]),int(digits[2:])
            if 10<=ft<=60 and 0<=inch<=11: return round(ft+inch/12,3)
    return x

def normalize_category(title, supplied, source_url=None)->str:
    t=str(title or '').lower(); s=str(supplied or '').lower(); u=str(source_url or '')
    # Apache's product URL taxonomy uses trailing -5 for fifth-wheel inventory.
    # Treat it as dealer-source category evidence; this recovers units whose titles omit 'fifth wheel'.
    if re.search(r'-5(?:$|[?#])', u): return 'Fifth Wheel'
    if 'fifth wheel' in t or '5th wheel' in t or any(x in t for x in FIFTH_HINTS): return 'Fifth Wheel'
    if 'truck camper' in t or any(x in t for x in CAMPER_HINTS): return 'Truck Camper'
    if s in ('fifth wheel','truck camper','travel trailer'): return s.title() if s!='fifth wheel' else 'Fifth Wheel'
    return 'Travel Trailer'


def infer_rv_style(title, category, source_url=None):
    """Sales shopping style, separate from interior floorplan."""
    t=str(title or '').lower(); u=str(source_url or '')
    if category=='Truck Camper':
        if any(x in t for x in ('pop-up','pop up','cirrus 620','cirrus 820','scout ')):
            return 'Pop-Up'
        return 'Hard-Side'
    if category=='Travel Trailer':
        # Apache dealer taxonomy -28 identifies towable toy-hauler inventory.
        if re.search(r'-28(?:$|[?#])', u) or 'toy hauler' in t or any(x in t for x in ('seismic','valor','triton')):
            return 'Toy Hauler'
        if 'aliner' in t or 'a-frame' in t or 'a frame' in t:
            return 'A-Frame / Folding / Pop Up'
        if re.search(r'\bnucamp rv tab\b', t) or 'teardrop' in t:
            return 'Teardrop'
        return 'Conventional Travel Trailer'
    if category=='Fifth Wheel':
        if 'toy hauler' in t or any(x in t for x in ('seismic','valor','triton')):
            return 'Toy Hauler'
        return 'Conventional Fifth Wheel'
    return None


def infer_floorplan(title, category, source_url=None):
    """Interior/layout shopping attribute. Never affects tow qualification."""
    t=str(title or '').lower()
    if category not in ('Travel Trailer','Fifth Wheel'):
        return None
    if ('bunkhouse' in t or 'bunk house' in t or 'hidden bunk' in t or
        re.search(r'\d(?:bh|bhs|sbh|brds|bks)(?:[a-z]{0,2})?(?:\b|$)', t)):
        return 'Bunkhouse'
    if 'mid bunk' in t or 'mid-bunk' in t:
        return 'Mid-Bunk'
    if 'front living' in t or re.search(r'\d(?:fl|fls)(?:[a-z]{0,2})?(?:\b|$)', t): return 'Front Living'
    if 'front kitchen' in t or re.search(r'\d(?:fk|cfk)(?:[a-z]{0,2})?(?:\b|$)', t): return 'Front Kitchen'
    if 'rear kitchen' in t or re.search(r'\d(?:rk|rks|srk)(?:[a-z]{0,2})?(?:\b|$)', t): return 'Rear Kitchen'
    if 'rear living' in t or re.search(r'\d(?:rl|rls)(?:[a-z]{0,2})?(?:\b|$)', t): return 'Rear Living'
    return 'Couples / Non-Bunkhouse'


def infer_major_type(title, category, source_url=None):
    """Backward-compatible legacy field; new UI uses rv_style + floorplan."""
    style=infer_rv_style(title,category,source_url)
    if category=='Truck Camper' or style=='Toy Hauler':
        return style
    return infer_floorplan(title,category,source_url)

def normalize_location(v):
    s=str(v or '').strip()
    return {'Kitsap / Poulsbo':'Poulsbo, WA','Portland / Clackamas':'Portland, OR',
            'Everett':'Everett, WA','Tacoma':'Tacoma, WA','Unassigned':None}.get(s,s or None)

def normalize_status(v):
    s=str(v or '').strip().lower()
    if s=='on lot': return 'On Lot'
    if any(x in s for x in ('inbound','incoming','pipeline','on order','in transit')): return 'Pipeline'
    return str(v).strip() or None

def normalize_price(v):
    n=_num(v)
    # A $199 first-dollar regex hit is not a credible RV selling price. Preserve unknown rather
    # than displaying it as dealer price. The VDP parser uses labeled price extraction instead.
    if n is None or n < 1000: return None
    return int(round(n))

def load_apache_scraper_csv(path: str|Path):
    df=pd.read_csv(path); records=[]
    for _,r in df.iterrows():
        title=str(r.get('Model','')).strip()
        source_url=None if pd.isna(r.get('URL')) else str(r.get('URL')).strip()
        category=normalize_category(title,r.get('Category'),source_url)
        records.append({
            'display_title':title,
            'rv_category':category,
            'major_type':infer_major_type(title,category,source_url),
            'rv_style':infer_rv_style(title,category,source_url),
            'floorplan':infer_floorplan(title,category,source_url),
            'manufacturer':infer_manufacturer(title),
            'condition':str(r.get('Condition') or '').strip() or ('Used' if title.lower().startswith('used ') else 'New'),
            'location':normalize_location(r.get('Location')),
            'inventory_status':normalize_status(r.get('Status')),
            'sellable':True,
            'pipeline_stage':'Incoming / In Transit' if normalize_status(r.get('Status'))=='Pipeline' else None,
            'overall_length_ft':normalize_length(r.get('Length')),
            'uvw_lb':_num(r.get('DryWeight')),
            'gvwr_lb':_num(r.get('GVWR')),
            'published_hitch_pin_lb':_num(r.get('HitchWeight')),
            'price_usd':normalize_price(r.get('Price')),
            'image_url':None if pd.isna(r.get('Image')) else str(r.get('Image')).strip(),
            'source_url':source_url,
            'source_category':None if pd.isna(r.get('Category')) else str(r.get('Category')),
        })
    return records
