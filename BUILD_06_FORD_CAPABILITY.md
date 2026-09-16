# Build 06 — Ford Manufacturer Capability Layer

## Purpose
Add the first manufacturer-specific capability adapter without coupling Tow Match Pro to Streamlit, Apache, or an undocumented manufacturer web endpoint.

## Implemented
- Manufacturer-neutral `ManufacturerCapabilityService` dispatcher.
- Ford capability provider with explicit provenance.
- Ford configuration clues: axle code/ratio, drive, Expedition SWB/MAX, Heavy-Duty Trailer Tow status, fifth-wheel/gooseneck prep placeholder.
- Verified 2019 Expedition selector rules from Ford's official 2019 Expedition towing guide.
- 2019 Expedition axle-code mapping: 10 -> 3.15, 15 -> 3.31, 3L -> 3.73.
- Known Tow Match test vehicle (`1FMJU2AT7KEA31907`, 2019 Expedition Limited 4WD, axle code 15) resolves to a manufacturer-sourced 6,000-lb conventional tow rating when identity/configuration are supplied.
- Manufacturer enrichment fills missing facts and does not overwrite a reliable manual value already supplied.
- Ambiguous Ford configurations remain unresolved; Tow Match therefore keeps the appropriate Verify behavior rather than guessing.
- No universal max-tongue value is inferred from the Ford trailer selector; hitch/package-specific receiver limits remain separate facts to acquire when reliable.

## Why no Ford web scraping/API dependency
Ford's public towing page states that towing capacity may be obtained from its VIN-based Towing Calculator or RV Towing Guides. Build 06 uses documented guide rules as the first dependable adapter and keeps the provider interface replaceable. We do not depend on an undocumented endpoint that could disappear or change.

Official sources used for rule verification:
- Ford Towing hub: https://www.ford.com/towing/
- Ford 2019 Expedition towing guide: https://www.ford.com/cmslibs/content/dam/brand_ford/en_us/brand/resources/general/pdf/guides/19Towing_Ford_Expedition_r1_Dec21.pdf

## Tests
86 automated tests pass across adapter, matching engine, stress suite, vehicle acquisition, and Ford capability layer.

## Next
Expand the Ford provider beyond the Expedition to the high-value dealer tow-vehicle families, beginning with F-150 and Super Duty. The adapter should continue to resolve only configurations supported by reliable manufacturer data; otherwise it returns unresolved facts for interest-driven verification.
