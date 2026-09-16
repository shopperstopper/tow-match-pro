"""Apache Camping Center inventory adapter for Tow Match Pro v1.

Design rules:
- Capture broad VDP data; do not patch one matching field at a time.
- Preserve raw source facts and provenance.
- Never silently replace missing source facts with matching assumptions.
- Normalize malformed InteractRV length strings (e.g. `253 ft` => 25'3\").
"""
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from inventory_schema import InventoryRecord, SourceValue

BASE_URL = "https://www.apachecamping.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 TowMatchPro/1.0"
}

SPEC_ALIASES = {
    "sleeps": "Sleeps", "slides": "Slides", "length": "Length",
    "ext width": "Ext Width", "ext height": "Ext Height", "int height": "Int Height",
    "hitch weight": "Hitch Weight", "gvwr": "GVWR", "dry weight": "Dry Weight",
    "cargo capacity": "Cargo Capacity", "fresh water capacity": "Fresh Water Capacity",
    "grey water capacity": "Grey Water Capacity", "gray water capacity": "Grey Water Capacity",
    "black water capacity": "Black Water Capacity", "tire size": "Tire Size",
    "lp tank capacity": "LP Tank Capacity", "number of lp tanks": "Number of LP Tanks",
    "axle count": "Axle Count", "vin": "VIN", "truck bed size": "Truck Bed Size",
    "body style": "Body Style", "bed size": "Truck Bed Size", "recommended truck bed size": "Truck Bed Size", "truck bed length": "Truck Bed Size", "cg front": "CG Front", "center of gravity": "Center of Gravity",
    "center of gravity front": "Center of Gravity Front", "center of gravity location": "Center of Gravity", "floor length": "Floor Length",
}


def clean_number(value: Optional[str]) -> Optional[float]:
    if value is None: return None
    m = re.search(r"-?[\d,.]+", str(value))
    if not m: return None
    try: return float(m.group(0).replace(",", ""))
    except ValueError: return None


def clean_int(value: Optional[str]) -> Optional[int]:
    n = clean_number(value)
    return int(round(n)) if n is not None else None


def parse_feet_inches(value: Optional[str], *, compact_length_fix: bool = False) -> Optional[float]:
    """Parse dimension text to decimal feet.

    InteractRV currently emits some overall lengths as `253 ft` where the source
    means 25 ft 3 in. We repair only plausible compact 3-digit/4-digit length
    encodings; we do not divide arbitrary values by 12.
    """
    if not value: return None
    s = str(value).strip().lower().replace("′", "'").replace("″", '"')
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:ft|feet|')\s*(?:(\d+(?:\.\d+)?)\s*(?:in|inches|\"))?", s)
    if m:
        ft_raw = m.group(1)
        inches_raw = m.group(2)
        ft = float(ft_raw)
        inches = float(inches_raw) if inches_raw else 0.0
        if compact_length_fix and not inches_raw and ft.is_integer() and ft > 80:
            digits = str(int(ft))
            # 253 -> 25'3", 286 -> 28'6", 402 -> 40'2", 417 -> 41'7".
            # Four digits are interpreted only when last two form valid inches.
            if len(digits) == 3:
                candidate_ft, candidate_in = int(digits[:2]), int(digits[2:])
                if 10 <= candidate_ft <= 60 and 0 <= candidate_in <= 11:
                    return round(candidate_ft + candidate_in / 12.0, 3)
            elif len(digits) == 4:
                candidate_ft, candidate_in = int(digits[:2]), int(digits[2:])
                if 10 <= candidate_ft <= 60 and 0 <= candidate_in <= 11:
                    return round(candidate_ft + candidate_in / 12.0, 3)
        return round(ft + inches / 12.0, 3)
    return None


def parse_inches(value: Optional[str]) -> Optional[float]:
    ft = parse_feet_inches(value)
    return round(ft * 12, 2) if ft is not None else None


def parse_location(text: str) -> Optional[str]:
    t = (text or "").lower()
    if "poulsbo" in t or "kitsap" in t: return "Poulsbo, WA"
    if "everett" in t: return "Everett, WA"
    if "portland" in t or "clackamas" in t: return "Portland, OR"
    if "tacoma" in t: return "Tacoma, WA"
    return None


def normalize_category(text: str) -> Optional[str]:
    t = (text or "").lower()
    if "truck camper" in t: return "Truck Camper"
    if "fifth wheel" in t or "5th wheel" in t: return "Fifth Wheel"
    if "travel trailer" in t: return "Travel Trailer"
    return None


def infer_major_type(text: str, category: Optional[str]) -> Optional[str]:
    t = (text or "").lower()
    if "toy hauler" in t: return "Toy Hauler"
    if "bunk" in t: return "Bunkhouse"
    if category == "Truck Camper":
        if "pop-up" in t or "pop up" in t: return "Pop-Up"
        if "hard-side" in t or "hard side" in t: return "Hard-Side"
    return None


