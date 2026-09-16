import streamlit as st
import pandas as pd
import numpy as np

# Dealer Configuration Dictionary
DEALER_CONFIG = {
    "APACHE2026": {
        "name": "Apache Camping Center",
        "logo_icon": "rv-icon.png",
        "csv_path": "apache_full_inventory.csv"
    }
}

# Query Parameter Handling (Key and Default Lot)
query_params = st.query_params
license_key = query_params.get("key", "APACHE2026")
param_lot = query_params.get("lot", "").lower()
dealer_info = DEALER_CONFIG.get(license_key, DEALER_CONFIG["APACHE2026"])

# Page Setup
st.set_page_config(
    page_title=f"{dealer_info['name']} - Tow Match Pro",
    page_icon=dealer_info["logo_icon"],
    layout="wide"
)

# Header
st.title(f"🚐 {dealer_info['name']} — Tow Match Pro")
st.caption("Real-time tow capacity match against lot inventory.")

# Load Inventory Data
@st.cache_data(ttl=300)
def load_inventory(filepath):
    try:
        data = pd.read_csv(filepath)
    except Exception:
        return pd.DataFrame()

    default_cols = {
        "Model": "RV Unit",
        "Length": 26.0,
        "DryWeight": 5200,
        "GVWR": 7000,
        "HitchWeight": np.nan,
        "Location": "Unassigned",
        "Status": "On Lot",
        "Image": "",
        "URL": ""
    }
    for col, default_val in default_cols.items():
        if col not in data.columns:
            data[col] = default_val

    # Detect New vs Used directly from the Model title
    def get_condition(row):
        model_name = str(row["Model"]).strip().lower()
        if model_name.startswith("used") or " used " in model_name:
            return "Used"
        elif model_name.startswith("new") or " new " in model_name:
            return "New"
        
        # Fallback to column if already populated
        if "Condition" in row and str(row["Condition"]).strip().lower() in ["new", "used"]:
            return str(row["Condition"]).strip().capitalize()
        return "New"

    data["Condition"] = data.apply(get_condition, axis=1)

    # Numeric Conversions
    for num_col in ["Length", "DryWeight", "GVWR", "HitchWeight"]:
        data[num_col] = pd.to_numeric(data[num_col], errors="coerce")

    # Clean Lengths: convert values recorded in inches (> 45) to decimal feet
    data["Length"] = data["Length"].apply(
        lambda x: round(x / 12.0, 1) if pd.notnull(x) and x > 45 else (round(x, 1) if pd.notnull(x) else 24.0)
    )

    # Fill fallback weights
    data["DryWeight"] = data["DryWeight"].fillna(4800).astype(int)
    data["GVWR"] = data["GVWR"].fillna(data["DryWeight"] + 1800).astype(int)
    data["HitchWeight"] = data["HitchWeight"].fillna((data["GVWR"] * 0.12).round()).astype(int)
    data["Location"] = data["Location"].fillna("Unassigned")

    return data

df_raw = load_inventory(dealer_info["csv_path"])

if df_raw.empty:
    st.error("Unable to load inventory data. Please verify 'apache_full_inventory.csv' is uploaded.")
    st.stop()

# ----------------- SIDEBAR LOT & INVENTORY FILTERS -----------------
st.sidebar.header("Dealership Lot Selection")

# Available locations
raw_locations = sorted([loc for loc in df_raw["Location"].dropna().unique() if str(loc).strip() not in ["All Lots", "nan", "Unassigned", ""]])
all_lot_options = ["All Lots"] + (raw_locations if raw_locations else ["Portland / Clackamas", "Everett", "Tacoma", "Kitsap / Poulsbo"])

default_idx = 0
if param_lot:
    for idx, opt in enumerate(all_lot_options):
        if param_lot in opt.lower():
            default_idx = idx
            break

selected_location = st.sidebar.selectbox(
    "Active Store Lot",
    options=all_lot_options,
    index=default_idx
)

# Lot availability checkbox
gravel_only = st.sidebar.checkbox("In Stock 'On the Gravel' Only", value=True)

# Condition filter: New / Used / All (Defaults to New)
selected_condition = st.sidebar.radio(
    "Inventory Condition",
    options=["New", "Used", "All"],
    index=0,
    horizontal=True
)

st.sidebar.markdown("---")
st.sidebar.header("Length Filter (ft)")
st.sidebar.caption("Leave both at 0 for no length restrictions.")

col_len_min, col_len_max = st.sidebar.columns(2)
with col_len_min:
    min_length_input = st.number_input("Min Length", min_value=0, max_value=50, value=0, step=1)
with col_len_max:
    max_length_input = st.number_input("Max Length", min_value=0, max_value=50, value=0, step=1)

