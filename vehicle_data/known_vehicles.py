"""Verified vehicle-specific facts cache.

This is not a VIN decoder and must never contain inferred capability values. It is a small
cache of vehicle facts that Tow Match has independently verified from reliable vehicle/manufacturer
sources. A future persistent capability cache can implement the same idea.
"""

KNOWN_VEHICLES = {
    # Tow Match development/pilot validation vehicle. Axle code and package status were
    # verified from this vehicle; the tow rating itself is still resolved by FordCapabilityProvider.
    '1FMJU2AT7KEA31907': {
        'identity': {
            'year': 2019, 'make': 'FORD', 'model': 'Expedition', 'trim': 'Limited',
            'drive_type': '4WD/4-Wheel Drive',
        },
        'ford_config': {
            'axle_code': '15',
            'drive': '4x4',
            'wheelbase_variant': 'SWB',
            'heavy_duty_trailer_tow': False,
        },
        'detail': 'Verified Tow Match pilot vehicle configuration; Ford capability remains manufacturer-resolved',
    },
}

def get_known_vehicle(vin):
    return KNOWN_VEHICLES.get((vin or '').strip().upper())