def parse_title(title: str) -> tuple[Optional[str], Optional[int], Optional[str], Optional[str], Optional[str]]:
    condition = None
    s = (title or "").strip()
    if re.match(r"(?i)^used\b", s): condition = "Used"; s = re.sub(r"(?i)^used\s+", "", s)
    elif re.match(r"(?i)^new\b", s): condition = "New"; s = re.sub(r"(?i)^new\s+", "", s)
    m = re.match(r"(20\d{2}|19\d{2})\s+(.+)", s)
    if not m: return condition, None, None, None, None
    year = int(m.group(1)); rest = m.group(2).strip()
    # Manufacturer/brand/model boundaries are not reliably encoded in title.
    # Preserve the full post-year text as model_display rather than invent facts.
    return condition, year, None, None, rest


def extract_spec_pairs(soup: BeautifulSoup) -> dict[str, str]:
    """Extract broad label/value pairs from the Specifications region/table."""
    specs: dict[str, str] = {}
    # Common table markup first.
    for row in soup.select("table tr"):
        cells = [c.get_text(" ", strip=True) for c in row.select("th,td")]
        for i in range(0, len(cells)-1, 2):
            key = SPEC_ALIASES.get(cells[i].strip().lower(), cells[i].strip())
            if key and cells[i+1]: specs[key] = cells[i+1].strip()

    # InteractRV pages often render specs as alternating label/value elements.
    text = soup.get_text("\n", strip=True)
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    known = {k.lower(): v for k,v in SPEC_ALIASES.items()}
    for i, line in enumerate(lines[:-1]):
        canonical = known.get(line.lower())
        if canonical and canonical not in specs:
            nxt = lines[i+1]
            if nxt.lower() not in known: specs[canonical] = nxt

    # Robust text fallback for known labels. Non-greedy up to next known label.
    flat = soup.get_text(" | ", strip=True)
    labels = sorted(set(SPEC_ALIASES.values()), key=len, reverse=True)
    label_pat = "|".join(re.escape(x) for x in labels)
    for label in labels:
        if label in specs: continue
        m = re.search(rf"(?:^|\|)\s*{re.escape(label)}\s*\|?\s*(.*?)\s*(?=\|\s*(?:{label_pat})\s*\||$)", flat, re.I)
        if m and m.group(1).strip(): specs[label] = m.group(1).strip(" |")
    return specs


def provenance(value, raw, url, confidence="high", included=None):
    return SourceValue(value=value, raw=raw, source_url=url, confidence=confidence,
                       included_components=included or []).__dict__


def parse_vdp_html(html: bytes | str, url: str) -> InventoryRecord:
    """Parse one Apache VDP from supplied HTML. Kept separate from HTTP for testability."""
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    specs = extract_spec_pairs(soup)

    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else (soup.title.get_text(" ", strip=True) if soup.title else "")
    condition, year, manufacturer, brand, model = parse_title(title)

    category = None
    # Category generally sits near the H1 and is also in title/meta text.
    category = normalize_category(page_text[:5000])
    location = None
    stock = None
    if h1:
        nearby = h1.parent.get_text(" ", strip=True) if h1.parent else ""
        location = parse_location(nearby)
    location = location or parse_location(page_text[:4000])
    sm = re.search(r"Stock\s*#\s*([A-Za-z0-9_-]+)", page_text, re.I)
    if sm: stock = sm.group(1)

    price = None
    pm = re.search(r"(?:Our Price|Sale Price|Price)\s*:?\s*\$([\d,]+)", page_text, re.I)
    if pm: price = clean_int(pm.group(1))

    image = None
    og = soup.select_one("meta[property='og:image']")
    if og: image = og.get("content")
    if not image:
        img = soup.select_one(".unit-photo img, .gallery-slide img, img[src*='unit_photo']")
        if img: image = img.get("src") or img.get("data-src")
    if image: image = urljoin(url, image)

    status_text = page_text.lower()
    if any(x in status_text for x in ["sold", "sale pending", "pending sale"]):
        status, sellable, pipeline = "Unavailable / Committed", False, None
    elif any(x in status_text for x in ["in production", "on order"]):
        status, sellable, pipeline = "Pipeline", True, "In Production / On Order"
    elif any(x in status_text for x in ["incoming", "inbound", "in transit"]):
        status, sellable, pipeline = "Pipeline", True, "Incoming / In Transit"
    else:
        status, sellable, pipeline = "On Lot", True, None

    def raw(name): return specs.get(name)
    length = parse_feet_inches(raw("Length"), compact_length_fix=True)
    uvw = clean_int(raw("Dry Weight")); gvwr = clean_int(raw("GVWR")); ccc = clean_int(raw("Cargo Capacity"))
    hitch = clean_int(raw("Hitch Weight"))

    rec = InventoryRecord(
        source_url=url, scraped_at_utc=datetime.now(timezone.utc).isoformat(), stock_number=stock,
        vin=(raw("VIN") or None), condition=condition, year=year, manufacturer=manufacturer,
        brand=brand, model=model, floorplan=None, display_title=title, rv_category=category,
        major_type=infer_major_type(page_text[:8000], category), location=location,
        inventory_status=status, sellable=sellable, pipeline_stage=pipeline, price_usd=price,
        image_url=image, sleeps=clean_int(raw("Sleeps")), slides=clean_int(raw("Slides")),
        overall_length_ft=length, exterior_width_in=parse_inches(raw("Ext Width")),
        exterior_height_in=parse_inches(raw("Ext Height")), uvw_lb=uvw, gvwr_lb=gvwr,
        ccc_lb=ccc, published_hitch_pin_lb=hitch, fresh_water_gal=clean_number(raw("Fresh Water Capacity")),
        gray_water_gal=clean_number(raw("Grey Water Capacity")), black_water_gal=clean_number(raw("Black Water Capacity")),
        lp_tank_capacity_lb=clean_number(raw("LP Tank Capacity")), lp_tank_count=clean_int(raw("Number of LP Tanks")),
        axle_count=clean_int(raw("Axle Count")), tire_size=raw("Tire Size"), truck_bed_size=raw("Truck Bed Size"),
        body_style=raw("Body Style"), cg_front_in=clean_number(raw("CG Front") or raw("Center of Gravity Front") or raw("Center of Gravity")), raw_specs=specs,
    )

    normalized = {
        "overall_length_ft": (length, raw("Length")), "uvw_lb": (uvw, raw("Dry Weight")),
        "gvwr_lb": (gvwr, raw("GVWR")), "ccc_lb": (ccc, raw("Cargo Capacity")),
        "published_hitch_pin_lb": (hitch, raw("Hitch Weight")), "vin": (rec.vin, raw("VIN")),
        "fresh_water_gal": (rec.fresh_water_gal, raw("Fresh Water Capacity")),
        "gray_water_gal": (rec.gray_water_gal, raw("Grey Water Capacity")),
        "black_water_gal": (rec.black_water_gal, raw("Black Water Capacity")),
        "truck_bed_size": (rec.truck_bed_size, raw("Truck Bed Size")),
        "body_style": (rec.body_style, raw("Body Style")),
        "cg_front_in": (rec.cg_front_in, raw("CG Front") or raw("Center of Gravity Front") or raw("Center of Gravity")),
    }
    for key, (val, rawval) in normalized.items():
        if val is not None: rec.provenance[key] = provenance(val, rawval, url)

    if raw("Length") and length is None: rec.parse_warnings.append(f"Could not normalize Length: {raw('Length')}")
    if not category: rec.parse_warnings.append("RV category not confidently identified")
    if not stock: rec.parse_warnings.append("Stock number not found")
    # Deliberately no Dry/GVWR/Hitch/Length fallback values here.
    return rec


