from __future__ import annotations
from typing import Optional, Any
from .models import VehicleState, MatchResult, MatchStatus, GateResult


def _get(rv: Any, name: str, default=None):
    return getattr(rv, name, default) if not isinstance(rv, dict) else rv.get(name, default)

def _payload_available(v: VehicleState, hitch_default: float) -> Optional[float]:
    if v.payload_lb is None: return None
    hitch = v.hitch_hardware_lb if v.hitch_hardware_lb is not None else hitch_default
    return v.payload_lb - v.occupant_weight_lb - v.pets_weight_lb - v.truck_cargo_lb - hitch

def _trailer_reserve_label(reserve: Optional[float]) -> Optional[str]:
    if reserve is None: return None
    if reserve < 0: return "Not Match"
    if reserve < 50: return "Minimal — Verify Carefully"
    if reserve < 200: return "Limited — Verify"
    return "Comfortable"

def _camper_reserve_label(reserve: Optional[float]) -> Optional[str]:
    if reserve is None: return None
    if reserve < 0: return "Not Match"
    if reserve < 200: return "Minimal — Verify Carefully"
    if reserve < 500: return "Limited — Verify Loading"
    return "Comfortable"

def _finish(category, gates, *, loaded=None, qload=None, upper=None, avail=None, reserve=None,
            reserve_label=None, assumptions=None, advisories=None, missing=None, calculations=None,
            rv_data_missing=False, force_preliminary=False):
    assumptions = assumptions or []; advisories = advisories or []; missing = list(dict.fromkeys(missing or []))
    failures = [g for g in gates if g.passed is False and g.required]
    unresolved = [g for g in gates if g.passed is None and g.required]
    if failures:
        status = MatchStatus.NOT_MATCH
    elif rv_data_missing:
        status = MatchStatus.UNABLE
    elif force_preliminary or unresolved or missing:
        status = MatchStatus.PRELIMINARY
    else:
        status = MatchStatus.MATCH
    return MatchResult(status, category, loaded, qload, upper, avail, reserve, reserve_label,
                       gates, assumptions, advisories, missing, calculations or {})

def _normal_loaded(uvw: Optional[float], gvwr: Optional[float], bands):
    if uvw is None: return None, None
    allowance = next(a for ceiling, a in bands if uvw < ceiling)
    loaded = uvw + allowance
    if gvwr is not None: loaded = min(loaded, gvwr)
    return loaded, allowance

TT_BANDS = [(4000,500),(6000,750),(8000,1000),(float('inf'),1250)]
FW_BANDS = [(8000,1000),(11000,1250),(14000,1500),(float('inf'),1700)]

def match_travel_trailer(v: VehicleState, rv: Any) -> MatchResult:
    uvw, gvwr, published = _get(rv,'uvw_lb'), _get(rv,'gvwr_lb'), _get(rv,'published_hitch_pin_lb')
    missing=[]; assumptions=[]; advisories=[]; gates=[]; rv_missing=False
    loaded, allowance = _normal_loaded(uvw, gvwr, TT_BANDS)
    if uvw is not None and gvwr is not None and gvwr < uvw:
        loaded=None; allowance=None; missing.append("RV weight data inconsistent: GVWR is below UVW"); rv_missing=True
    if loaded is None:
        missing.append("RV dry/UVW weight"); rv_missing=True
    q = max(published or 0, loaded*.13) if loaded is not None else None
    upper = max(published or 0, loaded*.15) if loaded is not None else None
    if loaded is not None:
        assumptions.append(f"Normal trailer cargo allowance: {allowance:.0f} lb")
        if published is None: assumptions.append("Published hitch weight missing; 13% loaded tongue estimate used")
    avail = _payload_available(v,100)
    if v.payload_lb is None:
        gates.append(GateResult("Payload",None,"Vehicle payload not yet known")); missing.append("Vehicle payload")
    elif q is not None:
        reserve=avail-q
        gates.append(GateResult("Payload", reserve>=0, f"Available payload for tongue {avail:.0f} lb vs qualification tongue {q:.0f} lb", amount_over_lb=max(0,-reserve) or None))
    else: reserve=None
    if v.tow_rating_lb is None:
        gates.append(GateResult("Tow rating",None,"Vehicle-specific conventional tow rating not yet verified")); missing.append("Vehicle-specific conventional tow rating")
    elif loaded is not None:
        gates.append(GateResult("Tow rating", loaded<=v.tow_rating_lb, f"Estimated loaded trailer {loaded:.0f} lb vs tow rating {v.tow_rating_lb:.0f} lb", amount_over_lb=max(0,loaded-v.tow_rating_lb) or None))
    if v.max_tongue_lb is not None and q is not None:
        gates.append(GateResult("Manufacturer max tongue", q<=v.max_tongue_lb, f"Qualification tongue {q:.0f} lb vs manufacturer max {v.max_tongue_lb:.0f} lb", amount_over_lb=max(0,q-v.max_tongue_lb) or None))
    reserve = (avail-q) if avail is not None and q is not None else None
    force = bool(q is not None and upper is not None and avail is not None and q<=avail<upper)
    if force: missing.append("Verify loaded tongue remains within available payload")
    loading_advisory = gvwr is not None and v.tow_rating_lb is not None and loaded is not None and loaded<=v.tow_rating_lb<gvwr
    if loading_advisory:
        advisories.append("Verify loading before delivery; trailer GVWR exceeds vehicle tow rating")
    return _finish("Travel Trailer",gates,loaded=loaded,qload=q,upper=upper,avail=avail,reserve=reserve,
                   reserve_label=_trailer_reserve_label(reserve),assumptions=assumptions,advisories=advisories,missing=missing,
                   calculations={'cargo_allowance_lb':allowance,'gvwr_lb':gvwr,'published_hitch_lb':published},
                   rv_data_missing=rv_missing,force_preliminary=force)

