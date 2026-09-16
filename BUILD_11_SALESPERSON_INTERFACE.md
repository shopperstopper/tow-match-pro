# Build 11 — Salesperson Interface

## What this build does
Build 11 assembles the first new Tow Match Pro salesperson-facing Streamlit pilot on top of the independent matching engine. The interface is intentionally thin: matching rules remain in `tow_match/`, not in Streamlit.

### Workflow
1. Tow Vehicle — payload is the minimum useful input; VIN is independent; unknown tow rating is allowed.
2. Shopping — Travel Trailer / Fifth Wheel / Truck Camper, Condition, approximate length, and specific-unit search.
3. Results — current lot first, then all dealer locations, then pipeline. Results show Match / Verify / Unable to Verify; hard failures are excluded from ordinary results.
4. `Why This Matches` exposes calculations, gates, assumptions, and advisories without cluttering the normal card.
5. `View RV` opens the dealer VDP. `New Tow Match` clears the active session.

## Important pilot limitation
The bundled Apache CSV is the **legacy** inventory snapshot and does not contain the v1 normalized `rv_category` field. Build 11 therefore includes a UI-only compatibility classifier so the interface can be exercised now. This classifier is **not part of the matching engine and is not the commercial ingestion design**. The validated Apache v1 adapter / future dealer feed must supply category explicitly.

Likewise, the interface exposes known payload/tow-rating inputs immediately. The vehicle acquisition/manufacturer packages remain independent and can be connected to label/VIN scanning without changing the matching engine or result UI.

## Additional correction
While assembling the interface, RAM manufacturer dispatch in `vehicle_data/acquisition.py` was corrected so RAM vehicles receive `RamVehicleConfig` rather than falling through the GM configuration branch.

## Validation
- `python -m compileall -q .`
- `python -m pytest -q`
- **110 tests passing**

## Run locally
```bash
pip install -r requirements.txt
streamlit run salesperson_app.py
```

The app is a pilot presentation layer only. It does not own matching logic, dealer adapters, or manufacturer capability rules.
