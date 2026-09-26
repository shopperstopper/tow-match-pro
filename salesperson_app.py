from __future__ import annotations
import re
from io import BytesIO
import base64

import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
try:
    import pytesseract
except ImportError:
    pytesseract = None
try:
    from streamlit_back_camera_input import back_camera_input
except ImportError:
    back_camera_input = None

from tow_match.models import MatchStatus
from interface_logic import (load_inventory, evaluate_inventory, filter_matches, search_specific_unit, apply_scope,
                             available_lots, available_major_types, available_brands, sort_matches, available_rv_styles, available_floorplans)
from vehicle_data.models import VehicleAcquisitionInput
from vehicle_data.acquisition import acquire_vehicle, to_engine_vehicle_state
from vehicle_data.nhtsa_vpic import NHTSAVpicClient
from vehicle_data.manufacturer_service import ManufacturerCapabilityService
from dealer_config import DEALER_NAME, HOME_LOT

APP_TITLE='Tow Match Pro'
CATEGORIES=['Travel Trailer','Fifth Wheel','Truck Camper']
SCOPES=['This Lot','All Dealer Locations','Pipeline']


VIN_PATTERN = re.compile(r"[A-HJ-NPR-Z0-9]{17}")

try:
    from pyzbar.pyzbar import decode as decode_barcode
except Exception:
    decode_barcode = None


def _photo_to_image(photo) -> Image.Image | None:
    try:
        if isinstance(photo, Image.Image):
            return photo.convert("RGB")
        if isinstance(photo, str):
            raw = photo.split(",", 1)[1] if photo.startswith("data:") and "," in photo else photo
            photo = BytesIO(base64.b64decode(raw))
        elif isinstance(photo, (bytes, bytearray)):
            photo = BytesIO(photo)
        return Image.open(photo).convert("RGB")
    except Exception:
        return None


def _valid_vin_from_barcode_text(raw: str) -> str | None:
    """J1877 uses Code 39 and may prefix the 17-character VIN with data identifier I."""
    from vehicle_data.acquisition import vin_is_valid
    text = re.sub(r"[^A-Z0-9*]", "", (raw or "").upper()).strip("*")
    candidates = []
    if len(text) == 18 and text.startswith("I"):
        candidates.append(text[1:])
    if len(text) == 17:
        candidates.append(text)
    # Some readers return framing/data characters around the payload. Never guess: only
    # accept a unique checksum-valid 17-character window.
    for i in range(max(0, len(text) - 16)):
        candidates.append(text[i:i+17])
    valid = []
    for c in candidates:
        if VIN_PATTERN.fullmatch(c) and vin_is_valid(c) and c not in valid:
            valid.append(c)
    return valid[0] if len(valid) == 1 else None


def extract_vin_from_barcode(image: Image.Image) -> str | None:
    """Fast barcode-first path. A failed decode falls through; it never fabricates a VIN."""
    if decode_barcode is None:
        return None
    # Whole image first. Then broad bands because a barcode occupying more of the decoder's
    # input is easier to read. These are cheap barcode operations, not OCR sweeps.
    regions = [image]
    w, h = image.size
    regions += [
        image.crop((0, int(.18*h), w, int(.72*h))),
        image.crop((0, int(.28*h), w, int(.62*h))),
    ]
    seen = set()
    for region in regions:
        for angle in (0, -6, 6):
            test = region if angle == 0 else region.rotate(angle, expand=True, fillcolor="white")
            try:
                results = decode_barcode(test)
            except Exception:
                results = []
            for result in results:
                try:
                    raw = result.data.decode("ascii", errors="ignore")
                except Exception:
                    raw = str(result.data)
                vin = _valid_vin_from_barcode_text(raw)
                if vin:
                    seen.add(vin)
    return next(iter(seen)) if len(seen) == 1 else None


def _ocr_vin_candidate_from_line(line: str) -> str | None:
    """Extract a VIN-shaped string only from a line Tesseract itself identified as VIN."""
    u = (line or "").upper()
    m = re.search(r"V[I1L]N\s*[:;]?\s*(.*)", u)
    if not m:
        return None
    raw = re.sub(r"[^A-Z0-9]", "", m.group(1))
    # The VIN is the first VIN-like payload after the printed VIN label.
    return raw[:17] if len(raw) >= 17 else None


