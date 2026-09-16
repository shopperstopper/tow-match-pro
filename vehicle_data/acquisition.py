from __future__ import annotations
import re
from typing import Optional
from .models import DataSource, VehicleFact, VehicleIdentity, VehicleAcquisitionInput, VehicleAcquisitionResult
from tow_match.models import VehicleState

VIN_RE = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')
_TRANSLIT = {**{str(i):i for i in range(10)}, **dict(zip('ABCDEFGH', [1,2,3,4,5,6,7,8])), **dict(zip('JKLMNPR', [1,2,3,4,5,7,9])), **dict(zip('STUVWXYZ', [2,3,4,5,6,7,8,9]))}
_WEIGHTS = [8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2]

def normalize_vin(vin: Optional[str]) -> Optional[str]:
    if not vin: return None
    return re.sub(r'[^A-Za-z0-9]', '', vin).upper()

def vin_is_valid(vin: Optional[str]) -> bool:
    vin = normalize_vin(vin)
    if not vin or not VIN_RE.fullmatch(vin): return False
    try:
        total=sum(_TRANSLIT[c]*w for c,w in zip(vin,_WEIGHTS))
    except KeyError:
        return False
    check='X' if total % 11 == 10 else str(total % 11)
    return vin[8] == check

def _num(v):
    try:
        if v in (None,'','Not Applicable'): return None
        return float(str(v).replace(',','').strip())
    except (ValueError,TypeError): return None

def _identity_from_vpic(vin: str, d: dict) -> VehicleIdentity:
    bed_in = _num(d.get('BedLengthIN'))
    year = _num(d.get('ModelYear'))
    eng = d.get('EngineModel') or d.get('DisplacementL')
    return VehicleIdentity(vin=vin, year=int(year) if year else None,
        make=d.get('Make') or None, model=d.get('Model') or None, trim=d.get('Trim') or None,
        series=d.get('Series') or None, body_class=d.get('BodyClass') or None,
        drive_type=d.get('DriveType') or None, engine=str(eng) if eng else None, bed_length_in=bed_in)

