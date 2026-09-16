# Build 03 — Independent Matching Engine

This build moves Tow Match Pro qualification logic out of Streamlit and into the reusable `tow_match` package.

## Implemented
- Shared `VehicleState`, `MatchResult`, `GateResult`, and four-state status model.
- Travel Trailer engine: normal cargo bands, 13% qualification tongue, 15% verification condition, published hitch floor, payload gate, conventional tow-rating gate, manufacturer max tongue gate, GVWR verification behavior, reserve indicators.
- Fifth Wheel engine: FW cargo bands, 20% qualification pin, 25% verification condition, published pin floor, 200-lb hitch default, independent FW/gooseneck tow rating, manufacturer max pin gate.
- Truck Camper engine foundation: full-fresh assumption, propane/battery fallbacks, 500-lb personal cargo, option allowance, mounting equipment, payload/CWR gates, bed fit, manufacturer eligibility, CG when applicable, known rear-GAWR/tire gates, camper reserve indicators.
- Unknown data is not converted to a hard failure. Missing RV source data can classify `UNABLE TO VERIFY`; missing vehicle verification can classify `PRELIMINARY MATCH — VERIFY`.
- Known hard-gate failures classify `NOT A MATCH` and retain quantified gate diagnostics.

## Architecture
The engine imports no Streamlit code and has no dealer-specific logic. Dealer adapters produce normalized records; the matching engine consumes them; any future UI/API can consume structured `MatchResult` objects.

## Tests
The combined adapter + matching-engine test suite passes with `python -m pytest -q`.

## Important next work
This is the matching-engine foundation, not the finished commercial application. Before UI integration we should expand the scenario matrix, especially Truck Camper manufacturer-specific carrying-capacity basis/CG/fit cases and provenance-driven replacement of estimates by better data.
