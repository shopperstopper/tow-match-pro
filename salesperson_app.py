from __future__ import annotations
import re
from io import BytesIO
import base64
import numpy as np

import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
try:
    import pytesseract
except ImportError:
    pytesseract = None

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
    # Do not slide through arbitrary barcode data looking for a checksum-valid
    # window: only the exact VIN or J1877's leading I identifier is supported.
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


def _ocr_labeled_windows(line: str) -> list[str]:
    """Only the VIN field's first 17 glyphs; never slide into adjacent label fields.

    The old sliding-window approach accepted e.g. U2AT7KEA31907TYPE when
    the start of the VIN was lost and the neighboring TYPE field was appended.
    """
    u = (line or "").upper()
    m = re.search(r"(?<![A-Z0-9])V[I1L]N\s*[:;]?\s*(.*)", u)
    if not m:
        return []
    # The VIN is immediately after its printed label. If its beginning is
    # missing, fail; do not borrow characters from TYPE, GVWR, etc.
    tail = m.group(1)
    tail = re.split(r"\b(?:TYPE|GVWR|GAWR|DATE|TIRES|RIMS|AXLE|VIN)\b", tail, maxsplit=1)[0]
    raw = re.sub(r"[^A-Z0-9]", "", tail)
    if len(raw) < 17:
        return []
    candidate = raw[:17]
    # Even if the field name is stuck to the OCR token, do not accept it.
    if any(field in candidate for field in ("TYPE", "GVWR", "GAWR", "DATE", "TIRES", "RIMS", "AXLE")):
        return []
    return [candidate]


def _one_glyph_vin_candidates(raw_windows: list[str]) -> set[str]:
    """Generate only one-glyph OCR alternatives actually justified by common camera confusions."""
    from vehicle_data.acquisition import vin_is_valid
    # These are OCR alternatives, not arbitrary VIN substitutions. 1/4/7/T is especially
    # common on the narrow leading '1' printed on certification labels.
    alternatives = {
        "I":"1", "L":"1", "4":"1", "7":"1", "T":"1",
        "O":"0", "Q":"0", "Z":"2", "S":"5", "G":"6", "B":"8",
        "1":"4T7", "0":"OQ", "2":"Z", "5":"S", "6":"G", "8":"B",
    }
    out = set()
    for raw in raw_windows:
        if VIN_PATTERN.fullmatch(raw) and vin_is_valid(raw):
            out.add(raw)
        if len(raw) != 17:
            continue
        for i, ch in enumerate(raw):
            for repl in alternatives.get(ch, ""):
                candidate = raw[:i] + repl + raw[i+1:]
                if VIN_PATTERN.fullmatch(candidate) and vin_is_valid(candidate):
                    out.add(candidate)
    return out


def _estimate_label_angle(image: Image.Image) -> int:
    """Cheaply estimate door-label/barcode tilt before invoking Tesseract.

    Certification labels contain dense horizontal text plus a long 1-D barcode. When that
    structure is deskewed, horizontal intensity changes from the barcode's vertical bars
    concentrate into fewer rows. This gives us a fast angle estimate without OCR.
    """
    gray = ImageOps.grayscale(image)
    scale = min(1.0, 760.0 / max(1, gray.width))
    if scale < 1.0:
        gray = gray.resize((max(1, int(gray.width * scale)), max(1, int(gray.height * scale))))
    best_angle, best_score = 0, -1.0
    for angle in range(-20, 21, 2):
        work = gray if angle == 0 else gray.rotate(angle, expand=True, fillcolor=255)
        arr = np.asarray(work, dtype=np.int16)
        if arr.shape[1] < 20:
            continue
        edges = (np.abs(np.diff(arr, axis=1)) > 55).mean(axis=1)
        if len(edges) >= 12:
            edges = np.convolve(edges, np.ones(12) / 12.0, mode="same")
        score = float(np.percentile(edges, 99.5)) if len(edges) else 0.0
        if score > best_score:
            best_angle, best_score = angle, score
    return best_angle


