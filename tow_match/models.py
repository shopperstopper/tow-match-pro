from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any

class MatchStatus(str, Enum):
    MATCH = "MATCH"
    PRELIMINARY = "PRELIMINARY MATCH — VERIFY"
    UNABLE = "UNABLE TO VERIFY — Relevant Data Missing From Inventory Record"
    NOT_MATCH = "NOT A MATCH"

@dataclass
class VehicleState:
    payload_lb: Optional[float] = None
    tow_rating_lb: Optional[float] = None
    fifth_wheel_tow_rating_lb: Optional[float] = None
    max_tongue_lb: Optional[float] = None
    max_pin_lb: Optional[float] = None
    occupant_weight_lb: float = 0
    pets_weight_lb: float = 0
    truck_cargo_lb: float = 150
    hitch_hardware_lb: Optional[float] = None
    # Truck-camper vehicle facts
    camper_carrying_capacity_lb: Optional[float] = None
    bed_size: Optional[str] = None
    camper_eligible: Optional[bool] = None
    camper_cg_min_in: Optional[float] = None
    camper_cg_max_in: Optional[float] = None
    truck_class: Optional[str] = None
    rear_wheel_config: Optional[str] = None
    rear_gawr_remaining_lb: Optional[float] = None
    tire_capacity_remaining_lb: Optional[float] = None

@dataclass
class GateResult:
    name: str
    passed: Optional[bool]
    message: str
    required: bool = True
    amount_over_lb: Optional[float] = None

@dataclass
class MatchResult:
    status: MatchStatus
    category: str
    estimated_loaded_lb: Optional[float] = None
    qualification_load_lb: Optional[float] = None
    upper_verify_load_lb: Optional[float] = None
    available_payload_lb: Optional[float] = None
    reserve_lb: Optional[float] = None
    reserve_label: Optional[str] = None
    gates: list[GateResult] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    calculations: dict[str, Any] = field(default_factory=dict)

    @property
    def is_tow_match_result(self) -> bool:
        return self.status != MatchStatus.NOT_MATCH
