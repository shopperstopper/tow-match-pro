from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from vehicle_data.models import DataSource, VehicleAcquisitionResult, VehicleFact, VehicleIdentity

FORD_TOWING_URL = 'https://www.ford.com/towing/'
FORD_2019_EXPEDITION_GUIDE_URL = 'https://www.ford.com/cmslibs/content/dam/brand_ford/en_us/brand/resources/general/pdf/guides/19Towing_Ford_Expedition_r1_Dec21.pdf'

@dataclass
class FordVehicleConfig:
    """Vehicle-specific Ford facts already known to Tow Match.

    These values may come from a label scan, VIN/manufacturer lookup, dealer data, or
    quick salesperson entry. The provider never asks the salesperson to interpret them.
    """
    axle_code: Optional[str] = None
    axle_ratio: Optional[float] = None
    drive: Optional[str] = None
    wheelbase_variant: Optional[str] = None  # SWB / MAX for Expedition
    heavy_duty_trailer_tow: Optional[bool] = None
    fifth_wheel_gooseneck_prep: Optional[bool] = None
    truck_class: Optional[str] = None
    rear_wheel_config: Optional[str] = None
    engine: Optional[str] = None
    cab: Optional[str] = None  # REGULAR / SUPERCAB / CREW / SUPERCREW
    wheelbase_in: Optional[float] = None
    box_length_ft: Optional[float] = None
    max_tow_axle: Optional[bool] = None
    tremor: Optional[bool] = None
    high_capacity_axle: Optional[bool] = None

@dataclass
class FordCapabilityResolution:
    facts: dict[str, VehicleFact] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


