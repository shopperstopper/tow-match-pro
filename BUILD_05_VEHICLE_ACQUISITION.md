# Build 05 — Vehicle Data Acquisition Foundation

## Purpose
Create a Streamlit-independent bridge between quick salesperson inputs and the normalized `VehicleState` consumed by the tested matching engine.

## Implemented
- VIN normalization and North-American check-digit validation.
- Payload-label quick path independent of VIN acquisition.
- Optional single-VIN NHTSA vPIC identity decoder adapter.
- Graceful degradation: bad VIN or unavailable VIN service never blocks a Tow Match when payload/manual data is usable.
- Provenance-bearing vehicle facts.
- Optional reliable vehicle-specific conventional tow rating, fifth-wheel rating, tongue/pin limits, camper capacity/eligibility/bed/CG and remaining axle/tire capacity.
- Conversion into the existing independent matching-engine `VehicleState`.
- No Streamlit dependency and no dealer-specific dependency.

## Deliberate boundary
NHTSA vPIC is an identity/configuration source, not a tow-rating authority. This build does **not** pretend a VIN alone universally produces an exact tow rating. Manufacturer-specific rating adapters are the next enrichment layer and must only emit a rating when the source/configuration match is reliable.

## Rules directly supported
97 Progressive Vehicle Data Acquisition; 98 Frictionless Data Confirmation (data model side); 99 Deferred Tow-Rating Verification; 18 Better Information Replaces Defaults; 52 provenance; 53 exception-driven collection.

## Next
Implement manufacturer-specific vehicle capability providers, starting with Ford, with explicit confidence/provenance and no undocumented/brittle API dependency. Then expose the acquisition flow in the salesperson UI.
