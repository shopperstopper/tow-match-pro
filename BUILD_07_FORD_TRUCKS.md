# Build 07 — Ford F-150 / Super Duty Capability Expansion

## Purpose
Expand the manufacturer capability layer beyond the 2019 Expedition into Ford's high-value RV tow vehicles while preserving Tow Match Pro's rule: never guess a vehicle-specific rating from a headline maximum.

## Implemented
- Expanded `FordVehicleConfig` with engine, cab, wheelbase, box length and package/configuration fields.
- Added 2026 F-150 capability resolution from exact rows of Ford's 2026 F-150 Towing Guide v4.
- Added separate conventional and fifth-wheel/gooseneck ratings where an exact verified row is installed.
- Added 2026 F-150 axle-code mapping from Ford's current guide. This is deliberately model/year-specific; code `15` means 3.15 on 2026 F-150 but 3.31 in the 2019 Expedition adapter.
- Added initial 2026 F-250/F-350 Super Duty exact-row conventional resolution from Ford's 2026 Super Duty guide v3.
- Added Ford factory receiver maximum tongue limits as a separate manufacturer gate (F-250 2,200 lb; F-350 SRW 2,500 lb; F-450 DRW 3,000 lb where applicable). These never substitute for the configuration-specific tow rating.
- Unknown or not-yet-installed configurations remain unresolved and flow to Verify rather than being assigned Ford's advertised maximum.
- The provider is table-driven and intentionally conservative: only exact verified guide rows are installed.

## Important finding
Ford axle codes are not globally stable across model families/years. A generic Ford axle-code decoder would be unsafe. Tow Match must resolve axle code in the context of model/year.

## Test status
91 automated tests pass.

## Next development target
Continue populating verified Ford F-150/Super Duty rows and improve automatic configuration acquisition, then add GM as the second manufacturer family. The architecture should favor reliable VIN/build/configuration sources over asking salespeople to identify technical configuration fields manually.