def _safe_repair_labeled_vin(candidates: list[str]) -> str | None:
    """Repair only tightly constrained OCR ambiguity; never free-form guess a VIN."""
    from vehicle_data.acquisition import vin_is_valid
    legal = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    exact = {c for c in candidates if VIN_PATTERN.fullmatch(c) and vin_is_valid(c)}
    if len(exact) == 1:
        return next(iter(exact))
    if len(exact) > 1:
        return None

    # Strong consensus case: two or more labeled reads agree on positions 2-17.
    # Door-label perspective commonly turns the leading '1' into 4/T/7. We may repair
    # that one glyph only when the remainder is independently stable and checksum confirms it.
    tails = {}
    for c in candidates:
        if len(c) == 17:
            tails.setdefault(c[1:], []).append(c)
    for tail, group in tails.items():
        if len(group) >= 2:
            repaired = "1" + tail
            if VIN_PATTERN.fullmatch(repaired) and vin_is_valid(repaired):
                return repaired

    # A single high-quality labeled read may have one OCR glyph error. Restrict repairs to
    # well-observed camera/OCR confusions and require a UNIQUE checksum-valid result.
    confusion = {
        "I": "1", "L": "1", "O": "0", "Q": "0", "Z": "2", "S": "5",
        "G": "6", "B": "8", "T": "7", "4": "1", "7": "1",
    }
    repaired = set()
    for c in candidates:
        if len(c) != 17:
            continue
        for i, ch in enumerate(c):
            for repl in confusion.get(ch, ""):
                x = c[:i] + repl + c[i+1:]
                if VIN_PATTERN.fullmatch(x) and vin_is_valid(x):
                    repaired.add(x)
    return next(iter(repaired)) if len(repaired) == 1 else None


def extract_vin_from_photo(photo) -> str | None:
    """Build 23G: barcode first, then fast label-aware deskewed OCR with safe validation."""
    image = _photo_to_image(photo)
    if image is None:
        return None

    vin = extract_vin_from_barcode(image)
    if vin:
        return vin
    if pytesseract is None:
        return None

    from pathlib import Path
    if Path("/usr/bin/tesseract").exists():
        pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

    # Real certification labels are commonly photographed at an angle. Rather than the
    # Build 23E brute-force crop/threshold grid, use a small bounded set of deskew attempts.
    # Stop immediately on a checksum-valid labeled VIN.
    attempts = ((-13, 2.3), (0, 2.0), (13, 2.3), (-8, 2.1), (8, 2.1))
    candidates = []
    for angle, contrast in attempts:
        work = image if angle == 0 else image.rotate(angle, expand=True, fillcolor="white")
        scale = min(3.0, 2200 / max(1, work.width))
        if scale > 1:
            work = work.resize((int(work.width*scale), int(work.height*scale)))
        gray = ImageEnhance.Contrast(ImageOps.grayscale(work)).enhance(contrast).filter(ImageFilter.SHARPEN)
        try:
            text = pytesseract.image_to_string(
                gray,
                config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:",
            )
        except Exception:
            continue
        for line in text.splitlines():
            c = _ocr_vin_candidate_from_line(line)
            if c:
                candidates.append(c)
        repaired = _safe_repair_labeled_vin(candidates)
        if repaired:
            return repaired
    return _safe_repair_labeled_vin(candidates)


