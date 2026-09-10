"""
app.services.statutory_adapters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Package exporting base adapter, concrete adapters, and adapter registry.
"""

from app.services.statutory_adapters.base import BaseSourceAdapter, sanitize_payload
from app.services.statutory_adapters.gstn_adapter import GSTNSourceAdapter
from app.services.statutory_adapters.udyam_adapter import UdyamSourceAdapter
from app.services.statutory_adapters.mca_adapter import MCASourceAdapter
from app.services.statutory_adapters.income_tax_adapter import IncomeTaxSourceAdapter
from app.services.statutory_adapters.mii_adapter import MIISourceAdapter
from app.services.statutory_adapters.registry import (
    StatutoryAdapterRegistry,
    get_statutory_registry,
)

__all__ = [
    "BaseSourceAdapter",
    "sanitize_payload",
    "GSTNSourceAdapter",
    "UdyamSourceAdapter",
    "MCASourceAdapter",
    "IncomeTaxSourceAdapter",
    "MIISourceAdapter",
    "StatutoryAdapterRegistry",
    "get_statutory_registry",
]
