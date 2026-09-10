"""
app.services.statutory_adapters.registry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Centralized registry for statutory verification source adapters.
Provides runtime discovery, registration, and retrieval of adapters by StatutoryAuthority.
"""

import logging
from typing import Dict, List, Optional, Type

from app.schemas.statutory_verification import StatutoryAuthority
from app.services.statutory_adapters.base import BaseSourceAdapter
from app.services.statutory_adapters.gstn_adapter import GSTNSourceAdapter
from app.services.statutory_adapters.udyam_adapter import UdyamSourceAdapter
from app.services.statutory_adapters.mca_adapter import MCASourceAdapter
from app.services.statutory_adapters.income_tax_adapter import IncomeTaxSourceAdapter
from app.services.statutory_adapters.mii_adapter import MIISourceAdapter
from app.services.statutory_adapters.debarment_adapter import DebarmentSourceAdapter

logger = logging.getLogger(__name__)


class StatutoryAdapterRegistry:
    """Registry maintaining instances of statutory verification adapters."""

    def __init__(self) -> None:
        self._adapters: Dict[StatutoryAuthority, BaseSourceAdapter] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the canonical statutory adapters."""
        self.register(GSTNSourceAdapter())
        self.register(UdyamSourceAdapter())
        self.register(MCASourceAdapter())
        self.register(IncomeTaxSourceAdapter())
        self.register(MIISourceAdapter())
        self.register(DebarmentSourceAdapter())

    def register(self, adapter: BaseSourceAdapter) -> None:
        """Register an adapter instance for its declared statutory authority."""
        self._adapters[adapter.authority] = adapter
        logger.debug(f"Registered statutory adapter for {adapter.authority.value}: {adapter.__class__.__name__}")

    def get_adapter(self, authority: StatutoryAuthority) -> Optional[BaseSourceAdapter]:
        """Retrieve the adapter registered for given authority."""
        return self._adapters.get(authority)

    def list_supported_authorities(self) -> List[StatutoryAuthority]:
        """Return list of authorities currently registered."""
        return list(self._adapters.keys())

    def get_all_adapters(self) -> Dict[StatutoryAuthority, BaseSourceAdapter]:
        """Return shallow copy of all registered adapters."""
        return dict(self._adapters)


# Global singleton registry instance
_default_registry = StatutoryAdapterRegistry()


def get_statutory_registry() -> StatutoryAdapterRegistry:
    """Dependency / accessor for global statutory adapter registry."""
    return _default_registry
