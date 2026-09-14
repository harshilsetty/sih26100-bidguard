"""
app.services.statutory_adapters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Package exporting base adapter, concrete adapters, and adapter registry.
"""

from app.services.statutory_adapters.base import (
    BaseSourceAdapter,
    sanitize_payload,
    validate_bidder_identity_consistency,
)
from app.services.statutory_adapters.gstn_adapter import GSTNSourceAdapter
from app.services.statutory_adapters.udyam_adapter import UdyamSourceAdapter
from app.services.statutory_adapters.mca_adapter import MCASourceAdapter
from app.services.statutory_adapters.income_tax_adapter import IncomeTaxSourceAdapter
from app.services.statutory_adapters.mii_adapter import MIISourceAdapter
from app.services.statutory_adapters.debarment_adapter import DebarmentSourceAdapter
from app.services.statutory_adapters.dpiit_adapter import DPIITSourceAdapter
from app.services.statutory_adapters.epfo_adapter import EPFOSourceAdapter
from app.services.statutory_adapters.esic_adapter import ESICSourceAdapter
from app.services.statutory_adapters.registry import (
    StatutoryAdapterRegistry,
    get_statutory_registry,
)

__all__ = [
    "BaseSourceAdapter",
    "sanitize_payload",
    "validate_bidder_identity_consistency",
    "GSTNSourceAdapter",
    "UdyamSourceAdapter",
    "MCASourceAdapter",
    "IncomeTaxSourceAdapter",
    "MIISourceAdapter",
    "DebarmentSourceAdapter",
    "DPIITSourceAdapter",
    "EPFOSourceAdapter",
    "ESICSourceAdapter",
    "StatutoryAdapterRegistry",
    "get_statutory_registry",
]
