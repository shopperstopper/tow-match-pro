import re
import time
import requests
from bs4 import BeautifulSoup
import pandas as pd

BASE_URL = "https://www.apachecamping.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def clean_int(val_str):
    if not val_str:
        return None
    cleaned = re.sub(r"[^\d]", "", str(val_str))
    return int(cleaned) if cleaned else None

def parse_location(text):
    if not text:
        return "Unassigned"
    t = text.lower()
    if any(k in t for k in ["kitsap", "poulsbo"]):
        return "Kitsap / Poulsbo"
    elif "everett" in t:
        return "Everett"
    elif any(k in t for k in ["portland", "clackamas"]):
        return "Portland / Clackamas"
    elif "tacoma" in t:
        return "Tacoma"
    return "Unassigned"

def detect_category(title_text):
    t = title_text.lower()
    if "fifth wheel" in t or "5th wheel" in t:
        return "Fifth Wheel"
    elif "truck camper" in t or "camper" in t and "trailer" not in t:
        return "Truck Camper"
    return "Travel Trailer"

def extract_vdp_specs(vdp_url):
    specs = {
        "DryWeight": None,
        "GVWR": None,
        "HitchWeight": None,
        "Length": None,
        "Price": "Call for Price",
        "Image": "",
        "Status": "On Lot"
    }
    try:
        resp = requests.get(vdp_url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return specs
            
        soup = BeautifulSoup(resp.content, "html.parser")
        clean_text = soup.get_text(" ", strip=True)

        # Status
        if any(term in clean_text.lower() for term in ["incoming", "inbound", "on order"]):
            specs["Status"] = "Inbound / Pipeline"
        else:
            specs["Status"] = "On Lot"

        # Price
        price_match = re.search(r"\$[\d,]+", clean_text)
        if price_match:
            specs["Price"] = price_match.group(0)

        # Photo
        img = soup.select_one(".unit-photo img, .gallery-slide img, meta[property='og:image']")
        if img:
            specs["Image"] = img.get("content") or img.get("src") or ""

        # Hitch Weight
        hitch_match = re.search(r"Hitch\s*Weight\s*([\d,]+)\s*lbs?", clean_text, re.IGNORECASE)
        if hitch_match:
            specs["HitchWeight"] = clean_int(hitch_match.group(1))

        # Dry Weight
        dry_match = re.search(r"(?:Dry|Unloaded)\s*Weight\s*([\d,]+)\s*lbs?", clean_text, re.IGNORECASE)
        if dry_match:
            specs["DryWeight"] = clean_int(dry_match.group(1))

        # GVWR
        gvwr_match = re.search(r"GVWR\s*([\d,]+)\s*lbs?", clean_text, re.IGNORECASE)
        if gvwr_match:
            specs["GVWR"] = clean_int(gvwr_match.group(1))

        # Length (Rule 76: Real overall length)
        len_match = re.search(r"Length\s*(\d+)\s*ft(?:\s*(\d+)\s*in)?", clean_text, re.IGNORECASE)
        if len_match:
            ft = float(len_match.group(1))
            inch = float(len_match.group(2)) if len_match.group(2) else 0.0
            specs["Length"] = round(ft + (inch / 12.0), 1)

    except Exception:
        pass
        
    return specs

def scrape_apache_catalog():
    all_units = []
    seen_urls = set()
    page = 1

    print("--- Scraping Apache Inventory (Tow Match Pro Schema) ---")

    while True:
        catalog_url = f"{BASE_URL}/rv-search?page={page}"
        print(f"[Page {page}]")
        try:
            resp = requests.get(catalog_url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                break
        except Exception:
            break

        soup = BeautifulSoup(resp.content, "html.parser")
        raw_links = soup.select("a[href*='/product/'], a[href*='/rv/']")
        if not raw_links:
            break

        units_on_page = 0
        for a in raw_links:
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or any(junk in title.lower() for junk in ["send to", "floorplan", "details", "photo", "brochure", "quote"]):
                continue

            full_vdp_url = href if href.startswith("http") else BASE_URL + href
            if full_vdp_url in seen_urls:
                continue
            seen_urls.add(full_vdp_url)
            units_on_page += 1

            wrapper = a.find_parent(class_=lambda c: c and "unit-title-wrapper" in c)
            loc_text = wrapper.get_text(" ", strip=True) if wrapper else (a.parent.get_text(" ", strip=True) if a.parent else "")
            location = parse_location(loc_text)

            category = detect_category(title)
            condition = "Used" if "used" in title.lower() else "New"

            specs = extract_vdp_specs(full_vdp_url)
            time.sleep(0.3)

            all_units.append({
                "Model": title,
                "Category": category,
                "Condition": condition,
                "Location": location,
                "Status": specs["Status"],
                "Length": specs["Length"],
                "DryWeight": specs["DryWeight"],
                "GVWR": specs["GVWR"],
                "HitchWeight": specs["HitchWeight"],
                "Price": specs["Price"],
                "Image": specs["Image"],
                "URL": full_vdp_url
            })

        if units_on_page == 0 or page >= 25:
            break
        page += 1

    df = pd.DataFrame(all_units)
    df.to_csv("apache_full_inventory.csv", index=False)
    print(f"Scraped {len(df)} units successfully to 'apache_full_inventory.csv'.")

if __name__ == "__main__":
    scrape_apache_catalog()