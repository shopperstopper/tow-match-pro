# Tow Match Pro — Build 12 Interface Stress Test

## Purpose
Stress-test the first salesperson interface against the locked v1.0 product rules and realistic sales workflows, then fix defects rather than adding unrelated features.

## Result
115 automated tests pass.

## Defects found and corrected

1. **Development Expedition leaked into production defaults.** Build 11 started every New Tow Match with payload 1,501 lb, tow rating 6,000 lb and the test Expedition VIN. Build 12 starts blank. The only retained defaults are product-standard loading defaults (2 adults and 150 lb truck cargo/gear).

2. **Ford/GM/RAM acquisition work was not actually connected to the UI.** Build 11 displayed a VIN field but did not call the acquisition/manufacturer layer. Build 12 invokes vehicle acquisition when Find Tow Matches is pressed, uses vPIC only for identity/configuration clues, and lets manufacturer capability providers fill reliable missing facts. Failure is non-blocking.

3. **Legacy Apache fifth-wheel classification was broken.** The temporary compatibility classifier identified zero fifth wheels. Build 12 recognizes the fifth-wheel families actually present in the snapshot. Current legacy snapshot classification: 188 Travel Trailers, 17 Fifth Wheels, 71 Truck Campers.

4. **Legacy compact lengths corrupted filtering/display.** Values such as 253, 286 and 402 were being treated as feet. Build 12 applies a constrained compatibility decoder (253 = 25 ft 3 in; 286 = 28 ft 6 in; 402 = 40 ft 2 in). It does not use the old blanket divide-by-12 workaround.

5. **Specific Unit Search violated Rule 82.** Build 11 hid a specifically searched RV if it failed Tow Match. Build 12 deliberately shows the requested unit as NOT A MATCH with the failed gate explanation. Normal browsing still hides Not Match inventory.

6. **Verify This Match did nothing.** Build 12 makes the control reveal the exact missing information for that result. For Unable to Verify it follows Rule 107: show what is missing and do not launch a search or invent data.

7. **Category state violated Rules 109–110.** Build 11 shared scope/filter state across TT/FW/Truck Camper. Build 12 remembers Condition, Length, Specific Search, Search Scope and current lot independently for each category. Changing category retains the Active Tow Match.

8. **Tow Match total could conceptually include a specifically searched failure.** Build 12 counts only Match, Verify and Unable as Tow Matches. A specifically searched Not Match can be displayed but is not included in the Tow Match total.

## Scenario beating

- 2019 Expedition-style known payload/tow rating: produces both confirmed matches and exclusions; normal browse only presents the Tow Matches.
- Other-brand payload-only vehicle: payload-qualified trailers remain Preliminary/Verify rather than being rejected for unknown tow rating.
- Fifth-wheel capable pickup: fifth-wheel inventory now exists in the interface and exercises FW matching.
- Truck-camper pickup: incomplete camper/vehicle fit data remains Verify, consistent with the product standard.
- This Lot / All Dealer Locations / Pipeline: scope is monotonic and category-specific.
- Length boundaries: normalized lengths are used before filtering.
- Specific heavy unit with undersized tow vehicle: requested unit remains visible as Not Match with explanation.

## Remaining deliberate limitations

- The bundled Apache inventory is still a legacy snapshot. The UI compatibility classifier is temporary; normalized live adapter inventory should replace it.
- The interface does not yet capture every manufacturer-specific clue that could resolve a Preliminary result. This is intentional under the progressive-acquisition rules; verification should request only the information that matters to an interested unit.
- Truck-camper matching will frequently remain Verify until bed/eligibility/CG or equivalent manufacturer facts are available.
- This build is a Streamlit pilot UI, not the eventual commercial frontend.

## Recommendation
Build 12 is a materially safer pilot than Build 11. The next build should focus on **real inventory ingestion into the interface and end-to-end pilot usability**, not additional manufacturers or CRM-style features.