def _ocr_vin_windows(image: Image.Image, angle: int, threshold: int | None = None, *, psm: int = 6) -> list[str]:
    work = image if angle == 0 else image.rotate(angle, expand=True, fillcolor="white")
    # Cap the OCR raster. 23J repeatedly enlarged every full 1080x1920 frame and paid the
    # Tesseract cost six times. One deskewed 2200px raster retains the label detail we need.
    scale = min(2.5, 2400.0 / max(1, work.width))
    if scale > 1.0:
        work = work.resize((int(work.width * scale), int(work.height * scale)))
    gray = ImageEnhance.Contrast(ImageOps.grayscale(work)).enhance(2.3).filter(ImageFilter.SHARPEN)
    if threshold is not None:
        gray = gray.point(lambda p, t=threshold: 255 if p > t else 0)
    try:
        text = pytesseract.image_to_string(
            gray,
            config=f"--psm {psm} -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:",
            timeout=4,
        )
    except Exception:
        return []
    windows = []
    for line in text.splitlines():
        windows.extend(_ocr_labeled_windows(line))
    return windows


def _exact_valid_reads(windows: list[str]) -> list[str]:
    from vehicle_data.acquisition import vin_is_valid
    out = []
    for v in windows:
        if VIN_PATTERN.fullmatch(v or "") and not any(t in v for t in ("TYPE", "GVWR", "GAWR", "DATE", "TIRES", "RIMS", "AXLE")) and vin_is_valid(v) and v not in out:
            out.append(v)
    return out


def _confirm_single_vin(vin: str) -> bool:
    """One bounded identity check, never the 23J candidate fan-out."""
    try:
        d = NHTSAVpicClient(timeout=3).decode(vin)
    except Exception:
        return False
    return (str(d.get("ErrorCode") or "").strip() == "0" and
            bool(d.get("Make")) and bool(d.get("Model")) and bool(d.get("ModelYear")))


def _fast_consensus_vin(primary: list[str], corroborating: list[str]) -> str | None:
    """Accept only a VIN read verbatim by OCR; never synthesize one from substitutions."""
    valid_primary = _exact_valid_reads(primary)
    valid_secondary = _exact_valid_reads(corroborating)
    exact = set(valid_primary) & set(valid_secondary)
    if len(exact) == 1:
        return next(iter(exact))
    supported = set()
    for v in set(valid_primary + valid_secondary):
        other = corroborating if v in valid_primary else primary
        # Corroboration can be imperfect, but the accepted VIN itself was read verbatim and
        # already passed its checksum. Two-glyph tolerance handles common 1/T and 2/Z pairs.
        if any(len(r) == 17 and sum(a != b for a, b in zip(v, r)) <= 2 for r in other):
            supported.add(v)
    return next(iter(supported)) if len(supported) == 1 else None


def extract_vin_from_photo(photo) -> str | None:
    """Build 23K: 23J accuracy with bounded OCR and at most one identity lookup per exact read."""
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

    estimated = _estimate_label_angle(image)
    angles = []
    for a in (estimated - 1, estimated + 1, estimated, 0):
        a = max(-22, min(22, int(a)))
        if a not in angles:
            angles.append(a)

    # Highest-yield pass first. If it produces one exact checksum-valid VIN, make ONE
    # short identity check. 23J could make many network calls after every OCR pass.
    first = _ocr_vin_windows(image, angles[0], None)
    exact = _exact_valid_reads(first)
    if len(exact) == 1 and _confirm_single_vin(exact[0]):
        return exact[0]

    # Independent rendering for local corroboration. No network call is needed if both
    # OCR paths support the same verbatim checksum-valid VIN.
    second = _ocr_vin_windows(image, angles[0], 135)
    resolved = _fast_consensus_vin(first, second)
    if resolved:
        return resolved

    # Bounded fallback at the other side of the estimated angle.
    third = _ocr_vin_windows(image, angles[1], None)
    resolved = _fast_consensus_vin(first + second, third)
    if resolved:
        return resolved
    exact = _exact_valid_reads(third)
    if len(exact) == 1 and _confirm_single_vin(exact[0]):
        return exact[0]

    # Build 23L: progressively recover using the orientations that 23J used successfully.
    # Do not run NHTSA lookups for speculative OCR mutations; only corroborate exact reads.
    # Keep the known-good camera and matching logic completely unchanged.
    observed = first + second + third
    for angle, threshold, psm in (
        (angles[2], None, 6),
        (0, None, 6),
        (-13, None, 6),
        (13, None, 6),
        (-8, 115, 6),
        (8, 115, 6),
        (0, 115, 6),
        (estimated, None, 11),
    ):
        # Do not duplicate work already performed by the fast stage.
        if (angle, threshold, psm) in ((angles[0], None, 6),
                                        (angles[0], 135, 6),
                                        (angles[1], None, 6)):
            continue
        more = _ocr_vin_windows(image, angle, threshold, psm=psm)
        if not more:
            continue
        resolved = _fast_consensus_vin(observed, more)
        if resolved:
            return resolved
        observed.extend(more)
    return None