def init_state():
    # Production-safe defaults: never seed a real Tow Match with the development Expedition.
    defaults={
        'vehicle_ready':False,'payload':None,'tow_rating':None,'fw_rating':None,'vin':'',
        'adults':2,'children':0,'pets':0.0,'cargo':150.0,'category':'Travel Trailer',
        'acquisition':None,'verify_target':None,'matched_category':None,
        'edit_people_open':False,'edit_vehicle_open':False,
        'edit_payload':None,'edit_tow_rating':None,'edit_fw_rating':None,
        'vin_camera_open':False,'vin_scan_message':None,
    }
    for cat in CATEGORIES:
        slug=cat.lower().replace(' ','_')
        defaults[f'scope_{slug}']='This Lot'
        defaults[f'lot_{slug}']=''
        defaults[f'condition_{slug}']='Any'
        defaults[f'length_{slug}']='Any'
        defaults[f'brand_{slug}']='Any'
        defaults[f'major_type_{slug}']='Any'
        defaults[f'rv_style_{slug}']='Any'
        defaults[f'floorplan_{slug}']='Any'
        defaults[f'search_{slug}']=''
        defaults[f'status_{slug}']='All'
        defaults[f'sort_{slug}']='Recommended'
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
    with a: st.title('Tow Match Pro')
    with b:
        if st.button('New Tow Match',use_container_width=True): reset()

    with st.expander('1 · Tow Vehicle',expanded=not st.session_state.vehicle_ready):
        if not st.session_state.vehicle_ready:
            # Apply a scanned VIN before the VIN widget is instantiated on this rerun.
            # This avoids Streamlit's widget-state mutation error.
            if st.session_state.get('apply_scanned_vin'):
                st.session_state.vin=st.session_state.pop('apply_scanned_vin')
                st.session_state.pop('vin_camera',None)
            st.caption('Scan or enter the VIN to identify the tow vehicle.')
            c1,c2=st.columns(2)
            with c1:
                st.text_input('VIN',key='vin',placeholder='17-character VIN')
                if not st.session_state.vin_camera_open:
                    if st.button('📷 Scan VIN',key='open_vin_camera'):
                        st.session_state.vin_camera_open=True
                        st.session_state.vin_scan_message=None
                        st.rerun()
                else:
                    st.markdown('**VIN camera**')
                    st.caption('Rear camera is open. Photograph the vehicle certification label so the VIN area is reasonably clear.')
                    if st.button('✕ Close Camera',key='close_vin_camera_top',use_container_width=True):
                        st.session_state.vin_camera_open=False
                        st.session_state.vin_scan_message=None
                        st.rerun()
                    st.info('**SCAN VEHICLE LABEL — point the camera at the certification label and take the photo.**')
                    if back_camera_input is not None:
                        vin_photo=back_camera_input()
                    else:
                        st.caption('Rear-camera component is unavailable. Use the camera control below and switch to the rear camera if needed.')
                        vin_photo=st.camera_input('Take VIN Photo',key='vin_camera',help='Photograph the vehicle certification label with the VIN area reasonably clear.',resolution='1080p')
                    if vin_photo is not None:
                        if pytesseract is None:
                            st.error('VIN reader is not installed in this deployment. Reboot the app after deploying requirements.txt and packages.txt.')
                            extracted_vin=None
                        else:
                            with st.spinner('Reading VIN…'):
                                extracted_vin=extract_vin_from_photo(vin_photo)
                        if extracted_vin:
                            st.session_state.apply_scanned_vin=extracted_vin
                            st.session_state.vin_camera_open=False
                            st.session_state.vin_scan_message=f'VIN read: {extracted_vin}'
                            st.rerun()
                        else:
                            st.warning("VIN wasn't recognized. Retake the photo or enter the VIN manually.")
                            r1,r2=st.columns(2)
                            with r1:
                                if st.button('↻ Retake Photo',key='retake_vin_photo',use_container_width=True):
                                    st.session_state.vin_scan_message=None
                                    st.rerun()
                            with r2:
                                if st.button('✕ Close Camera',key='close_vin_camera_bottom',use_container_width=True):
                                    st.session_state.vin_camera_open=False
                                    st.session_state.vin_scan_message=None
                                    st.rerun()
                if st.session_state.get('vin_scan_message'):
                    st.success(st.session_state.vin_scan_message)
                    st.session_state.vin_scan_message=None
                st.caption('Enter the payload from the yellow door label.')
                st.number_input('Yellow-label payload (lb)',min_value=0,step=1,value=None,key='payload',placeholder='Payload shown on door label')
            with c2:
                st.number_input('Adults 13+',min_value=0,max_value=10,step=1,key='adults')
                st.number_input('Children 2–12',min_value=0,max_value=10,step=1,key='children')
            d1,d2,d3=st.columns(3)
            with d1: st.number_input('Pets combined (lb)',min_value=0,step=10,key='pets')
            with d2: st.number_input('Truck cargo & gear (lb)',min_value=0,step=25,key='cargo')
            with d3: st.segmented_control('RV Category',CATEGORIES,key='category')
            if st.button('Find Tow Matches',type='primary',use_container_width=True):
                from vehicle_data.acquisition import normalize_vin, vin_is_valid
                entered_vin=normalize_vin(st.session_state.vin)
                has_payload=st.session_state.payload is not None
                if not entered_vin and not has_payload:
                    st.error('Enter or paste the VIN, or enter the yellow-label payload.')
                elif entered_vin and not vin_is_valid(entered_vin) and not has_payload:
                    st.error('That VIN could not be validated. Check the VIN, or enter the yellow-label payload to continue without it.')
                else:
                    # Do not mutate the VIN widget's session-state value after Streamlit instantiates it.
                    # acquire_vehicle() normalizes/extracts pasted values such as 'VIN: 1FT...' downstream.
                    _,result,_=acquire_for_category(st.session_state.category,live_lookup=True)
                    st.session_state.acquisition=result; st.session_state.vehicle_ready=True
                    st.session_state.matched_category=st.session_state.category; st.session_state.verify_target=None
                    st.rerun()
        else:
            st.caption('Vehicle identity is locked for this Tow Match. Use **New Tow Match** for a different vehicle.')
            st.write(f"VIN: **{st.session_state.vin or 'Not entered'}**")

    if not st.session_state.vehicle_ready:
        st.info('**Scan or enter the VIN to identify the tow vehicle.** Add the payload from the yellow door label to finalize payload qualification.')
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
    rating_label='Fifth-wheel tow rating' if category=='Fifth Wheel' else 'Conventional tow rating'
    rating_value=vehicle.fifth_wheel_tow_rating_lb if category=='Fifth Wheel' else vehicle.tow_rating_lb
    st.markdown(f'''<div class="tm-vehicle"><b>Active Tow Match</b> · {identity_text} · Payload <b>{fmt_num(vehicle.payload_lb)}</b> · {rating_label} <b>{fmt_num(rating_value)}</b><br><span class="tm-muted">People {vehicle.occupant_weight_lb:,.0f} lb · Pets {vehicle.pets_weight_lb:,.0f} lb · Truck gear {vehicle.truck_cargo_lb:,.0f} lb</span></div>''',unsafe_allow_html=True)
    e1,e2,_=st.columns([1.25,1.25,5])
    with e1:
        if st.button('Edit People & Cargo',use_container_width=True):
            st.session_state.edit_people_open=not st.session_state.edit_people_open
            st.session_state.edit_vehicle_open=False
    with e2:
        if st.button('Correct Vehicle Data',use_container_width=True):
            opening=not st.session_state.edit_vehicle_open
            st.session_state.edit_vehicle_open=opening
            st.session_state.edit_people_open=False
            if opening:
                # Always seed the correction form from the CURRENT effective vehicle facts.
                # Streamlit otherwise preserves stale widget state from an earlier opening.
                st.session_state.edit_payload=int(round(vehicle.payload_lb)) if vehicle.payload_lb is not None else None
                st.session_state.edit_tow_rating=int(round(vehicle.tow_rating_lb)) if vehicle.tow_rating_lb is not None else None
                st.session_state.edit_fw_rating=int(round(vehicle.fifth_wheel_tow_rating_lb)) if vehicle.fifth_wheel_tow_rating_lb is not None else None

    if st.session_state.edit_people_open:
        with st.container(border=True):
            st.markdown('**Edit People & Cargo**')
            with st.form('edit_people_cargo'):
                pc1,pc2,pc3,pc4=st.columns(4)
                with pc1: adults=st.number_input('Adults 13+',0,10,int(st.session_state.adults),1)
                with pc2: children=st.number_input('Children 2–12',0,10,int(st.session_state.children),1)
                with pc3: pets=st.number_input('Pets combined (lb)',min_value=0,value=int(round(st.session_state.pets)),step=10)
                with pc4: cargo=st.number_input('Truck cargo & gear (lb)',min_value=0,value=int(round(st.session_state.cargo)),step=25)
                if st.form_submit_button('Update Tow Matches',type='primary'):
                    st.session_state.adults=adults; st.session_state.children=children
                    st.session_state.pets=pets; st.session_state.cargo=cargo
                    st.session_state.edit_people_open=False
                    st.rerun()

    if st.session_state.edit_vehicle_open:
        with st.container(border=True):
            st.markdown('**Correct Vehicle Data**')
            st.caption(f"VIN / vehicle identity locked: {st.session_state.vin or identity_text}")
            st.caption('Current effective values are shown below. Leave an unknown rating blank.')
            with st.form('correct_vehicle_data'):
                vc1,vc2,vc3=st.columns(3)
                with vc1: payload=st.number_input('Yellow-label payload (lb)',min_value=0,step=1,placeholder='Unknown',key='edit_payload')
                with vc2: tow=st.number_input('Conventional tow rating (lb)',min_value=0,step=100,placeholder='Unknown',key='edit_tow_rating')
                with vc3: fw=st.number_input('Fifth-wheel rating (lb)',min_value=0,step=100,placeholder='Unknown',key='edit_fw_rating')
                if st.form_submit_button('Correct & Recalculate',type='primary'):
                    st.session_state.payload=payload
                    st.session_state.tow_rating=tow
                    st.session_state.fw_rating=fw
                    st.session_state.edit_vehicle_open=False
                    st.rerun()
    for warning in (prior.warnings if prior else []): st.caption('Vehicle note: '+warning)
    preliminary_needs=[]
    if vehicle.payload_lb is None: preliminary_needs.append('yellow-label payload')
    active_rating=vehicle.fifth_wheel_tow_rating_lb if category=='Fifth Wheel' else vehicle.tow_rating_lb
    if category in ('Travel Trailer','Fifth Wheel') and active_rating is None:
        preliminary_needs.append('vehicle-specific '+('fifth-wheel tow rating' if category=='Fifth Wheel' else 'conventional tow rating'))
    if preliminary_needs:
        st.info('**Preliminary matches — verify payload and tow rating when available.**')

    selected_category=st.segmented_control('RV Category',CATEGORIES,key='category') or category
    if selected_category != category:
        st.session_state.matched_category=selected_category
        st.session_state.verify_target=None
        st.rerun()

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
    status_key=f'status_{slug}'
    st.caption('Click a status tile to isolate those results. Click Total Tow Matches to show all.')
    m1,m2,m3,m4=st.columns(4)
    with m1:
        if st.button(f'Total Tow Matches  ·  {base_total}',key=f'tile_total_{slug}',use_container_width=True): st.session_state[status_key]='All'; st.rerun()
    with m2:
        if st.button(f'Match  ·  {base_counts[MatchStatus.MATCH]}',key=f'tile_match_{slug}',use_container_width=True): st.session_state[status_key]='Match'; st.rerun()
    with m3:
        if st.button(f'Verify  ·  {base_counts[MatchStatus.PRELIMINARY]}',key=f'tile_verify_{slug}',use_container_width=True): st.session_state[status_key]='Verify'; st.rerun()
    with m4:
        if st.button(f'Unable  ·  {base_counts[MatchStatus.UNABLE]}',key=f'tile_unable_{slug}',use_container_width=True): st.session_state[status_key]='Unable'; st.rerun()

    st.markdown('#### Filter & Sort Tow Matches')
    c1,c2,c3=st.columns(3)
    with c1: condition=st.selectbox('Condition',['Any','New','Used'],key=f'condition_{slug}')
    with c2: rv_style=st.selectbox('RV Style',available_rv_styles(inventory,category),key=f'rv_style_{slug}')
    with c3: floorplan=st.selectbox('Floorplan',available_floorplans(inventory,category),key=f'floorplan_{slug}',disabled=(category=='Truck Camper'))
    c4,c5,c6=st.columns(3)
    with c4: length=st.selectbox('Length',['Any','Under 20 ft','20–25 ft','25–30 ft','30–35 ft','35+ ft'],key=f'length_{slug}')
    brands=available_brands(qualified_scope)
    if st.session_state.get(f'brand_{slug}') not in brands: st.session_state[f'brand_{slug}']='Any'
    with c5: brand=st.selectbox('Brand',brands,key=f'brand_{slug}')
    with c6: sort_by=st.selectbox('Sort',['Recommended','Heaviest first','Lightest first','Longest first','Shortest first','Price low to high','Price high to low'],key=f'sort_{slug}')

    shown=filter_matches(qualified_scope,condition,length,'Any',brand,status=st.session_state.get(status_key,'All'),rv_style=rv_style,floorplan=floorplan)
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

    shown=sort_matches(shown,sort_by if not search else 'Recommended')
    if not shown:
        if not search: st.warning('No Tow Matches meet the current filters.')
        return

    for rv,res in shown:
        unit_key=re.sub(r'\W+','_',rv['source_url'] or rv['display_title'])[-100:]
        # Re-evaluate the displayed unit against the CURRENT effective vehicle state.
        # This keeps Why This Matches synchronized after Correct Vehicle Data edits.
        refreshed = evaluate_inventory([rv], vehicle, category)
        if refreshed:
            _, res = refreshed[0]
        with st.container(border=True):
            left,mid,right=st.columns([1.3,4.8,1.5])
            with left:
                if rv['image_url'] and rv['image_url']!='nan': st.image(rv['image_url'],use_container_width=True)
            with mid:
                stock = str(rv.get('stock_number') or '').strip()
                if stock.lower() == 'nan': stock = ''
                title = f"Stock # {stock} · {rv['display_title']}" if stock else rv['display_title']
                st.markdown(f"### {title}")
                bits=[rv['rv_category'],f"{rv['overall_length_ft']:.1f} ft" if rv['overall_length_ft'] else None,rv['condition'],rv['location'],rv['inventory_status']]
                st.write(' · '.join(x for x in bits if x))
                facts=[]
                if res.estimated_loaded_lb is not None: facts.append(f"Est. loaded **{fmt_num(res.estimated_loaded_lb)}**")
                if rv.get('price_usd') is not None: facts.append(f"Price **${rv['price_usd']:,.0f}**")
                if facts: st.write(' · '.join(facts))
                st.markdown(f"**{status_label(res.status)}**")
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
                    if category=='Travel Trailer' and res.qualification_load_lb is not None and res.upper_verify_load_lb is not None:
                        st.write(f"Normal tongue estimate (13%): **{fmt_num(res.qualification_load_lb)}** · Upper tongue estimate (15%): **{fmt_num(res.upper_verify_load_lb)}** · Available: **{fmt_num(res.available_payload_lb)}**")
                        if res.status==MatchStatus.PRELIMINARY and res.available_payload_lb is not None and res.qualification_load_lb<=res.available_payload_lb<res.upper_verify_load_lb: st.warning('Verify: qualifies at the normal 13% tongue estimate, but could exceed available payload if loaded tongue approaches 15%.')
                    elif category=='Fifth Wheel' and res.qualification_load_lb is not None and res.upper_verify_load_lb is not None:
                        st.write(f"Normal pin estimate (20%): **{fmt_num(res.qualification_load_lb)}** · Upper pin estimate (25%): **{fmt_num(res.upper_verify_load_lb)}** · Available: **{fmt_num(res.available_payload_lb)}**")
                        if res.status==MatchStatus.PRELIMINARY and res.available_payload_lb is not None and res.qualification_load_lb<=res.available_payload_lb<res.upper_verify_load_lb: st.warning('Verify: qualifies at the normal 20% pin estimate, but could exceed available payload if loaded pin approaches 25%.')
                    if res.reserve_lb is not None: st.write(f"Payload reserve at qualification estimate: **{fmt_num(res.reserve_lb)}**")
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
