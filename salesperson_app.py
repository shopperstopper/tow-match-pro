from __future__ import annotations
import re
import streamlit as st

from tow_match.models import MatchStatus
from interface_logic import (load_inventory, evaluate_inventory, filter_matches, search_specific_unit, apply_scope,
                             available_lots, available_major_types, available_brands)
from vehicle_data.models import VehicleAcquisitionInput
from vehicle_data.acquisition import acquire_vehicle, to_engine_vehicle_state
from vehicle_data.nhtsa_vpic import NHTSAVpicClient
from vehicle_data.manufacturer_service import ManufacturerCapabilityService
from dealer_config import DEALER_NAME, HOME_LOT

APP_TITLE='Tow Match Pro'
CATEGORIES=['Travel Trailer','Fifth Wheel','Truck Camper']
SCOPES=['This Lot','All Dealer Locations','Pipeline']


def init_state():
    # Production-safe defaults: never seed a real Tow Match with the development Expedition.
    defaults={
        'vehicle_ready':False,'payload':None,'tow_rating':None,'fw_rating':None,'vin':'',
        'adults':2,'children':0,'pets':0.0,'cargo':150.0,'category':'Travel Trailer',
        'acquisition':None,'verify_target':None,'matched_category':None,
    }
    for cat in CATEGORIES:
        slug=cat.lower().replace(' ','_')
        defaults[f'scope_{slug}']='This Lot'
        defaults[f'lot_{slug}']=''
        defaults[f'condition_{slug}']='Any'
        defaults[f'length_{slug}']='Any'
        defaults[f'brand_{slug}']='Any'
        defaults[f'major_type_{slug}']='Any'
        defaults[f'search_{slug}']=''
    for k,v in defaults.items(): st.session_state.setdefault(k,v)


def reset():
    for k in list(st.session_state.keys()): del st.session_state[k]
    st.rerun()


def fmt_num(x): return '—' if x is None else f'{x:,.0f} lb'

def status_label(s):
    if s==MatchStatus.MATCH: return '✓ MATCH'
    if s==MatchStatus.PRELIMINARY: return '△ VERIFY'
    if s==MatchStatus.UNABLE: return '⚠ UNABLE TO VERIFY'
    return '✕ NOT A MATCH'


def acquisition_input(category):
    hitch=100 if category in ('Travel Trailer','Truck Camper') else 200
    return VehicleAcquisitionInput(
        vin=st.session_state.vin or None,
        payload_label_lb=st.session_state.payload,
        conventional_tow_rating_lb=st.session_state.tow_rating,
        fifth_wheel_tow_rating_lb=st.session_state.fw_rating,
        occupant_weight_lb=st.session_state.adults*200+st.session_state.children*100,
        pets_weight_lb=st.session_state.pets,
        truck_cargo_lb=st.session_state.cargo,
        hitch_hardware_lb=hitch,
    )


def acquire_for_category(category, live_lookup=True):
    inp=acquisition_input(category)
    result=acquire_vehicle(
        inp,
        vpic_client=NHTSAVpicClient(timeout=5) if live_lookup and inp.vin else None,
        manufacturer_provider=ManufacturerCapabilityService(),
    )
    return inp,result,to_engine_vehicle_state(inp,result)


def category_key(prefix,category): return prefix+'_'+category.lower().replace(' ','_')


