# Build 14 — Salesperson UX Stress Test

Build 13 was exercised against the current 276-unit Apache sample inventory and the interface/business-logic paths were reviewed against the locked Tow Match Pro rules.

## What was run
- Full automated suite.
- Current Apache CSV normalization.
- Known-rating travel-trailer scenario using the 2019 Expedition-style limits.
- Payload-only / unknown-tow-rating scenario for unsupported brands.
- Higher-capability half-ton scenario.
- TT / Fifth Wheel / Truck Camper category switching logic.
- This Lot / All Dealer Locations / Pipeline scope behavior.
- Specific-unit searches for both compatible and failed units.
- Approximate-length preference behavior.
- Lot selection when a lot has zero compatible units.

## Problems found and fixed
1. **Approximate length was acting as a hard exclusion.** Rule 68 says it is normally a loose target. Build 14 retains all compatible RVs and ranks units in the selected length band first; known out-of-band units follow; unknown lengths remain visible last.
2. **The lot selector was derived from matched units rather than dealer inventory.** A lot could disappear merely because the current vehicle had zero matches there. Lots now come from sellable on-lot inventory for the selected category/condition.
3. **Specific Unit Search could still be blocked by shopping preferences.** It now bypasses condition and approximate-length preferences while retaining category, search scope, and every Tow Match compatibility gate.
4. **Zero-match expansion messaging was too vague.** The interface now checks whether broader on-lot matches actually exist before telling the salesperson to expand.

## Current inventory reality
The 276-unit sample normalizes to 191 Travel Trailers, 16 Fifth Wheels, and 69 Truck Campers. A large amount of source RV data remains incomplete, especially GVWR and truck-camper fit data. Those records remain Unable to Verify rather than receiving invented specifications.

## Remaining UX limitations worth addressing next
- The current sample does not contain stock numbers, so Specific Unit Search cannot yet reliably search stock number even though the commercial design calls for it.
- Major Type (bunkhouse, toy hauler, couples/non-bunkhouse, etc.) is not yet implemented because the current source does not provide a normalized major-type field.
- The pilot has no configured salesperson/home lot, so the first This Lot selection is alphabetical rather than dealer/user configured.
- Truck Camper results are often Unable to Verify because the sample CSV lacks bed requirement, CG, water/LP/battery and related camper fields. The VDP-aware acquisition adapter should be the path to improve this, not UI guesses.
- This environment does not have Streamlit installed, so the actual browser rendering could not be launched here. The complete UI logic, imports other than Streamlit runtime, scenario paths, and automated tests were exercised. A real browser pilot remains the next visual/usability check.

## Test result
**124 tests passed.**