VIN_CAMERA_HTML = """
<div class="vin-camera">
  <video id="vin-video" autoplay playsinline></video>
  <canvas id="vin-canvas" hidden></canvas>
  <div id="vin-status">Opening rear camera…</div>
  <button id="vin-capture" type="button">Take VIN Photo</button>
</div>
"""
VIN_CAMERA_CSS = """
.vin-camera { font-family: var(--st-font); width: 100%; }
#vin-video { width: 100%; border-radius: 10px; background: #111; }
#vin-capture { width:100%; margin-top:.5rem; padding:.7rem; font-size:1rem; }
#vin-status { margin-top:.35rem; font-size:.85rem; opacity:.75; }
"""
VIN_CAMERA_JS = r"""
export default function(component) {
  const { parentElement, setTriggerValue } = component;
  const video = parentElement.querySelector('#vin-video');
  const canvas = parentElement.querySelector('#vin-canvas');
  const button = parentElement.querySelector('#vin-capture');
  const status = parentElement.querySelector('#vin-status');
  let stream = null;
  let barcodeTimer = null;
  let barcodeBusy = false;
  let barcodeDone = false;

  async function startBarcodeWatch() {
    if (!("BarcodeDetector" in globalThis)) return;
    try {
      const formats = await BarcodeDetector.getSupportedFormats();
      if (!formats.includes('code_39')) return;
      const detector = new BarcodeDetector({formats:['code_39']});
      barcodeTimer = setInterval(async () => {
        if (barcodeBusy || barcodeDone || video.readyState < 2) return;
        barcodeBusy = true;
        try {
          const hits = await detector.detect(video);
          for (const hit of hits) {
            const raw = (hit.rawValue || '').trim();
            if (raw) {
              barcodeDone = true;
              status.textContent = 'VIN barcode found';
              setTriggerValue('barcode', raw);
              clearInterval(barcodeTimer);
              break;
            }
          }
        } catch (e) { /* photo/OCR fallback remains available */ }
        finally { barcodeBusy = false; }
      }, 350);
    } catch (e) { /* unsupported format: photo/OCR fallback */ }
  }

  async function openRearCamera() {
    try {
      // Require the environment-facing camera. Do not silently fall back to selfie camera.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { exact: 'environment' },
          width: { ideal: 1920, min: 1280 },
          height: { ideal: 1080, min: 720 }
        }
      });
    } catch (e) {
      try {
        // Some browsers reject exact facingMode even though they honor an environment preference.
        stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1920 },
            height: { ideal: 1080 }
          }
        });
      } catch (e2) {
        status.textContent = 'Rear camera could not be opened.';
        button.disabled = true;
        return;
      }
    }
    video.srcObject = stream;
    await video.play();
    const settings = stream.getVideoTracks()[0].getSettings();
    status.textContent = `Rear camera ready · ${settings.width || video.videoWidth} × ${settings.height || video.videoHeight}`;
    startBarcodeWatch();
  }

  button.onclick = () => {
    if (!video.videoWidth || !video.videoHeight) return;
    // Critical: canvas uses the CAMERA FRAME dimensions, never the displayed widget dimensions.
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
    setTriggerValue('photo', dataUrl);
  };

  openRearCamera();
  return () => {
    if (barcodeTimer) clearInterval(barcodeTimer);
    if (stream) stream.getTracks().forEach(track => track.stop());
  };
}
"""

def _vin_camera_component():
    return st.components.v2.component(
        "tow_match_vin_rear_camera",
        html=VIN_CAMERA_HTML, css=VIN_CAMERA_CSS, js=VIN_CAMERA_JS,
    )


