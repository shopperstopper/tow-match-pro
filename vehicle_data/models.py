from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any

class DataSource(str, Enum):
    ACTUAL = 'Actual / Customer-Specific'
    VEHICLE_LABEL = 'Vehicle Label'
    MANUFACTURER = 'Manufacturer'
    NHTSA_VPIC = 'NHTSA vPIC'
    MANUAL_RELIABLE = 'Manual Reliable Source'
    TOW_MATCH_DEFAULT = 'Tow Match Default'

@dataclass
class VehicleFact:
    value: Any
    source: DataSource
    confidence: str = 'high'
    detail: Optional[str] = None

@dataclass
class VehicleIdentity:
    vin: Optional[str] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    series: Optional[str] = None
    body_class: Optional[str] = None
    drive_type: Optional[str] = None
    engine: Optional[str] = None
    bed_length_in: Optional[float] = None

@dataclass
class VehicleAcquisitionInput:
    # Quick-acquisition inputs. Payload and VIN are intentionally independent.
    vin: Optional[str] = None
    payload_label_lb: Optional[float] = None
    # Optional values already known from a reliable vehicle-specific source.
    conventional_tow_rating_lb: Optional[float] = None
    fifth_wheel_tow_rating_lb: Optional[float] = None
    max_tongue_lb: Optional[float] = None
    max_pin_lb: Optional[float] = None
    camper_carrying_capacity_lb: Optional[float] = None
    camper_eligible: Optional[bool] = None
    bed_size: Optional[str] = None
    camper_cg_min_in: Optional[float] = None
    camper_cg_max_in: Optional[float] = None
    rear_gawr_remaining_lb: Optional[float] = None
    tire_capacity_remaining_lb: Optional[float] = None
    # Optional manufacturer/configuration clues acquired automatically or from labels.
    axle_code: Optional[str] = None
    axle_ratio: Optional[float] = None
    drive: Optional[str] = None
    wheelbase_variant: Optional[str] = None
    heavy_duty_trailer_tow: Optional[bool] = None
    fifth_wheel_gooseneck_prep: Optional[bool] = None
    # GM trailering/configuration facts; may come from the vehicle-specific Trailering Information Label or VIN/config data.
    gm_engine: Optional[str] = None
    gm_cab: Optional[str] = None
    gm_bed: Optional[str] = None
    gm_wheel_size_in: Optional[float] = None
    gm_gvwr_lb: Optional[float] = None
    gm_gcwr_lb: Optional[float] = None
    gm_rear_gawr_lb: Optional[float] = None
    gm_label_max_payload_lb: Optional[float] = None
    gm_label_max_tongue_lb: Optional[float] = None
    # Loading inputs/defaults used by the matching engine.
    occupant_weight_lb: float = 0
    pets_weight_lb: float = 0
    truck_cargo_lb: float = 150
    hitch_hardware_lb: Optional[float] = None

@dataclass
class VehicleAcquisitionResult:
    identity: VehicleIdentity = field(default_factory=VehicleIdentity)
    facts: dict[str, VehicleFact] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def fact_value(self, name: str, default=None):
        fact = self.facts.get(name)
        return fact.value if fact is not None else default