def acquire_vehicle(inp: VehicleAcquisitionInput, vpic_client=None, manufacturer_provider=None) -> VehicleAcquisitionResult:
    """Acquire the minimum useful vehicle state without making the salesperson hunt technical data.

    Precedence is enforced by only placing reliable supplied facts here. Manufacturer adapters can
    enrich this result later; missing secondary facts remain missing and therefore drive Verify.
    """
    out=VehicleAcquisitionResult()
    vin=normalize_vin(inp.vin)
    decoded = {}
    known = None
    if vin:
        if vin_is_valid(vin):
            out.identity.vin=vin
            from .known_vehicles import get_known_vehicle
            known=get_known_vehicle(vin)
            if known:
                ident=known.get('identity',{})
                out.identity=VehicleIdentity(vin=vin, **ident)
            if vpic_client is not None:
                try:
                    decoded=vpic_client.decode(vin)
                    decoded_identity=_identity_from_vpic(vin, decoded)
                    # vPIC is preferred for identity when it supplies a field; verified cache fills gaps.
                    if known:
                        base=known.get('identity',{})
                        for field_name in VehicleIdentity.__dataclass_fields__:
                            if field_name == 'vin': continue
                            if getattr(decoded_identity,field_name) is None and field_name in base:
                                setattr(decoded_identity,field_name,base[field_name])
                    out.identity=decoded_identity
                    if decoded.get('ErrorCode') not in (None,'','0'):
                        out.warnings.append('VIN decoder returned a warning; review vehicle identity.')
                except Exception:
                    out.warnings.append('VIN lookup unavailable. Continue with label/manual data; VIN lookup can be retried later.')
        else:
            out.warnings.append('VIN is not a valid 17-character VIN. Tow Match can continue without VIN.')
    if inp.payload_label_lb is not None:
        out.facts['payload_lb']=VehicleFact(float(inp.payload_label_lb),DataSource.VEHICLE_LABEL,detail='Tire and Loading placard occupant/cargo capacity')
    elif inp.gm_label_max_payload_lb is not None:
        out.facts['payload_lb']=VehicleFact(float(inp.gm_label_max_payload_lb),DataSource.VEHICLE_LABEL,detail='GM vehicle-specific Trailering Information Label maximum payload')
    else:
        out.missing.append('Vehicle payload label value')

    manual = {
      'tow_rating_lb': inp.conventional_tow_rating_lb,
      'fifth_wheel_tow_rating_lb': inp.fifth_wheel_tow_rating_lb,
      'max_tongue_lb': inp.max_tongue_lb,
      'max_pin_lb': inp.max_pin_lb,
      'camper_carrying_capacity_lb': inp.camper_carrying_capacity_lb,
      'camper_eligible': inp.camper_eligible,
      'bed_size': inp.bed_size,
      'camper_cg_min_in': inp.camper_cg_min_in,
      'camper_cg_max_in': inp.camper_cg_max_in,
      'rear_gawr_remaining_lb': inp.rear_gawr_remaining_lb,
      'tire_capacity_remaining_lb': inp.tire_capacity_remaining_lb,
    }
    for name,val in manual.items():
        if val is not None:
            out.facts[name]=VehicleFact(val,DataSource.MANUAL_RELIABLE,detail='Vehicle-specific reliable value supplied to Tow Match')
    # GM Trailering Information Label can provide vehicle-specific limits directly.
    for name,val in {'gvwr_lb':inp.gm_gvwr_lb,'gcwr_lb':inp.gm_gcwr_lb,'rear_gawr_lb':inp.gm_rear_gawr_lb,'max_tongue_lb':inp.gm_label_max_tongue_lb}.items():
        if val is not None and name not in out.facts:
            out.facts[name]=VehicleFact(float(val),DataSource.VEHICLE_LABEL,detail='GM vehicle-specific Trailering/Certification label')
    if inp.bed_size is None and out.identity.bed_length_in is not None:
        out.facts['bed_size']=VehicleFact(f'{out.identity.bed_length_in:g} in',DataSource.NHTSA_VPIC,confidence='medium',detail='VIN-decoded bed length; manufacturer-specific fit still controls')

    # Manufacturer enrichment is optional and failure-tolerant. It fills missing facts only.
    if manufacturer_provider is not None and out.identity.make:
        try:
            make=(out.identity.make or '').strip().upper()
            if make in {'FORD','FORD MOTOR COMPANY'}:
                from .manufacturers.ford import FordVehicleConfig
                kcfg=(known or {}).get('ford_config',{})
                cfg=FordVehicleConfig(
                    axle_code=inp.axle_code if inp.axle_code is not None else kcfg.get('axle_code'),
                    axle_ratio=inp.axle_ratio if inp.axle_ratio is not None else kcfg.get('axle_ratio'),
                    drive=inp.drive if inp.drive is not None else kcfg.get('drive'),
                    wheelbase_variant=inp.wheelbase_variant if inp.wheelbase_variant is not None else kcfg.get('wheelbase_variant'),
                    heavy_duty_trailer_tow=inp.heavy_duty_trailer_tow if inp.heavy_duty_trailer_tow is not None else kcfg.get('heavy_duty_trailer_tow'),
                    fifth_wheel_gooseneck_prep=inp.fifth_wheel_gooseneck_prep if inp.fifth_wheel_gooseneck_prep is not None else kcfg.get('fifth_wheel_gooseneck_prep'))
                if decoded:
                    from .configuration import ford_config_from_vpic, merge_ford_config
                    cfg=merge_ford_config(cfg, ford_config_from_vpic(out.identity, decoded))
            elif make in {'RAM','DODGE RAM'}:
                from .manufacturers.ram import RamVehicleConfig
                cfg=RamVehicleConfig(engine=inp.gm_engine, drive=inp.drive, cab=inp.gm_cab, bed=inp.gm_bed, axle_ratio=inp.axle_ratio)
            else:
                from .manufacturers.gm import GMVehicleConfig, GMCapabilityProvider
                cfg=GMVehicleConfig(engine=inp.gm_engine, drive=inp.drive, cab=inp.gm_cab, bed=inp.gm_bed,
                    wheel_size_in=inp.gm_wheel_size_in, gvwr_lb=inp.gm_gvwr_lb)
                if make in GMCapabilityProvider.MAKES and decoded:
                    from .configuration import gm_config_from_vpic, merge_gm_config
                    cfg=merge_gm_config(cfg, gm_config_from_vpic(out.identity, decoded))
            resolved=manufacturer_provider.resolve(out.identity,cfg)
            for name,fact in resolved.facts.items():
                if name not in out.facts: out.facts[name]=fact
            out.warnings.extend(resolved.warnings)
            out.missing.extend(x for x in resolved.missing if x not in out.missing)
        except Exception:
            out.warnings.append('Manufacturer capability lookup unavailable. Continue with known vehicle data; unresolved limits remain Verify.')
    return out

def to_engine_vehicle_state(inp: VehicleAcquisitionInput, result: VehicleAcquisitionResult) -> VehicleState:
    f=result.fact_value
    return VehicleState(payload_lb=f('payload_lb'), tow_rating_lb=f('tow_rating_lb'),
        fifth_wheel_tow_rating_lb=f('fifth_wheel_tow_rating_lb'), max_tongue_lb=f('max_tongue_lb'),
        max_pin_lb=f('max_pin_lb'), occupant_weight_lb=inp.occupant_weight_lb,
        pets_weight_lb=inp.pets_weight_lb, truck_cargo_lb=inp.truck_cargo_lb,
        hitch_hardware_lb=inp.hitch_hardware_lb, camper_carrying_capacity_lb=f('camper_carrying_capacity_lb'),
        bed_size=f('bed_size'), camper_eligible=f('camper_eligible'), camper_cg_min_in=f('camper_cg_min_in'),
        camper_cg_max_in=f('camper_cg_max_in'), rear_gawr_remaining_lb=f('rear_gawr_remaining_lb'),
        tire_capacity_remaining_lb=f('tire_capacity_remaining_lb'))