def init_state():
    # Production-safe defaults: never seed a real Tow Match with the development Expedition.
    defaults={
        'vehicle_ready':False,'payload':None,'tow_rating':None,'fw_rating':None,'vin':'',
        'adults':2,'children':0,'pets':0.0,'cargo':150.0,'category':'Travel Trailer',
        'acquisition':None,'verify_target':None,'matched_category':None,
        'edit_people_open':False,'edit_vehicle_open':False,
        'edit_payload':None,'edit_tow_rating':None,'edit_fw_rating':None,'edit_vin':'',
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
                    # Build 23I: purpose-built rear-camera component. It requires/prefers
                    # facingMode=environment and captures at the camera frame's native
                    # dimensions rather than shrinking to the displayed widget size.
                    vin_camera = _vin_camera_component()
                    camera_result = vin_camera(
                        key='vin_rear_camera',
                        on_photo_change=lambda: None,
                    )
                    barcode_raw = getattr(camera_result, 'barcode', None)
                    if barcode_raw:
                        barcode_vin = _valid_vin_from_barcode_text(barcode_raw)
                        if barcode_vin:
                            st.session_state.apply_scanned_vin=barcode_vin
                            st.session_state.vin_camera_open=False
                            st.session_state.vin_scan_message=f'VIN read: {barcode_vin}'
                            st.rerun()
                    vin_photo = getattr(camera_result, 'photo', None)
                    if vin_photo:
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
                            # Diagnostic is intentionally visible only on failure. It tells us
                            # what resolution the browser actually delivered; 1080p is a request.
                            received = _photo_to_image(vin_photo)
                            if received is not None:
                                st.caption(f"Camera image received: {received.width} × {received.height} pixels")
                            st.warning("VIN wasn't recognized. You can retake the photo, enter the VIN, or continue using the yellow-label payload.")
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
                            st.caption('Or continue without another scan:')
                            manual_vin, manual_payload = st.columns(2)
                            with manual_vin:
                                if st.button('Enter VIN Manually', key='scan_manual_vin', use_container_width=True):
                                    st.session_state.vin_camera_open=False
                                    st.session_state.vin_scan_message=None
                                    st.session_state.scan_manual_hint='vin'
                                    st.rerun()
                            with manual_payload:
                                if st.button('Enter Payload Manually', key='scan_manual_payload', use_container_width=True):
                                    st.session_state.vin_camera_open=False
                                    st.session_state.vin_scan_message=None
                                    st.session_state.scan_manual_hint='payload'
                                    st.rerun()
                if st.session_state.get('vin_scan_message'):
                    st.success(st.session_state.vin_scan_message)
                    st.session_state.vin_scan_message=None
                hint=st.session_state.pop('scan_manual_hint',None)
                if hint=='vin':
                    st.info('Enter the VIN in the VIN field above. Scanning is optional.')
                elif hint=='payload':
                    st.info('Enter the yellow-label payload below. You can continue without a VIN; unverified vehicle ratings remain Verify.')
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
            st.caption('Vehicle details can be updated below. Once a VIN is established, use **New Tow Match** to change vehicles.')
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
                st.session_state.edit_vin=st.session_state.vin or ''
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
            # Payload-only acquisition is NOT an established vehicle identity.
            # A VIN can be supplied later without discarding the customer's inputs.
            identity_established=bool(st.session_state.vin and acq.identity.vin)
            if identity_established:
                st.caption(f"VIN / vehicle identity locked: {st.session_state.vin}. Use New Tow Match for another vehicle.")
            else:
                st.info('No VIN established yet. You can add the VIN now and keep the payload and other inputs already entered.')
            st.caption('Current effective values are shown below. Leave an unknown rating blank.')
            with st.form('correct_vehicle_data'):
                if not identity_established:
                    added_vin=st.text_input('Add VIN (optional)',key='edit_vin',placeholder='17-character VIN')
                else:
                    added_vin=st.session_state.vin
                vc1,vc2,vc3=st.columns(3)
                with vc1: payload=st.number_input('Yellow-label payload (lb)',min_value=0,step=1,placeholder='Unknown',key='edit_payload')
                with vc2: tow=st.number_input('Conventional tow rating (lb)',min_value=0,step=100,placeholder='Unknown',key='edit_tow_rating')
                with vc3: fw=st.number_input('Fifth-wheel rating (lb)',min_value=0,step=100,placeholder='Unknown',key='edit_fw_rating')
                if st.form_submit_button('Correct & Recalculate',type='primary'):
                    from vehicle_data.acquisition import normalize_vin, vin_is_valid
                    normalized=normalize_vin(added_vin) if added_vin else ''
                    if normalized and not vin_is_valid(normalized):
                        st.error('VIN is not valid. Correct it or leave it blank to continue with payload-only results.')
                    else:
                        adding_identity=bool(normalized and not identity_established)
                        st.session_state.payload=payload
                        st.session_state.tow_rating=tow
                        st.session_state.fw_rating=fw
                        if adding_identity:
                            st.session_state.vin=normalized
                            # Refresh identity/facts with the newly supplied VIN.
                            # The old payload-only acquisition must not overwrite them.
                            _,updated,_=acquire_for_category(category,live_lookup=True)
                            st.session_state.acquisition=updated
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
