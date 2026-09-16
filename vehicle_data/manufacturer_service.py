from __future__ import annotations
from typing import Optional, Any
from .models import VehicleIdentity
from .manufacturers.ford import FordCapabilityProvider, FordVehicleConfig, FordCapabilityResolution
from .manufacturers.gm import GMCapabilityProvider, GMVehicleConfig, GMCapabilityResolution
from .manufacturers.ram import RamCapabilityProvider, RamVehicleConfig, RamCapabilityResolution

class ManufacturerCapabilityService:
    """Manufacturer-neutral dispatcher for vehicle capability adapters."""
    def __init__(self, ford: Optional[FordCapabilityProvider]=None, gm: Optional[GMCapabilityProvider]=None, ram: Optional[RamCapabilityProvider]=None):
        self.ford=ford or FordCapabilityProvider()
        self.gm=gm or GMCapabilityProvider()
        self.ram=ram or RamCapabilityProvider()

    def resolve(self, identity: VehicleIdentity, config: Any):
        make=(identity.make or '').strip().upper()
        if make in {'FORD','FORD MOTOR COMPANY'}:
            return self.ford.resolve(identity, config if isinstance(config,FordVehicleConfig) else FordVehicleConfig())
        if make in GMCapabilityProvider.MAKES:
            return self.gm.resolve(identity, config if isinstance(config,GMVehicleConfig) else GMVehicleConfig())
        if make in RamCapabilityProvider.MAKES:
            return self.ram.resolve(identity, config if isinstance(config,RamVehicleConfig) else RamVehicleConfig())
        return FordCapabilityResolution()
