from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from vehicle_data.models import DataSource, VehicleFact, VehicleIdentity

GM_TRAILERING_GUIDE_URL = 'https://www.chevrolet.com/trucks/trailering-and-towing-guide'
GM_TRAILERING_LABEL_SUPPORT_URL = 'https://www.chevrolet.com/support/vehicle/entertainment/apps/trailering-app'

@dataclass
class GMVehicleConfig:
    engine: Optional[str] = None
    drive: Optional[str] = None
    cab: Optional[str] = None
    bed: Optional[str] = None
    wheel_size_in: Optional[float] = None
    gvwr_lb: Optional[float] = None
    max_trailering_package: Optional[bool] = None

@dataclass
class GMCapabilityResolution:
    facts: dict[str, VehicleFact] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

class GMCapabilityProvider:
    """Chevrolet/GMC truck capability provider using verified GM guide rows.

    The provider deliberately installs only exact rows verified against GM-published
    trailering guides. It never substitutes advertised maximums for a vehicle-specific row.
    Vehicle-specific Trailering Information Label values, when supplied to acquisition,
    take precedence and are not overwritten here.
    """
    MAKES={'CHEVROLET','CHEVY','GMC','GENERAL MOTORS LLC','GENERAL MOTORS'}

    @staticmethod
    def _fact(value, detail):
        return VehicleFact(float(value), DataSource.MANUFACTURER, detail=detail)

    @staticmethod
    def _norm_engine(v: Optional[str]) -> str:
        s=(v or '').upper()
        if '3.0' in s and ('DIESEL' in s or 'DURAMAX' in s): return '3.0 DURAMAX'
        if '6.6' in s and ('DIESEL' in s or 'DURAMAX' in s): return '6.6 DURAMAX'
        if '6.6' in s: return '6.6 GAS'
        if '5.3' in s: return '5.3 V8'
        if '6.2' in s: return '6.2 V8'
        if '2.7' in s or 'TURBOMAX' in s: return 'TURBOMAX'
        return ' '.join(s.split())

    @staticmethod
    def _norm_drive(v: Optional[str]) -> str:
        s=(v or '').upper().replace(' ','')
        if any(x in s for x in ('4X4','4WD','AWD')): return '4x4'
        if any(x in s for x in ('4X2','2WD','RWD')): return '2WD'
        return ''

    @staticmethod
    def _norm_cab(v: Optional[str]) -> str:
        s=(v or '').upper()
        if 'DOUBLE' in s or 'EXTENDED' in s: return 'DOUBLE'
        if 'CREW' in s: return 'CREW'
        if 'REGULAR' in s or s == 'REG': return 'REGULAR'
        return ''

    @staticmethod
    def _norm_bed(v: Optional[str]) -> str:
        s=(v or '').upper()
        if 'LONG' in s: return 'LONG'
        if 'STANDARD' in s or 'STD' in s: return 'STANDARD'
        if 'SHORT' in s: return 'SHORT'
        return ''

    def resolve(self, identity: VehicleIdentity, config: GMVehicleConfig) -> GMCapabilityResolution:
        out=GMCapabilityResolution()
        if (identity.make or '').strip().upper() not in self.MAKES:
            return out
        year=identity.year
        model=(identity.model or '').upper().replace(' ','')
        if year != 2026:
            out.missing.append('GM vehicle-specific tow rating not yet resolved by installed GM guide adapter')
            return out
        if 'SILVERADO1500' in model or 'SIERRA1500' in model:
            return self._resolve_2026_1500(identity,config)
        if any(x in model for x in ('SILVERADO2500','SIERRA2500','SILVERADO3500','SIERRA3500')):
            return self._resolve_2026_hd(identity,config)
        out.missing.append('GM vehicle-specific tow rating not yet resolved by installed GM guide adapter')
        return out

    def _resolve_2026_1500(self, identity, config):
        out=GMCapabilityResolution()
        e=self._norm_engine(config.engine or identity.engine)
        d=self._norm_drive(config.drive or identity.drive_type)
        c=self._norm_cab(config.cab)
        b=self._norm_bed(config.bed)
        if not all((e,d,c,b)):
            out.missing.append('2026 Silverado/Sierra 1500 engine, drive, cab and bed are needed for an exact GM guide row')
            return out
        # Verified exact 2026 Chevrolet guide rows. Tuple: conventional, fifth/gooseneck.
        # Only rows unambiguous in the official table are installed.
        rows={
            ('REGULAR','STANDARD','2WD','TURBOMAX'):(9100,9000),
            ('REGULAR','LONG','2WD','TURBOMAX'):(9500,9500),
            ('REGULAR','LONG','2WD','5.3 V8'):(9900,9800),
            ('REGULAR','STANDARD','4x4','TURBOMAX'):(9000,8800),
            ('REGULAR','LONG','4x4','TURBOMAX'):(9400,9200),
            ('REGULAR','LONG','4x4','5.3 V8'):(9800,9600),
        }
        vals=rows.get((c,b,d,e))
        if vals is None:
            out.missing.append('Exact 2026 Silverado/Sierra 1500 configuration is not yet installed in the verified GM guide table')
            return out
        conv,fw=vals
        detail=f'GM 2026 trailering guide; 1500; {c} cab; {b} bed; {d}; {e}'
        out.facts['tow_rating_lb']=self._fact(conv,detail+'; conventional')
        out.facts['fifth_wheel_tow_rating_lb']=self._fact(fw,detail+'; gooseneck/5th-wheel')
        return out

    def _resolve_2026_hd(self, identity, config):
        out=GMCapabilityResolution()
        model=(identity.model or '').upper()
        series='2500' if '2500' in model else '3500'
        e=self._norm_engine(config.engine or identity.engine)
        d=self._norm_drive(config.drive or identity.drive_type)
        c=self._norm_cab(config.cab)
        b=self._norm_bed(config.bed)
        wheel=round(float(config.wheel_size_in),1) if config.wheel_size_in else None
        gvwr=round(float(config.gvwr_lb)) if config.gvwr_lb else None
        if series!='2500' or not all((e,d,c,b)):
            out.missing.append('Exact 2026 GM HD configuration is not yet installed in the verified GM guide table')
            return out
        # Initial verified 2500HD Double Cab Long Bed rows from Chevrolet 2026 guide.
        # GVWR/wheel size distinguish rows that otherwise share engine/body configuration.
        rows={
          ('DOUBLE','LONG','2WD','6.6 GAS',10000):(14500,17260),
          ('DOUBLE','LONG','2WD','6.6 GAS',10200):(14500,17260),
          ('DOUBLE','LONG','2WD','6.6 GAS',10600):(16000,18400),
          ('DOUBLE','LONG','2WD','6.6 DURAMAX',10900):(14500,18000),
          ('DOUBLE','LONG','2WD','6.6 DURAMAX',11100):(17900,17900),
          ('DOUBLE','LONG','4x4','6.6 GAS',10000):(14500,16390),
          ('DOUBLE','LONG','4x4','6.6 GAS',10500):(14500,16960),
          ('DOUBLE','LONG','4x4','6.6 GAS',10950):(16000,18000),
          ('DOUBLE','LONG','4x4','6.6 DURAMAX',10000):(14500,11760),
          ('DOUBLE','LONG','4x4','6.6 DURAMAX',11200):(14500,17700),
          ('DOUBLE','LONG','4x4','6.6 DURAMAX',11450):(17600,17600),
        }
        if gvwr is None:
            out.missing.append('2026 GM 2500HD GVWR is needed to select the exact verified trailering-guide row')
            return out
        vals=rows.get((c,b,d,e,gvwr))
        if vals is None:
            out.missing.append('Exact 2026 GM 2500HD configuration is not yet installed in the verified GM guide table')
            return out
        conv,fw=vals
        detail=f'GM 2026 trailering guide; 2500HD; {c} cab; {b} bed; {d}; {e}; GVWR {gvwr:,} lb'
        out.facts['tow_rating_lb']=self._fact(conv,detail+'; conventional')
        out.facts['fifth_wheel_tow_rating_lb']=self._fact(fw,detail+'; gooseneck/5th-wheel')
        return out
