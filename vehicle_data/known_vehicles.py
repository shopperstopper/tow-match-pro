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
    # 2026 F-250 Tow Match regression vehicle. Configuration and category-specific ratings
    # were verified from the vehicle-specific dealer/OEM technical record supplied during pilot development.
    # This cache proves the VIN -> verified capability path; it is not a generic VIN inference rule.
    '1FT7W2BT7TEF56538': {
        'identity': {
            'year': 2026, 'make': 'FORD', 'model': 'F-250', 'trim': 'XL',
            'drive_type': '4WD/4-Wheel Drive', 'engine': '6.7L Power Stroke diesel',
            'bed_length_in': 98.1,
        },
        'ford_config': {
            'axle_ratio': 3.73,
            'drive': '4x4',
            'engine': '6.7 DIESEL',
            'cab': 'CREW',
            'wheelbase_in': 176.0,
            'box_length_ft': 8.175,
        },
        'capability': {
            'tow_rating_lb': 13800,
            'fifth_wheel_tow_rating_lb': 13600,
        },
        'detail': 'Verified vehicle-specific Tow Match pilot record',
    },
}

def get_known_vehicle(vin):
    return KNOWN_VEHICLES.get((vin or '').strip().upper())