def match_fifth_wheel(v: VehicleState, rv: Any) -> MatchResult:
    uvw, gvwr, published = _get(rv,'uvw_lb'), _get(rv,'gvwr_lb'), _get(rv,'published_hitch_pin_lb')
    missing=[]; assumptions=[]; advisories=[]; gates=[]; rv_missing=False
    loaded, allowance = _normal_loaded(uvw, gvwr, FW_BANDS)
    if uvw is not None and gvwr is not None and gvwr < uvw:
        loaded=None; allowance=None; missing.append("RV weight data inconsistent: GVWR is below UVW"); rv_missing=True
    if loaded is None: missing.append("RV dry/UVW weight"); rv_missing=True
    q = max(published or 0, loaded*.20) if loaded is not None else None
    upper = max(published or 0, loaded*.25) if loaded is not None else None
    if loaded is not None:
        assumptions.append(f"Normal fifth-wheel cargo allowance: {allowance:.0f} lb")
        if published is None: assumptions.append("Published pin weight missing; 20% loaded pin estimate used")
    avail = _payload_available(v,200)
    if v.payload_lb is None:
        gates.append(GateResult("Payload",None,"Vehicle payload not yet known")); missing.append("Vehicle payload")
    elif q is not None:
        gates.append(GateResult("Payload", q<=avail, f"Available payload for pin {avail:.0f} lb vs qualification pin {q:.0f} lb", amount_over_lb=max(0,q-avail) or None))
    if v.fifth_wheel_tow_rating_lb is None:
        gates.append(GateResult("Fifth-wheel tow rating",None,"Vehicle-specific fifth-wheel/gooseneck tow rating not yet verified")); missing.append("Vehicle-specific fifth-wheel/gooseneck tow rating")
    elif loaded is not None:
        gates.append(GateResult("Fifth-wheel tow rating",loaded<=v.fifth_wheel_tow_rating_lb,f"Estimated loaded fifth wheel {loaded:.0f} lb vs rating {v.fifth_wheel_tow_rating_lb:.0f} lb",amount_over_lb=max(0,loaded-v.fifth_wheel_tow_rating_lb) or None))
    if v.max_pin_lb is not None and q is not None:
        gates.append(GateResult("Manufacturer max pin",q<=v.max_pin_lb,f"Qualification pin {q:.0f} lb vs manufacturer max {v.max_pin_lb:.0f} lb",amount_over_lb=max(0,q-v.max_pin_lb) or None))
    reserve=(avail-q) if avail is not None and q is not None else None
    force=bool(q is not None and upper is not None and avail is not None and q<=avail<upper)
    if force: missing.append("Verify loaded pin remains within available payload")
    loading_advisory = gvwr is not None and v.fifth_wheel_tow_rating_lb is not None and loaded is not None and loaded<=v.fifth_wheel_tow_rating_lb<gvwr
    if loading_advisory:
        advisories.append("Verify loading before delivery; fifth-wheel GVWR exceeds vehicle rating")
    return _finish("Fifth Wheel",gates,loaded=loaded,qload=q,upper=upper,avail=avail,reserve=reserve,
                   reserve_label=_trailer_reserve_label(reserve),assumptions=assumptions,advisories=advisories,missing=missing,
                   calculations={'cargo_allowance_lb':allowance,'gvwr_lb':gvwr,'published_pin_lb':published},
                   rv_data_missing=rv_missing,force_preliminary=force)

