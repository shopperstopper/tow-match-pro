# Build 08 — Automatic Vehicle Configuration Enrichment

## Purpose
Reduce salesperson technical entry before broadening manufacturer coverage. VIN decoding now feeds useful manufacturer-reported configuration clues into the Ford capability adapter automatically while preserving Tow Match's strict source hierarchy.

## What changed
- Added `vehicle_data/configuration.py` as a normalization boundary between VIN decoding and manufacturer capability providers.
- Ford configuration can now be filled from vPIC clues for drive type, engine description, cab/body clue, wheelbase, and bed length when those values are present.
- Explicit/label/reliable inputs always win over VIN-decoded clues. VIN data only fills blanks.
- Axle ratio, towing packages, max-tow equipment, and other decisive facts are **not guessed** when vPIC does not establish them.
- VIN/vPIC remains an identity/configuration source, never a towing-capacity authority. Ford's own towing guides/provider remain the capability source.
- The acquisition workflow remains failure-tolerant: incomplete VIN configuration produces Verify rather than blocking Tow Match.

## Why this matters
Build 07 proved exact Ford guide rows work, but manually supplying engine/cab/drive/wheelbase would violate the salesperson-first requirement. Build 08 begins removing those inputs from the salesperson's job. The remaining unresolved data becomes a much smaller exception set (for example axle ratio or tow-package status when truly decisive).

## Data-source policy
1. Actual / customer-specific / reliable vehicle-specific value
2. Vehicle label or other reliable direct source
3. Manufacturer capability data
4. NHTSA vPIC manufacturer-reported identity/configuration clues
5. Tow Match defaults only where the v1.0 standard explicitly permits them

No VIN-decoded clue is promoted into a tow rating by itself.

## Tests
93 automated tests pass. New tests cover vPIC-to-Ford configuration normalization and precedence of explicit configuration over decoded clues.

## Next build
Add the GM capability provider around GM's vehicle-specific Trailering Information Label and documented configuration data, while keeping the same manufacturer-neutral acquisition contract. Chevrolet/GMC is manufacturer family #2; RAM follows.
