# Build 15 — Pilot Configuration & Major Type

## Purpose
Apply the three pilot-readiness changes identified in Build 14 without moving matching rules into Streamlit.

## Changes

### 1. Explicit Apache home lot
- Added `dealer_config.py`.
- Apache pilot home lot is explicitly configured as `Portland, OR`.
- `This Lot` now initializes from dealer configuration rather than alphabetic location order.
- If a configured home lot is not present for a category/condition, the UI safely falls back to an available lot.
- This is tenant/presentation configuration, not matching logic.

### 2. Major Type shopping control
- Added a compact `Major Type` selector beside Condition and Approximate Length.
- Travel Trailer / Fifth Wheel vocabulary: Bunkhouse, Toy Hauler, Couples / Non-Bunkhouse.
- Truck Camper vocabulary: Hard-Side, Pop-Up.
- Default is Any.
- Major Type is a shopping refinement only; it never relaxes Tow Match compatibility.
- Specific Unit Search bypasses Major Type just as it bypasses other shopping preferences.
- The current Apache sample CSV receives conservative title-based major-type normalization because it does not contain a MajorType column. The live VDP adapter remains the preferred source.

### 3. Apache truck-camper VDP acquisition
- Expanded Apache VDP aliases for truck bed size / recommended bed size / truck bed length and CG wording.
- Truck camper bed size, body style, and CG now receive explicit provenance records when Apache supplies them.
- No camper fit values are invented when Apache does not supply them.
- Missing camper-specific facts therefore remain Unable to Verify / Verify according to the matching engine.

## Tests
`python -m pytest -q`

Result: **128 passed**.

## Pilot configuration boundary
The home lot is deliberately isolated in `dealer_config.py`. A future multi-dealer deployment should load the equivalent values from dealer/tenant configuration rather than changing application code.
