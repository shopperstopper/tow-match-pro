"""Tow Match Pro v1 inventory schema.

The adapter stores source facts separately from normalized/derived values.
Missing source facts remain missing. Matching-engine assumptions belong later.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

SCHEMA_VERSION = "1.0"

@dataclass
class SourceValue:
    value: Any = None
    raw: Optional[str] = None
    source_type: str = "dealer_vdp"
    source_url: Optional[str] = None
    confidence: str = "high"
    included_components: list[str] = field(default_factory=list)

@dataclass
class InventoryRecord:
    schema_version: str = SCHEMA_VERSION
    dealer_id: str = "apache_camping_center"
    source_url: str = ""
    scraped_at_utc: str = ""

    # Identity
    stock_number: Optional[str] = None
    vin: Optional[str] = None
    condition: Optional[str] = None
    year: Optional[int] = None
    manufacturer: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    floorplan: Optional[str] = None
    display_title: Optional[str] = None
    rv_category: Optional[str] = None
    major_type: Optional[str] = None

    # Availability / presentation
    location: Optional[str] = None
    inventory_status: Optional[str] = None
    sellable: Optional[bool] = None
    pipeline_stage: Optional[str] = None
    price_usd: Optional[int] = None
    image_url: Optional[str] = None
    sleeps: Optional[int] = None
    slides: Optional[int] = None

    # Normalized dimensions/weights
    overall_length_ft: Optional[float] = None
    exterior_width_in: Optional[float] = None
    exterior_height_in: Optional[float] = None
    uvw_lb: Optional[int] = None
    gvwr_lb: Optional[int] = None
    ccc_lb: Optional[int] = None
    published_hitch_pin_lb: Optional[int] = None

    # Tanks / equipment useful to category engines
    fresh_water_gal: Optional[float] = None
    gray_water_gal: Optional[float] = None
    black_water_gal: Optional[float] = None
    lp_tank_capacity_lb: Optional[float] = None
    lp_tank_count: Optional[int] = None
    axle_count: Optional[int] = None
    tire_size: Optional[str] = None

    # Truck-camper-specific normalized fields
    truck_bed_size: Optional[str] = None
    body_style: Optional[str] = None
    cg_front_in: Optional[float] = None
    # True only when the source establishes that the camper weight already includes factory options.
    weight_includes_factory_options: Optional[bool] = None

    # Preserve every VDP specification and material provenance.
    raw_specs: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    parse_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