# ----------------- MAIN VEHICLE INPUTS -----------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Tow Vehicle Specs")
    entry_method = st.radio("Entry Method:", ["Door Placard (Fastest)", "Desk Lookup"], horizontal=True)

    sticker_payload = st.number_input(
        "Sticker Payload (Yellow Tag lbs)",
        min_value=500,
        max_value=8000,
        value=1650,
        step=50
    )
    truck_gvwr = st.number_input(
        "Truck GVWR (Safety Tag lbs)",
        min_value=3000,
        max_value=20000,
        value=7100,
        step=50
    )

with col2:
    st.subheader("2. Trip Loading & Passengers")
    towable_style = st.radio("Towable Style:", ["Travel Trailer (Bumper Pull)", "Fifth Wheel"], horizontal=True)
    occupants = st.number_input("Occupants in Truck (Total Count)", min_value=1, max_value=8, value=2, step=1)
    bed_cargo = st.number_input("Bed Cargo / Gear (lbs)", min_value=0, max_value=2500, value=150, step=25)
    hitch_hardware = st.number_input("Hitch Hardware Weight (lbs)", min_value=0, max_value=350, value=75, step=5)

# Capacity Calculations
passenger_allowance = occupants * 175
total_truck_occupant_cargo = passenger_allowance + bed_cargo + hitch_hardware
available_payload = sticker_payload - total_truck_occupant_cargo

st.markdown("---")
st.subheader("Vehicle Towing Envelope")

m1, m2, m3 = st.columns(3)
m1.metric("Gross Available Payload", f"{available_payload:,} lbs")
m2.metric("Occupant & Gear Load", f"{total_truck_occupant_cargo:,} lbs")
m3.metric("Max Tongue Weight Budget", f"{max(0, available_payload):,} lbs")

if available_payload <= 0:
    st.error("⚠️ Passenger and cargo weight exceeds vehicle payload capacity before hooking up a trailer.")

# ----------------- FILTERING & SAFETY RATINGS -----------------
df_matches = df_raw.copy()

# Filter by selected lot
if selected_location != "All Lots" and "Location" in df_matches.columns:
    df_matches = df_matches[df_matches["Location"] == selected_location]

# Filter by gravel / in stock status
if gravel_only and "Status" in df_matches.columns:
    df_matches = df_matches[df_matches["Status"].astype(str).str.contains("On Lot|Stock", case=False, na=False)]

# Filter by Condition (New / Used / All)
if selected_condition != "All":
    df_matches = df_matches[df_matches["Condition"] == selected_condition]

# Filter by length
if not (min_length_input == 0 and max_length_input == 0):
    if min_length_input > 0:
        df_matches = df_matches[df_matches["Length"] >= min_length_input]
    if max_length_input > 0:
        df_matches = df_matches[df_matches["Length"] <= max_length_input]

# Dynamic safety rating calculation (1 = Safe, 2 = Marginal)
def calculate_safety(row):
    tongue = row["HitchWeight"]
    if tongue <= (available_payload * 0.85):
        return pd.Series(["🟢 Safe to Tow", 1])
    elif tongue <= available_payload:
        return pd.Series(["🟡 Marginal (Pack Light)", 2])
    else:
        return pd.Series(["🔴 Overload", 3])

df_matches[["Tow Status", "SortOrder"]] = df_matches.apply(calculate_safety, axis=1)

# Keep only units within safe or marginal thresholds
df_matches = df_matches[df_matches["SortOrder"].isin([1, 2])].copy()

# Sort: Safe first (1 before 2), then lightest tongue weight
df_matches = df_matches.sort_values(by=["SortOrder", "HitchWeight"], ascending=[True, True])

st.markdown("---")
lot_display_title = f"{selected_location} Lot" if selected_location != "All Lots" else "All Lots"
condition_suffix = f" ({selected_condition})" if selected_condition != "All" else ""
st.subheader(f"Matching Inventory for {lot_display_title}{condition_suffix} — {len(df_matches)} Trailers Towable")

# Display Columns
show_cols = ["Image", "Tow Status", "Condition", "Model", "Length", "DryWeight", "GVWR", "HitchWeight", "Location", "URL"]
final_cols = [c for c in show_cols if c in df_matches.columns and df_matches[c].notnull().any() and (df_matches[c] != "").any()]

essential = ["Tow Status", "Condition", "Model", "Length", "DryWeight", "GVWR", "HitchWeight", "Location", "URL"]
for e in essential:
    if e in df_matches.columns and e not in final_cols:
        final_cols.append(e)

st.dataframe(
    df_matches[final_cols].rename(columns={
        "Length": "Length (ft)",
        "DryWeight": "Dry (lbs)",
        "GVWR": "GVWR (lbs)",
        "HitchWeight": "Tongue (lbs)"
    }),
    column_config={
        "Image": st.column_config.ImageColumn("Photo", help="Trailer Image"),
        "URL": st.column_config.LinkColumn("Listing", display_text="View RV")
    },
    use_container_width=True,
    hide_index=True
)