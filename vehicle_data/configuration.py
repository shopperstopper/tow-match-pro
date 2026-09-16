from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .models import VehicleIdentity
from .manufacturers.ford import FordVehicleConfig


def _num(v):
    try:
        if v in (None, '', 'Not Applicable', '0'): return None
        return float(str(v).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def _text(*vals):
    return ' '.join(str(v).strip() for v in vals if v not in (None, '', 'Not Applicable')).strip()


def _drive(v):
    s=(v or '').upper().replace(' ', '')
    if any(x in s for x in ('4WD','4X4')): return '4x4'
    if any(x in s for x in ('RWD','4X2','2WD')): return '4x2'
    if 'AWD' in s: return 'AWD'
    return None


def _cab_from_vpic(d: dict) -> Optional[str]:
    # vPIC frequently exposes pickup cab clues through BodyClass/Series/Trim rather than a single cab field.
    s=_text(d.get('CabType'), d.get('BodyClass'), d.get('Series'), d.get('Trim')).upper()
    if 'SUPERCREW' in s or 'SUPER CREW' in s: return 'SUPERCREW'
    if 'SUPERCAB' in s or 'SUPER CAB' in s or 'EXTENDED CAB' in s: return 'SUPERCAB'
    if 'REGULAR CAB' in s or 'REG CAB' in s: return 'REGULAR'
    if 'CREW CAB' in s: return 'CREW'
    return None


def _engine_from_vpic(d: dict) -> Optional[str]:
    # Preserve manufacturer/NHTSA wording. Ford adapter owns normalization.
    return _text(d.get('EngineModel'), d.get('DisplacementL'), d.get('EngineConfiguration'), d.get('FuelTypePrimary')) or None


def ford_config_from_vpic(identity: VehicleIdentity, d: dict) -> FordVehicleConfig:
    """Convert manufacturer-reported vPIC configuration clues into Ford adapter input.

    This intentionally does not invent axle ratio or towing packages: those are often not encoded by vPIC.
    The goal is to eliminate salesperson entry for facts vPIC can reliably provide and leave only decisive
    unresolved facts for exception-driven acquisition.
    """
    bed_in=_num(d.get('BedLengthIN')) or identity.bed_length_in
    wb=_num(d.get('WheelBaseShort')) or _num(d.get('WheelBaseLong')) or _num(d.get('WheelBaseType'))
    return FordVehicleConfig(
        drive=_drive(d.get('DriveType') or identity.drive_type),
        engine=_engine_from_vpic(d) or identity.engine,
        cab=_cab_from_vpic(d),
        wheelbase_in=wb,
        box_length_ft=(bed_in / 12.0) if bed_in else None,
    )


def merge_ford_config(primary: FordVehicleConfig, fallback: FordVehicleConfig) -> FordVehicleConfig:
    """Explicit/label/manufacturer facts win; VIN-decoded clues fill only blanks."""
    vals={}
    for name in FordVehicleConfig.__dataclass_fields__:
        p=getattr(primary,name)
        vals[name]=p if p is not None else getattr(fallback,name)
    return FordVehicleConfig(**vals)

from .manufacturers.gm import GMVehicleConfig

def _gm_cab_from_vpic(d: dict) -> Optional[str]:
    s=_text(d.get('CabType'),d.get('BodyClass'),d.get('Series'),d.get('Trim')).upper()
    if 'DOUBLE' in s or 'EXTENDED' in s: return 'DOUBLE'
    if 'CREW' in s: return 'CREW'
    if 'REGULAR' in s or 'REG CAB' in s: return 'REGULAR'
    return None

def _gm_bed_from_vpic(identity: VehicleIdentity, d: dict) -> Optional[str]:
    bed=_num(d.get('BedLengthIN')) or identity.bed_length_in
    if not bed: return None
    if bed >= 90: return 'LONG'
    if bed >= 75: return 'STANDARD'
    return 'SHORT'

def gm_config_from_vpic(identity: VehicleIdentity, d: dict) -> GMVehicleConfig:
    """Use vPIC only for GM identity/configuration clues; never as towing authority."""
    return GMVehicleConfig(
        engine=_engine_from_vpic(d) or identity.engine,
        drive=_drive(d.get('DriveType') or identity.drive_type),
        cab=_gm_cab_from_vpic(d),
        bed=_gm_bed_from_vpic(identity,d),
    )

def merge_gm_config(primary: GMVehicleConfig, fallback: GMVehicleConfig) -> GMVehicleConfig:
    vals={}
    for name in GMVehicleConfig.__dataclass_fields__:
        p=getattr(primary,name)
        vals[name]=p if p is not None else getattr(fallback,name)
    return GMVehicleConfig(**vals)


from .manufacturers.ram import RamVehicleConfig

def _ram_cab_from_vpic(d: dict) -> Optional[str]:
    s=_text(d.get('CabType'),d.get('BodyClass'),d.get('Series'),d.get('Trim')).upper()
    if 'QUAD' in s or 'EXTENDED' in s: return 'QUAD'
    if 'MEGA' in s: return 'MEGA'
    if 'CREW' in s: return 'CREW'
    if 'REGULAR' in s or 'REG CAB' in s: return 'REGULAR'
    return None

def _ram_bed_from_vpic(identity: VehicleIdentity, d: dict) -> Optional[str]:
    bed=_num(d.get('BedLengthIN')) or identity.bed_length_in
    if not bed: return None
    if bed >= 90: return '8-0'
    if bed >= 72: return '6-4'
    return '5-7'

def ram_config_from_vpic(identity: VehicleIdentity, d: dict) -> RamVehicleConfig:
    """Use vPIC for RAM configuration clues only; RAM remains towing authority."""
    return RamVehicleConfig(
        engine=_engine_from_vpic(d) or identity.engine,
        drive=_drive(d.get('DriveType') or identity.drive_type),
        cab=_ram_cab_from_vpic(d),
        bed=_ram_bed_from_vpic(identity,d),
    )

def merge_ram_config(primary: RamVehicleConfig, fallback: RamVehicleConfig) -> RamVehicleConfig:
    vals={}
    for name in RamVehicleConfig.__dataclass_fields__:
        p=getattr(primary,name)
        vals[name]=p if p is not None else getattr(fallback,name)
    return RamVehicleConfig(**vals)