def main():
    st.set_page_config(page_title=APP_TITLE,page_icon='🚐',layout='wide')
    init_state()
    st.markdown('''<style>
    .block-container{padding-top:1.2rem;max-width:1500px}.tm-muted{color:#666;font-size:.9rem}
    .tm-vehicle{padding:.65rem 1rem;border:1px solid #ddd;border-radius:10px;background:#fafafa;margin-bottom:.8rem}
    div[data-testid="stMetric"]{border:1px solid #e5e5e5;padding:.5rem;border-radius:10px}
    </style>''',unsafe_allow_html=True)

    a,b=st.columns([6,1])
    with a: st.title('Tow Match Pro'); st.caption(f'{DEALER_NAME} · Salesperson Pilot · Home lot: {HOME_LOT}')
    with b:
        if st.button('New Tow Match',use_container_width=True): reset()

    with st.expander('1 · Tow Vehicle',expanded=not st.session_state.vehicle_ready):
        st.caption('Start with the yellow-label payload. Type the VIN if available. Tow rating may be left blank.')
        c1,c2,c3=st.columns(3)
        with c1:
            st.text_input('VIN (optional)',key='vin',placeholder='17-character VIN')
            with st.popover('📷 Open camera'):
                vin_photo=st.camera_input('Photograph VIN / vehicle label',key='vin_camera')
                if vin_photo is not None:
                    st.caption('Photo captured. For this pilot, read/type the 17-character VIN above; automatic VIN text extraction is not yet enabled.')
            st.number_input('Yellow-label payload (lb)',min_value=0.0,step=1.0,value=None,key='payload',placeholder='Required for useful matching')
        with c2:
            st.number_input('Conventional tow rating (lb, if already known)',min_value=0.0,step=100.0,value=None,key='tow_rating',placeholder='Tow Match will try to resolve it')
            st.number_input('Fifth-wheel rating (lb, if already known)',min_value=0.0,step=100.0,value=None,key='fw_rating',placeholder='Leave blank if unknown')
        with c3:
            st.number_input('Adults 13+',min_value=0,max_value=10,step=1,key='adults')
            st.number_input('Children 2–12',min_value=0,max_value=10,step=1,key='children')
        d1,d2,d3=st.columns(3)
        with d1: st.number_input('Pets combined (lb)',min_value=0.0,step=10.0,key='pets')
        with d2: st.number_input('Truck cargo & gear (lb)',min_value=0.0,step=25.0,key='cargo')
        with d3: st.segmented_control('RV Category',CATEGORIES,key='category')
        if st.button('Find Tow Matches',type='primary',use_container_width=True):
            if st.session_state.payload is None:
                st.error('Enter the yellow-label payload number to start a useful Tow Match.')
            else:
                _,result,_=acquire_for_category(st.session_state.category,live_lookup=True)
                st.session_state.acquisition=result
                st.session_state.vehicle_ready=True
                st.session_state.matched_category=st.session_state.category
                st.session_state.verify_target=None
                st.rerun()

    if not st.session_state.vehicle_ready:
        st.info('Enter the yellow-label payload and press **Find Tow Matches**. VIN and tow rating can be unknown.')
        return

    category=st.session_state.matched_category or st.session_state.category or 'Travel Trailer'
    inp,acq,vehicle=acquire_for_category(category,live_lookup=False)
    # Preserve identity/facts learned during the initial live acquisition; category recalculation only changes hitch default.
    prior=st.session_state.acquisition
    if prior is not None:
        for name,fact in prior.facts.items():
            if name not in acq.facts: acq.facts[name]=fact
        if prior.identity.vin: acq.identity=prior.identity
        vehicle=to_engine_vehicle_state(inp,acq)

    ident=acq.identity
    identity_text=' '.join(str(x) for x in (ident.year,ident.make,ident.model,ident.trim) if x) or (st.session_state.vin or 'Vehicle')
    st.markdown(f'''<div class="tm-vehicle"><b>Active Tow Match</b> · {identity_text} · Payload <b>{fmt_num(vehicle.payload_lb)}</b> · Conventional tow rating <b>{fmt_num(vehicle.tow_rating_lb)}</b><br><span class="tm-muted">People {vehicle.occupant_weight_lb:,.0f} lb · Pets {vehicle.pets_weight_lb:,.0f} lb · Truck gear {vehicle.truck_cargo_lb:,.0f} lb</span></div>''',unsafe_allow_html=True)
    for warning in (prior.warnings if prior else []): st.caption('Vehicle note: '+warning)

    inventory=load_inventory()
    evaluated=evaluate_inventory(inventory,vehicle,category)
    slug=category.lower().replace(' ','_')

    # Scope is part of where the dealer can sell from, not a customer shopping preference.
    lots=available_lots(inventory,category,'Any')
    lot_key=f'lot_{slug}'
    if lots and st.session_state.get(lot_key) not in lots:
        st.session_state[lot_key]=HOME_LOT if HOME_LOT in lots else lots[0]
    scope=st.segmented_control('Inventory Scope',SCOPES,key=f'scope_{slug}') or 'This Lot'
    lot=st.selectbox('Current lot',lots,key=lot_key) if scope=='This Lot' and lots else st.session_state.get(lot_key)
    qualified_scope=apply_scope(evaluated,scope,lot)

    st.subheader('2 · Tow Matches')
    base_counts={x:sum(1 for _,r in qualified_scope if r.status==x) for x in (MatchStatus.MATCH,MatchStatus.PRELIMINARY,MatchStatus.UNABLE)}
    base_total=sum(base_counts.values())
    m1,m2,m3,m4=st.columns(4)
    m1.metric('Total Tow Matches',base_total); m2.metric('Match',base_counts[MatchStatus.MATCH]); m3.metric('Verify',base_counts[MatchStatus.PRELIMINARY]); m4.metric('Unable',base_counts[MatchStatus.UNABLE])

    st.markdown('#### Filter Tow Matches')
    c1,c2,c3,c4=st.columns(4)
    with c1: condition=st.selectbox('Condition',['Any','New','Used'],key=f'condition_{slug}')
    with c2: major_type=st.selectbox('Major Type',available_major_types(inventory,category),key=f'major_type_{slug}')
    with c3: length=st.selectbox('Length',['Any','Under 20 ft','20–25 ft','25–30 ft','30–35 ft','35+ ft'],key=f'length_{slug}')
    brands=available_brands(qualified_scope)
    if st.session_state.get(f'brand_{slug}') not in brands: st.session_state[f'brand_{slug}']='Any'
    with c4: brand=st.selectbox('Brand',brands,key=f'brand_{slug}')

    shown=filter_matches(qualified_scope,condition,length,major_type,brand)
    st.caption(f'**{len(shown)} of {base_total} Tow Matches shown** after filters.' if len(shown)!=base_total else f'**All {base_total} Tow Matches shown.**')

    search=st.text_input('Specific Unit Search',placeholder='Stock number / model / manufacturer',key=f'search_{slug}')
    if search:
        searched=apply_scope(search_specific_unit(inventory,vehicle,category,search),scope,lot)
        if searched:
            st.caption('Specific Unit Search is independent of the filters above and can show a requested RV even when it is not a Tow Match.')
            shown=searched
        else:
            st.warning('No unit matching that search was found in the selected inventory scope.')
            shown=[]

    order={MatchStatus.MATCH:0,MatchStatus.PRELIMINARY:1,MatchStatus.UNABLE:2,MatchStatus.NOT_MATCH:3}
    shown.sort(key=lambda x:(order.get(x[1].status,9),x[0]['display_title']))
    if not shown:
        if not search: st.warning('No Tow Matches meet the current filters.')
        return

    for rv,res in shown:
        unit_key=re.sub(r'\W+','_',rv['source_url'] or rv['display_title'])[-100:]
        with st.container(border=True):
            left,mid,right=st.columns([1.3,4.8,1.5])
            with left:
                if rv['image_url'] and rv['image_url']!='nan': st.image(rv['image_url'],use_container_width=True)
            with mid:
                st.markdown(f"### {rv['display_title']}")
                bits=[rv['rv_category'],f"{rv['overall_length_ft']:.1f} ft" if rv['overall_length_ft'] else None,rv['condition'],rv['location'],rv['inventory_status']]
                st.write(' · '.join(x for x in bits if x)); st.markdown(f"**{status_label(res.status)}**")
                if res.status==MatchStatus.UNABLE:
                    st.caption('Missing: '+', '.join(res.missing_information))
                elif res.status==MatchStatus.PRELIMINARY and res.missing_information:
                    st.caption('Verify: '+', '.join(res.missing_information[:2]))
                elif res.status==MatchStatus.NOT_MATCH:
                    failed=[g.message for g in res.gates if g.passed is False]
                    st.caption('Excluded: '+('; '.join(failed) if failed else 'Vehicle/RV compatibility gate failed.'))
                with st.expander('Why This Matches' if res.status!=MatchStatus.NOT_MATCH else 'Why This Is Not a Match'):
                    st.write(f"Estimated normal loaded weight: **{fmt_num(res.estimated_loaded_lb)}**")
                    st.write(f"Qualification tongue/pin/load: **{fmt_num(res.qualification_load_lb)}**")
                    if res.reserve_lb is not None: st.write(f"Payload reserve: **{fmt_num(res.reserve_lb)}** · {res.reserve_label or ''}")
                    for g in res.gates:
                        icon='✓' if g.passed is True else '△' if g.passed is None else '✕'
                        st.write(f"{icon} **{g.name}:** {g.message}")
                    for a in res.advisories: st.info(a)
                    if res.assumptions: st.caption('Tow Match assumptions: '+'; '.join(res.assumptions))
            with right:
                st.write('')
                if rv['source_url'] and rv['source_url']!='nan': st.link_button('View RV',rv['source_url'],use_container_width=True)
                if res.status in (MatchStatus.PRELIMINARY,MatchStatus.UNABLE):
                    if st.button('Verify This Match',key='verify_'+unit_key,use_container_width=True):
                        st.session_state.verify_target=unit_key
                if st.session_state.verify_target==unit_key and res.status in (MatchStatus.PRELIMINARY,MatchStatus.UNABLE):
                    # Rule 107: for Unable, show exactly what is missing; do not launch a hunt for it.
                    missing=res.missing_information or ['No additional verification item is identified.']
                    st.info('Needed: '+', '.join(missing))

if __name__=='__main__': main()
