# Tow Match Pro — Build 10: RAM Capability Layer

## Result
Build 10 adds RAM as the third manufacturer-specific capability provider, alongside Ford and GM.

## Implemented
- `vehicle_data/manufacturers/ram.py`
- RAM dispatch through `ManufacturerCapabilityService`
- RAM vPIC configuration conversion and merge helpers
- Verified exact 2026 RAM 1500 configuration rows from RAM's published Payload & Towing Weight Capacities guide
- Separate manufacturer fact for the 2026 RAM 1500 Class IV receiver 1,100 lb maximum tongue weight
- Explicit refusal to substitute RAM's advertised model/engine maximums for a vehicle-specific tow rating
- Initial 2500/3500 recognition with safe unresolved/Verify behavior until exact 2026 HD configuration rows are installed

## Important product behavior
Tow Match requires an exact enough configuration before assigning a manufacturer tow rating. For the installed 2026 RAM 1500 table this means engine, drive, cab, bed and axle ratio. vPIC can fill many identity/configuration clues, but it does not invent axle ratio.

The RAM 1500 guide itself shows why this matters. The same 3.0L Hurricane SO engine has materially different trailer ratings depending on axle ratio, drive, cab and bed. Tow Match therefore never takes the advertised 11,610 lb maximum and applies it to every Hurricane-equipped RAM 1500.

For 2026 RAM 2500/3500, RAM publishes useful maximum capability figures online, but Build 10 deliberately does not treat those headline maxima as exact vehicle ratings. Those trucks remain unresolved until a sufficiently specific manufacturer table/source is installed.

## Verification
`python -m pytest -q`

Result: **107 passed**.

## Next build
Stop broad manufacturer expansion temporarily and assemble the first new salesperson-facing Tow Match Pro interface over the independent inventory adapter, vehicle acquisition/manufacturer capability service, and matching engine.