class FordCapabilityProvider:
    """Resolve Ford vehicle-specific towing facts from verified Ford guide rules.

    v1 intentionally uses documented manufacturer guide rules, not an undocumented Ford
    web endpoint. A future official/contracted VIN service can implement the same interface.
    Unknown/ambiguous configurations remain unresolved so the matching engine returns Verify.
    """

    def resolve(self, identity: VehicleIdentity, config: FordVehicleConfig) -> FordCapabilityResolution:
        out = FordCapabilityResolution()
        if (identity.make or '').strip().upper() not in {'FORD', 'FORD MOTOR COMPANY'}:
            return out
        model = (identity.model or '').strip().lower()
        if identity.year == 2019 and model.startswith('expedition'):
            return self._resolve_2019_expedition(identity, config)
        if identity.year == 2026 and ('f-150' in model or 'f150' in model):
            return self._resolve_2026_f150(identity, config)
        if identity.year == 2026 and any(x in model for x in ('f-250','f250','f-350','f350','f-450','f450')):
            return self._resolve_2026_super_duty(identity, config)
        out.missing.append('Ford vehicle-specific tow rating not yet resolved by installed Ford guide adapter')
        return out

    @staticmethod
    def _drive_4x4(identity: VehicleIdentity, config: FordVehicleConfig) -> Optional[bool]:
        raw = (config.drive or identity.drive_type or '').upper().replace(' ', '')
        if any(x in raw for x in ('4X4','4WD','AWD')): return True
        if any(x in raw for x in ('4X2','2WD','RWD')): return False
        return None

    @staticmethod
    def _variant(identity: VehicleIdentity, config: FordVehicleConfig) -> Optional[str]:
        if config.wheelbase_variant:
            v=config.wheelbase_variant.upper()
            if 'MAX' in v or 'LWB' in v: return 'MAX'
            if 'SWB' in v or 'STANDARD' in v: return 'SWB'
        text=' '.join(filter(None,[identity.model,identity.trim,identity.series])).upper()
        return 'MAX' if 'MAX' in text else 'SWB'

    @staticmethod
    def _axle_ratio(config: FordVehicleConfig) -> Optional[float]:
        if config.axle_ratio is not None: return round(float(config.axle_ratio),2)
        # 2019 Expedition Ford guide rear axle ratio codes.
        code=(config.axle_code or '').strip().upper()
        return {'10':3.15,'15':3.31,'3L':3.73}.get(code)


    @staticmethod
    def _norm_engine(value: Optional[str]) -> str:
        s=(value or '').upper().replace('ECOBOOST','GTDI').replace('POWERBOOST','HYBRID')
        s=' '.join(s.split())
        if '3.5' in s and 'HYBRID' in s: return '3.5 HYBRID'
        if '3.5' in s and ('H.O' in s or 'HO ' in s): return '3.5 HO'
        if '3.5' in s: return '3.5 GTDI'
        if '2.7' in s: return '2.7 GTDI'
        if '5.0' in s: return '5.0'
        if '5.2' in s: return '5.2 SC'
        if '6.7' in s and ('H.O' in s or 'HIGH OUTPUT' in s or 'HO ' in s): return '6.7 HO DIESEL'
        if '6.7' in s: return '6.7 DIESEL'
        if '6.8' in s: return '6.8 GAS'
        if '7.3' in s: return '7.3 GAS'
        return s

    @staticmethod
    def _norm_cab(value: Optional[str]) -> str:
        s=(value or '').upper().replace('SUPER CREW','SUPERCREW').replace('CREW CAB','CREW')
        if 'SUPERCREW' in s: return 'SUPERCREW'
        if 'SUPERCAB' in s or 'SUPER CAB' in s: return 'SUPERCAB'
        if 'REGULAR' in s or s == 'REG': return 'REGULAR'
        if 'CREW' in s: return 'CREW'
        return s

    @staticmethod
    def _fact(value: float, detail: str) -> VehicleFact:
        return VehicleFact(float(value), DataSource.MANUFACTURER, detail=detail)

    def _resolve_2026_f150(self, identity: VehicleIdentity, config: FordVehicleConfig) -> FordCapabilityResolution:
        out=FordCapabilityResolution()
        engine=self._norm_engine(config.engine)
        if config.axle_ratio is not None:
            ratio=round(float(config.axle_ratio),2)
        else:
            ratio={'15':3.15,'27':3.31,'L3':3.31,'19':3.55,'L9':3.55,'L6':3.73,'L4':4.10}.get((config.axle_code or '').strip().upper())
        cab=self._norm_cab(config.cab)
        is4=self._drive_4x4(identity,config)
        wb=round(float(config.wheelbase_in),1) if config.wheelbase_in else None
        if not all((engine, ratio, cab)) or is4 is None or wb is None:
            out.missing.append('2026 F-150 engine, axle ratio, cab, drive and wheelbase are needed for an exact Ford guide row')
            return out
        drive='4x4' if is4 else '4x2'
        # Exact, unambiguous rows transcribed from Ford 2026 F-150 guide v4.
        # The table intentionally grows only with verified exact rows; no interpolation/max-rating guesses.
        rows={
          ('5.0',3.15,'REGULAR','4x2',122.8):(9600,9500),
          ('5.0',3.15,'REGULAR','4x2',141.5):(9500,9400),
          ('3.5 GTDI',3.31,'REGULAR','4x2',141.5):(10900,10800),
          ('3.5 HO',4.10,'SUPERCREW','4x4',145.4):(8200,None),
          ('5.2 SC',4.10,'SUPERCREW','4x4',145.4):(8700,None),
        }
        key=(engine,round(ratio,2),cab,drive,wb)
        vals=rows.get(key)
        if vals is None:
            out.missing.append('Exact 2026 F-150 configuration is not yet installed in the verified Ford guide table')
            return out
        conventional,fifth=vals
        detail=f'Ford 2026 F-150 guide v4; {engine}; {ratio:.2f}; {cab}; {drive}; {wb:.1f} in wheelbase'
        out.facts['tow_rating_lb']=self._fact(conventional,detail+'; conventional')
        if fifth is not None:
            out.facts['fifth_wheel_tow_rating_lb']=self._fact(fifth,detail+'; fifth-wheel/gooseneck')
        if 'RAPTOR' in ((identity.trim or '')+' '+(identity.series or '')).upper():
            out.warnings.append('Ford does not recommend fifth-wheel towing for F-150 Raptor')
            out.facts.pop('fifth_wheel_tow_rating_lb',None)
        out.facts['axle_ratio']=self._fact(ratio,'Ford 2026 F-150 axle configuration')
        return out

    def _resolve_2026_super_duty(self, identity: VehicleIdentity, config: FordVehicleConfig) -> FordCapabilityResolution:
        out=FordCapabilityResolution()
        model=(identity.model or '').upper().replace(' ','')
        engine=self._norm_engine(config.engine)
        if config.axle_ratio is not None:
            ratio=round(float(config.axle_ratio),2)
        else:
            ratio={'31':3.31,'3H':3.31,'35':3.55,'3K':3.55,'3J':3.55,'37':3.73,'3L':3.73,'3E':3.73,'4N':4.10,'4L':4.30,'4M':4.30}.get((config.axle_code or '').strip().upper())
        cab=self._norm_cab(config.cab)
        is4=self._drive_4x4(identity,config)
        wb=round(float(config.wheelbase_in),1) if config.wheelbase_in else None
        if not all((engine, ratio, cab)) or is4 is None or wb is None:
            out.missing.append('2026 Super Duty engine, axle ratio, cab, drive and wheelbase are needed for an exact Ford guide row')
            return out
        drive='4x4' if is4 else '4x2'
        # Verified exact conventional rows. More rows are added from Ford tables without inference.
        rows={
          ('F-250','6.7 DIESEL',3.31,'REGULAR','4x2',141.6):16600,
          ('F-250','6.7 DIESEL',3.31,'REGULAR','4x4',141.6):16200,
          ('F-250','6.8 GAS',3.73,'REGULAR','4x2',141.6):14800,
          ('F-250','6.8 GAS',4.30,'REGULAR','4x2',141.6):17300,
          ('F-250','7.3 GAS',4.30,'REGULAR','4x2',141.6):18200,
          ('F-350','6.7 DIESEL',3.31,'REGULAR','4x2',141.6):20000,
          ('F-350','6.8 GAS',3.73,'REGULAR','4x2',141.6):14700,
        }
        m='F-250' if 'F-250' in model or 'F250' in model else ('F-350' if 'F-350' in model or 'F350' in model else 'F-450')
        key=(m,engine,round(ratio,2),cab,drive,wb)
        rating=rows.get(key)
        if rating is None:
            out.missing.append('Exact 2026 Super Duty configuration is not yet installed in the verified Ford guide table')
            return out
        detail=f'Ford 2026 Super Duty guide v3; {m}; {engine}; {ratio:.2f}; {cab}; {drive}; {wb:.1f} in wheelbase'
        out.facts['tow_rating_lb']=self._fact(rating,detail+'; conventional')
        out.facts['axle_ratio']=self._fact(ratio,'Ford 2026 Super Duty axle configuration')
        # Receiver maximum tongue load is a separate applicable gate, not a substitute for vehicle tow rating.
        tongue={'F-250':2200,'F-350':2500,'F-450':3000}.get(m)
        if tongue:
            out.facts['max_tongue_lb']=self._fact(tongue,'Ford 2026 Super Duty factory hitch receiver capacity; configuration-specific tow rating may be lower')
        return out

    def _resolve_2019_expedition(self, identity: VehicleIdentity, config: FordVehicleConfig) -> FordCapabilityResolution:
        out=FordCapabilityResolution()
        ratio=self._axle_ratio(config)
        is_4x4=self._drive_4x4(identity,config)
        variant=self._variant(identity,config)
        detail=f'2019 Ford Expedition towing guide; axle ratio {ratio if ratio else "unknown"}; {variant or "variant unknown"}'

        if ratio is None:
            out.missing.append('Ford rear axle ratio/code needed to resolve 2019 Expedition tow rating')
            return out
        if is_4x4 is None:
            out.missing.append('Ford drive configuration needed to resolve 2019 Expedition tow rating')
            return out

        rating=None
        requires_hd=False
        # Official 2019 selector. Multiple GCWR rows with the same configuration collapse
        # to the same max trailer rating where the guide permits that safely.
        if ratio in (3.15,3.31):
            if variant == 'SWB': rating=6000
            elif variant == 'MAX': rating=6300 if not is_4x4 else 6000
        elif ratio == 3.73:
            if config.heavy_duty_trailer_tow is True:
                requires_hd=True
                if variant == 'SWB': rating=9200 if is_4x4 else 9300
                elif variant == 'MAX': rating=9000
            elif config.heavy_duty_trailer_tow is False:
                # Without package 536, Ford's 2019 guide does not grant the 9k+ ratings.
                rating=6000 if variant == 'SWB' else (6000 if is_4x4 else 6300)
            else:
                out.missing.append('Heavy-Duty Trailer Tow Package status needed to resolve 2019 Expedition 3.73 rating')
                return out

        if rating is None:
            out.missing.append('2019 Expedition configuration does not map unambiguously to an installed Ford guide row')
            return out

        out.facts['tow_rating_lb']=VehicleFact(float(rating),DataSource.MANUFACTURER,
            detail=detail + ('; requires Heavy-Duty Trailer Tow Package 536' if requires_hd else ''))
        out.facts['axle_ratio']=VehicleFact(float(ratio),DataSource.MANUFACTURER,
            detail=f'Ford 2019 Expedition axle code mapping ({config.axle_code})' if config.axle_code else 'Reliable Ford configuration input')

        # Do not infer a universal max tongue from the trailer selector. Ford publishes
        # hitch receiver capacities separately, and vehicle/package/hitch setup matters.
        return out


def apply_ford_capabilities(result: VehicleAcquisitionResult, config: FordVehicleConfig, provider: Optional[FordCapabilityProvider]=None) -> VehicleAcquisitionResult:
    provider=provider or FordCapabilityProvider()
    resolved=provider.resolve(result.identity,config)
    # Better information replaces defaults. Existing Actual/Label/Manual Reliable values win;
    # manufacturer enrichment fills missing capability facts rather than overwriting them.
    for name,fact in resolved.facts.items():
        if name not in result.facts:
            result.facts[name]=fact
    result.warnings.extend(x for x in resolved.warnings if x not in result.warnings)
    result.missing.extend(x for x in resolved.missing if x not in result.missing)
    return result