def extract_vdp(url: str, session: Optional[requests.Session] = None) -> InventoryRecord:
    sess = session or requests.Session()
    resp = sess.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return parse_vdp_html(resp.content, url)


def discover_vdp_urls(session: requests.Session, max_pages: int = 25) -> list[str]:
    seen: set[str] = set(); urls: list[str] = []
    for page in range(1, max_pages + 1):
        r = session.get(f"{BASE_URL}/rv-search?page={page}", headers=HEADERS, timeout=20)
        if r.status_code != 200: break
        soup = BeautifulSoup(r.content, "html.parser")
        page_urls = []
        for a in soup.select("a[href*='/product/']"):
            href = a.get("href")
            if not href: continue
            u = urljoin(BASE_URL, href.split("?")[0])
            if u not in seen:
                seen.add(u); page_urls.append(u); urls.append(u)
        if not page_urls: break
    return urls


def flatten_for_csv(rec: InventoryRecord) -> dict:
    d = rec.to_dict()
    d["raw_specs_json"] = json.dumps(d.pop("raw_specs"), ensure_ascii=False, sort_keys=True)
    d["provenance_json"] = json.dumps(d.pop("provenance"), ensure_ascii=False, sort_keys=True)
    d["parse_warnings"] = " | ".join(d.get("parse_warnings") or [])
    return d


def scrape(output: Path, max_pages: int = 25, limit: Optional[int] = None, delay: float = 0.25) -> pd.DataFrame:
    session = requests.Session()
    urls = discover_vdp_urls(session, max_pages=max_pages)
    if limit: urls = urls[:limit]
    rows = []
    for i, url in enumerate(urls, 1):
        try:
            rec = extract_vdp(url, session)
            rows.append(flatten_for_csv(rec))
            print(f"[{i}/{len(urls)}] {rec.stock_number or '-'} | {rec.rv_category or '?'} | {rec.display_title}")
        except Exception as e:
            print(f"[{i}/{len(urls)}] ERROR {url}: {e}")
        if delay: time.sleep(delay)
    df = pd.DataFrame(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    return df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="apache_inventory_v1.csv")
    p.add_argument("--max-pages", type=int, default=25)
    p.add_argument("--limit", type=int)
    p.add_argument("--delay", type=float, default=0.25)
    p.add_argument("--url", help="Parse one VDP URL instead of catalog")
    args = p.parse_args()
    if args.url:
        rec = extract_vdp(args.url)
        print(json.dumps(rec.to_dict(), indent=2, ensure_ascii=False))
    else:
        df = scrape(Path(args.output), args.max_pages, args.limit, args.delay)
        print(f"Saved {len(df)} normalized Apache inventory records to {args.output}")

if __name__ == "__main__": main()
