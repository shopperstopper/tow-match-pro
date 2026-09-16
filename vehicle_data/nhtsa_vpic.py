from __future__ import annotations
import requests
from typing import Optional

class NHTSAVpicClient:
    """Single-VIN identity decoder. Not a tow-rating service.

    NHTSA states vPIC data is manufacturer-reported. Tow Match uses it for identity/configuration
    clues only; payload/tow ratings still require label/manufacturer-specific reliable data.
    """
    BASE = 'https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValuesExtended/{vin}?format=json'

    def __init__(self, session: Optional[requests.Session] = None, timeout: int = 10):
        self.session = session or requests.Session()
        self.timeout = timeout

    def decode(self, vin: str) -> dict:
        r = self.session.get(self.BASE.format(vin=vin), timeout=self.timeout,
                             headers={'User-Agent':'TowMatchPro/1.0 single-VIN-decode'})
        r.raise_for_status()
        data = r.json()
        rows = data.get('Results') or []
        return rows[0] if rows else {}