def _norm_bed(s):
    if not s: return None
    t=str(s).lower()
    if 'ultra' in t or 'super short' in t or '5.5' in t or '5 ft' in t: return 'super_short'
    if 'long' in t or '8' in t: return 'long'
    if 'short' in t or 'standard' in t or '6' in t: return 'standard_short'
    if 'compact' in t: return 'compact'
    return t.strip()

def match_truck_camper(v: VehicleState, rv: Any, personal_cargo_lb: float=500,
                        battery_weight_lb: Optional[float]=None, propane_load_lb: Optional[float]=None) -> MatchResult:
    dry=_get(rv,'uvw_lb'); fresh=_get(rv,'fresh_water_gal'); lp_cap=_get(rv,'lp_tank_capacity_lb'); lp_count=_get(rv,'lp_tank_count')
    camper_bed=_get(rv,'truck_bed_size'); cg=_get(rv,'cg_front_in')
    gates=[]; missing=[]; assumptions=[]; rv_missing=False
    if dry is None:
        missing.append("Camper dry/actual weight"); rv_missing=True
    includes_options = bool(_get(rv,'weight_includes_factory_options',False))
    option_allowance = (0 if includes_options else min(dry*.10,300)) if dry is not None else None
    if option_allowance is not None: assumptions.append(f"Unaccounted factory options estimate: {option_allowance:.0f} lb")
    water = fresh*8.3 if fresh is not None else 250
    assumptions.append("Fresh water assumed full" + (f" ({fresh:g} gal)" if fresh is not None else " (250 lb fallback)"))
    if propane_load_lb is not None: propane=propane_load_lb
    elif lp_cap is not None:
        propane=lp_cap*(lp_count or 1); assumptions.append("Propane assumed full from published capacity")
    else:
        propane=30; assumptions.append("Propane load estimated at 30 lb")
    battery=battery_weight_lb if battery_weight_lb is not None else 65
    if battery_weight_lb is None: assumptions.append("Battery estimated at one 65-lb battery")
    mounting=v.hitch_hardware_lb if v.hitch_hardware_lb is not None else 100
    assumptions.append(f"Camper personal cargo allowance: {personal_cargo_lb:.0f} lb")
    assumptions.append(f"Camper mounting equipment: {mounting:.0f} lb")
    camper_loaded=(dry+option_allowance+water+propane+battery+personal_cargo_lb) if dry is not None else None
    total_vehicle_load=(camper_loaded+v.occupant_weight_lb+v.pets_weight_lb+v.truck_cargo_lb+mounting) if camper_loaded is not None else None
    # payload and CWR are independent gates
    if v.payload_lb is None:
        gates.append(GateResult("Payload",None,"Vehicle payload not yet known")); missing.append("Vehicle payload")
    elif total_vehicle_load is not None:
        gates.append(GateResult("Payload",total_vehicle_load<=v.payload_lb,f"Total truck load {total_vehicle_load:.0f} lb vs payload {v.payload_lb:.0f} lb",amount_over_lb=max(0,total_vehicle_load-v.payload_lb) or None))
    if v.camper_carrying_capacity_lb is not None and total_vehicle_load is not None:
        gates.append(GateResult("Manufacturer camper carrying capacity",total_vehicle_load<=v.camper_carrying_capacity_lb,f"Total truck load {total_vehicle_load:.0f} lb vs camper carrying capacity {v.camper_carrying_capacity_lb:.0f} lb",amount_over_lb=max(0,total_vehicle_load-v.camper_carrying_capacity_lb) or None))
    # Bed fit
    tb, cb=_norm_bed(v.bed_size),_norm_bed(camper_bed)
    if tb and cb:
        gates.append(GateResult("Bed compatibility",tb==cb,f"Truck bed {v.bed_size} vs camper requirement {camper_bed}"))
    elif camper_bed or v.bed_size:
        gates.append(GateResult("Bed compatibility",None,"Truck/camper bed compatibility not fully known")); missing.append("Truck/camper bed compatibility")
    else:
        gates.append(GateResult("Bed compatibility",None,"Truck and camper bed-size information missing")); missing.append("Truck/camper bed-size information")
    # Manufacturer eligibility
    if v.camper_eligible is False: gates.append(GateResult("Manufacturer camper eligibility",False,"Manufacturer identifies this truck as not recommended/not rated for slide-in camper use"))
    elif v.camper_eligible is True: gates.append(GateResult("Manufacturer camper eligibility",True,"Manufacturer camper eligibility confirmed"))
    else: gates.append(GateResult("Manufacturer camper eligibility",None,"Manufacturer camper eligibility not yet verified")); missing.append("Manufacturer camper eligibility")
    # CG only mandatory when applicable limits exist
    if v.camper_cg_min_in is not None or v.camper_cg_max_in is not None:
        if cg is None:
            gates.append(GateResult("Center of gravity",None,"Camper center-of-gravity value missing")); missing.append("Camper center of gravity")
        else:
            lo=v.camper_cg_min_in if v.camper_cg_min_in is not None else float('-inf'); hi=v.camper_cg_max_in if v.camper_cg_max_in is not None else float('inf')
            gates.append(GateResult("Center of gravity",lo<=cg<=hi,f"Camper CG {cg:g} in vs truck allowed range {lo:g} to {hi:g} in"))
    # known secondary hard limits
    if v.rear_gawr_remaining_lb is not None and total_vehicle_load is not None:
        gates.append(GateResult("Rear GAWR",total_vehicle_load<=v.rear_gawr_remaining_lb,f"Calculated load {total_vehicle_load:.0f} lb vs available rear-axle capacity {v.rear_gawr_remaining_lb:.0f} lb",amount_over_lb=max(0,total_vehicle_load-v.rear_gawr_remaining_lb) or None))
    if v.tire_capacity_remaining_lb is not None and total_vehicle_load is not None:
        gates.append(GateResult("Tire capacity",total_vehicle_load<=v.tire_capacity_remaining_lb,f"Calculated load {total_vehicle_load:.0f} lb vs available tire capacity {v.tire_capacity_remaining_lb:.0f} lb",amount_over_lb=max(0,total_vehicle_load-v.tire_capacity_remaining_lb) or None))
    reserve=(v.payload_lb-total_vehicle_load) if v.payload_lb is not None and total_vehicle_load is not None else None
    # Rule 44: marginal + material estimates -> Preliminary
    material_estimates = (fresh is None or lp_cap is None or battery_weight_lb is None or option_allowance not in (None,0))
    force=bool(reserve is not None and 0<=reserve<200 and material_estimates)
    if force: missing.append("Verify estimated camper loading because payload reserve is minimal")
    return _finish("Truck Camper",gates,loaded=camper_loaded,qload=total_vehicle_load,avail=v.payload_lb,reserve=reserve,
                   reserve_label=_camper_reserve_label(reserve),assumptions=assumptions,missing=missing,
                   calculations={'dry_lb':dry,'factory_options_allowance_lb':option_allowance,'fresh_water_load_lb':water,'propane_load_lb':propane,'battery_load_lb':battery,'personal_cargo_lb':personal_cargo_lb,'mounting_equipment_lb':mounting,'total_vehicle_load_lb':total_vehicle_load},
                   rv_data_missing=rv_missing,force_preliminary=force)

def match(v: VehicleState, rv: Any) -> MatchResult:
    category=_get(rv,'rv_category')
    if category == 'Travel Trailer': return match_travel_trailer(v,rv)
    if category == 'Fifth Wheel': return match_fifth_wheel(v,rv)
    if category == 'Truck Camper': return match_truck_camper(v,rv)
    return MatchResult(MatchStatus.UNABLE, category or 'Unknown', missing_information=['RV category'])
