# Tow Match Pro v1 — Build 04: Matching Engine Stress Test

## Result
The independent matching engine was exercised against a substantially expanded boundary and scenario matrix before any UI work.

- 68 automated tests pass.
- The suite includes 2,000 deterministic randomized TT/FW scenarios in addition to named boundary cases.
- All three RV-category engines remain independent of Streamlit and dealer-specific ingestion.

## Defects / specification mismatches found and corrected

### 1. Rule 4 status mismatch
The Build 03 engine made a towable `PRELIMINARY` when estimated normal loaded weight passed the vehicle tow rating but the RV's full GVWR exceeded the rating. Locked Rule 4 says this remains a `MATCH` with a `Verify loading before delivery` warning.

Corrected by separating **advisories** from **missing qualification information**. An advisory no longer downgrades qualification status by itself.

### 2. Truck-camper factory-option double counting risk
Build 03 always added the Rule 35 10%/300-lb factory-option allowance whenever dry weight existed. That was wrong when a reliable source establishes that the supplied weight already includes factory options.

Added `weight_includes_factory_options`. When true, option allowance is zero. When not established, the Rule 35 estimate remains 10%, capped at 300 lb.

### 3. Invalid RV weight relationship
A malformed source record with GVWR below UVW could previously produce an impossible estimated loaded weight below dry weight because the normal-loaded calculation caps at GVWR.

Now GVWR < UVW is treated as inconsistent RV source data and returns `UNABLE TO VERIFY`, never a fabricated lighter loaded weight.

## Boundary coverage added

### Travel Trailer
- Every Rule 5 cargo-band boundary (3,999/4,000; 5,999/6,000; 7,999/8,000).
- GVWR cap on normal loaded weight.
- Exact 13% qualification threshold.
- One-pound payload failure below threshold.
- 13%-15% verification band.
- Published hitch floor.
- Independent manufacturer max-tongue gate.
- Known tow-rating failure.
- Full-GVWR-over-rating / normal-load-passes advisory behavior.
- Missing vehicle payload vs missing RV data classification.
- Multiple simultaneous hard-gate failures.
- Occupant/pet/truck-cargo/hitch deductions.

### Fifth Wheel
- Every Rule 21 cargo-band boundary.
- GVWR cap.
- 20% qualification / 25% verification behavior.
- Published pin floor.
- Dedicated fifth-wheel rating requirement (never conventional substitution).
- Full-GVWR advisory behavior.
- Invalid GVWR/UVW source data.

### Truck Camper
- Full fresh-water calculation and 250-lb fallback.
- Propane published-capacity path and 30-lb fallback.
- Battery 65-lb fallback.
- Factory-option 10% allowance and 300-lb cap.
- Known factory-optioned weight suppressing the allowance.
- Payload and manufacturer CWR evaluated independently.
- Known bed mismatch.
- Missing bed information.
- Manufacturer eligibility known-pass / known-fail / unknown.
- CG in range, out of range, missing when applicable, and not required when truck has no applicable CG range.
- Rear GAWR and tire-capacity known failures.
- Negative payload reserve.
- Minimal reserve plus material estimates -> Preliminary.

## Randomized invariant tests
Two deterministic 1,000-case loops exercise TT and FW combinations across broad ranges of UVW, GVWR, payload, tow rating, occupants, pets, and cargo. Invariants include:

- estimated normal loaded weight never below UVW or above GVWR for valid records;
- any known mandatory payload/tow hard-gate failure must produce `NOT A MATCH`;
- randomized cases execute without exceptions.

These are deterministic (fixed seeds), so failures are reproducible.

## Deliberately not invented
Truck-camper manufacturer CWR definitions can differ by manufacturer/source. Rule 33 requires equivalent-basis normalization. Build 04 does not invent a universal conversion for manufacturer CWR. That belongs in the manufacturer-specific vehicle-data acquisition/normalization layer, where the source definition can be preserved and converted correctly.

Likewise, manufacturer-specific camper fit/class/SRW/DRW rules require actual manufacturer data rather than generic assumptions.

## Next step
Proceed to the vehicle-data acquisition layer. It should produce normalized vehicle facts (with provenance and basis) that the tested engine consumes. Streamlit remains outside the business logic.
