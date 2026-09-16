# Build 09 — GM Chevrolet/GMC Capability Layer

## Purpose
Add Chevrolet Silverado and GMC Sierra as manufacturer family #2 without changing the salesperson-first acquisition contract or allowing advertised maximums to masquerade as vehicle-specific ratings.

## What changed
- Added a GM capability provider beside Ford under the manufacturer-neutral dispatcher.
- Added GM configuration normalization for engine, drive, cab, and bed clues from VIN/vPIC data.
- Added support for GM's vehicle-specific Trailering Information Label as a high-value direct source. Tow Match can retain label-provided maximum payload, maximum tongue weight, GVWR, GCWR, and rear GAWR with Vehicle Label provenance.
- Added initial verified 2026 Silverado/Sierra 1500 exact guide rows with separate conventional and gooseneck/5th-wheel ratings.
- Added initial verified 2026 Silverado/Sierra 2500HD exact guide rows. GVWR is required where GM's table contains materially different ratings for otherwise similar body/engine configurations.
- Unknown or not-yet-installed configurations remain unresolved; no advertised maximum is substituted.
- Chevrolet and GMC share the GM provider contract while retaining their vehicle identity.

## Source policy
GM's own support material states that some vehicles have a driver-side doorjamb Trailering Information Label containing vehicle-specific curb weight, GVWR, GCWR, maximum payload, maximum tongue weight, and rear GAWR. Those direct vehicle-specific values are preferred when available.

GM's official trailering guide supplies configuration-specific conventional and gooseneck/5th-wheel trailer ratings. VIN/vPIC remains configuration identification only, never towing authority.

## Tests
101 automated tests pass across inventory ingestion, matching engine, stress tests, vehicle acquisition, Ford capability, automatic configuration, and GM capability.

New GM tests cover:
- exact Silverado 1500 conventional and fifth-wheel rows
- incomplete configuration staying unresolved
- exact Silverado 2500HD row selection
- GVWR-required ambiguity
- GMC dispatch through the same provider
- VIN/vPIC configuration normalization
- GM Trailering Information Label provenance and direct payload/max-tongue use

## Next build
RAM capability provider, using the same manufacturer-neutral contract and the same rule: exact/reliable vehicle-specific data where available; otherwise Verify, never guess.
