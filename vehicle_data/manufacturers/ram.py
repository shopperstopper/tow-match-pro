from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from vehicle_data.models import DataSource, VehicleFact, VehicleIdentity

RAM_TOWING_URL = 'https://www.ramtrucks.com/towing.html'
RAM_2026_1500_GUIDE_URL = 'https://www.ramtrucks.com/content/dam/fca-brands/na/ramtrucks/en_us/towing/towing-capacity-guide/brochure/26MY_Ram_1500_PayTow_2.3.pdf'

@dataclass
class RamVehicleConfig:
    engine: Optional[str] = None
    drive: Optional[str] = None
    cab: Optional[str] = None
    bed: Optional[str] = None
    axle_ratio: Optional[float] = None
    gvwr_lb: Optional[float] = None
    gcwr_lb: Optional[float] = None
    rear_wheel_config: Optional[str] = None

@dataclass
class RamCapabilityResolution:
    facts: dict[str, VehicleFact] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

class RamCapabilityProvider:
    """RAM capability provider using exact manufacturer-published configuration rows.

    Advertised model/engine maximums are deliberately not used as vehicle-specific ratings.
    Unknown or uninstalled configurations remain unresolved for Tow Match verification.
    """
    MAKES={'RAM','RAM TRUCKS','FCA US LLC','CHRYSLER'}

    @staticmethod
    def _fact(value, detail):
        return VehicleFact(float(value), DataSource.MANUFACTURER, detail=detail)

    @staticmethod
    def _norm_engine(v: Optional[str]) -> str:
        s=(v or '').upper()
        if '3.0' in s and ('H/O' in s or 'HIGH OUTPUT' in s or 'HIGH-OUTPUT' in s or 'HO ' in s): return '3.0 HURRICANE HO'
        if '3.0' in s and ('HURRICANE' in s or 'TWIN TURBO' in s): return '3.0 HURRICANE SO'
        if '3.6' in s and ('PENTASTAR' in s or 'V6' in s): return '3.6 PENTASTAR'
        if '5.7' in s and ('HEMI' in s or 'V8' in s): return '5.7 HEMI'
        if '6.4' in s and ('HEMI' in s or 'V8' in s): return '6.4 HEMI'
        if '6.7' in s and ('CUMMINS' in s or 'DIESEL' in s): return '6.7 CUMMINS HO'
        return ' '.join(s.split())

    @staticmethod
    def _norm_drive(v: Optional[str]) -> str:
        s=(v or '').upper().replace(' ','')
        if any(x in s for x in ('4X4','4WD','AWD')): return '4x4'
        if any(x in s for x in ('4X2','2WD','RWD')): return '4x2'
        return ''

    @staticmethod
    def _norm_cab(v: Optional[str]) -> str:
        s=(v or '').upper()
        if 'QUAD' in s or 'EXTENDED' in s: return 'QUAD'
        if 'MEGA' in s: return 'MEGA'
        if 'CREW' in s: return 'CREW'
        if 'REGULAR' in s or 'REG CAB' in s: return 'REGULAR'
        return ''

    @staticmethod
    def _norm_bed(v: Optional[str]) -> str:
        s=(v or '').upper().replace(' ','')
        if any(x in s for x in ('6\'4','6FT4','76.3','76IN','STANDARD','LONG')): return '6-4'
        if any(x in s for x in ('5\'7','5FT7','67.4','67IN','SHORT')): return '5-7'
        if any(x in s for x in ('8\'','8FT','96IN','98IN')): return '8-0'
        return ''

    def resolve(self, identity: VehicleIdentity, config: RamVehicleConfig) -> RamCapabilityResolution:
        out=RamCapabilityResolution()
        if (identity.make or '').strip().upper() not in self.MAKES:
            return out
        year=identity.year
        model=(identity.model or '').upper().replace(' ','')
        if year != 2026:
            out.missing.append('RAM vehicle-specific tow rating not yet resolved by installed RAM guide adapter')
            return out
        if '1500' in model:
            return self._resolve_2026_1500(identity,config)
        if '2500' in model or '3500' in model:
            # RAM publishes useful model/engine maxima online, but Tow Match does not substitute
            # those for the exact cab/bed/axle/drive configuration rating.
            out.missing.append('Exact 2026 RAM Heavy Duty configuration table is not yet installed; advertised maximum towing is not used as a vehicle-specific rating')
            return out
        out.missing.append('RAM vehicle-specific tow rating not yet resolved by installed RAM guide adapter')
        return out

    def _resolve_2026_1500(self, identity, config):
        out=RamCapabilityResolution()
        e=self._norm_engine(config.engine or identity.engine)
        d=self._norm_drive(config.drive or identity.drive_type)
        c=self._norm_cab(config.cab)
        b=self._norm_bed(config.bed)
        ratio=round(float(config.axle_ratio),2) if config.axle_ratio is not None else None
        if not all((e,d,c,b)) or ratio is None:
            out.missing.append('2026 RAM 1500 engine, drive, cab, bed and axle ratio are needed for an exact RAM guide row')
            return out

        # Exact Tradesman rows from RAM's 2026 1500 Payload & Towing Weight Capacities guide.
        # Each rating is configuration-specific. NA combinations are intentionally absent.
        rows={
            ('3.6 PENTASTAR',3.21,'QUAD','6-4','4x4'):6470,
            ('3.6 PENTASTAR',3.21,'CREW','5-7','4x2'):6570,
            ('3.6 PENTASTAR',3.21,'CREW','5-7','4x4'):6340,
            ('3.6 PENTASTAR',3.55,'QUAD','6-4','4x2'):7660,
            ('3.6 PENTASTAR',3.55,'QUAD','6-4','4x4'):7470,
            ('3.6 PENTASTAR',3.55,'CREW','5-7','4x2'):7570,
            ('3.6 PENTASTAR',3.55,'CREW','5-7','4x4'):7340,
            ('3.6 PENTASTAR',3.55,'CREW','6-4','4x2'):8130,
            ('3.0 HURRICANE SO',3.21,'QUAD','6-4','4x2'):8510,
            ('3.0 HURRICANE SO',3.21,'CREW','5-7','4x2'):8390,
            ('3.0 HURRICANE SO',3.21,'CREW','6-4','4x2'):8320,
            ('3.0 HURRICANE SO',3.55,'QUAD','6-4','4x4'):8270,
            ('3.0 HURRICANE SO',3.55,'CREW','5-7','4x4'):8100,
            ('3.0 HURRICANE SO',3.55,'CREW','6-4','4x4'):8120,
            ('3.0 HURRICANE SO',3.92,'QUAD','6-4','4x2'):11610,
            ('3.0 HURRICANE SO',3.92,'QUAD','6-4','4x4'):11370,
            ('3.0 HURRICANE SO',3.92,'CREW','5-7','4x2'):11490,
            ('3.0 HURRICANE SO',3.92,'CREW','5-7','4x4'):11200,
            ('3.0 HURRICANE SO',3.92,'CREW','6-4','4x2'):11420,
            ('3.0 HURRICANE SO',3.92,'CREW','6-4','4x4'):11220,
            ('5.7 HEMI',3.21,'CREW','5-7','4x2'):8220,
            ('5.7 HEMI',3.55,'CREW','5-7','4x4'):7640,
            ('5.7 HEMI',3.92,'CREW','5-7','4x2'):11320,
            ('5.7 HEMI',3.92,'CREW','5-7','4x4'):9590,
        }
        rating=rows.get((e,ratio,c,b,d))
        if rating is None:
            out.missing.append('Exact 2026 RAM 1500 configuration is not yet installed in the verified RAM guide table')
            return out
        detail=f'RAM 2026 1500 Payload & Towing guide; {e}; axle {ratio:.2f}; {c} cab; {b} bed; {d}; conventional'
        out.facts['tow_rating_lb']=self._fact(rating,detail)
        # RAM states Class IV receiver maximum tongue weight is 1,100 lb for the chart.
        out.facts['max_tongue_lb']=self._fact(1100,'RAM 2026 1500 guide; Class IV receiver maximum tongue weight')
        out.facts['axle_ratio']=self._fact(ratio,'RAM 2026 1500 configuration')
        return out
