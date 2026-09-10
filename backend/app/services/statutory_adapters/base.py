"""
app.services.statutory_adapters.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Base contract and abstract interface for all statutory verification source adapters.
Ensures uniform return types, strict separation between transport connection status
and domain verification status, payload sanitization, and temporal support.
"""

from abc import ABC, abstractmethod
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional
import time

from app.schemas.statutory_verification import (
    StatutoryAuthority,
    SourceMode,
    SourceConnectionStatus,
    SourceVerificationStatus,
    SourceVerificationResult,
    STATUTORY_MOCK_BANNER,
)

# Sensitive keys to redact in sanitized data payloads
SENSITIVE_KEY_PATTERNS = {
    "secret", "token", "password", "api_key", "apikey",
    "auth", "bearer", "credential", "private_key"
}


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively sanitizes factual payload by redacting any keys matching sensitive patterns.
    Ensures safe persistence and exposure of statutory response data.
    """
    if not isinstance(payload, dict):
        return payload

    sanitized: Dict[str, Any] = {}
    for key, value in payload.items():
        lower_key = str(key).lower()
        if any(pat in lower_key for pat in SENSITIVE_KEY_PATTERNS):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_payload(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class BaseSourceAdapter(ABC):
    """
    Abstract contract for statutory verification sources (e.g. GSTN, Udyam, MCA, Income Tax, MII).
    All concrete adapters must inherit from this and implement the verification workflow.
    """

    @property
    @abstractmethod
    def authority(self) -> StatutoryAuthority:
        """Returns the statutory authority handled by this adapter."""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Returns human-readable canonical authority name."""
        pass

    @abstractmethod
    def get_supported_identifier_types(self) -> List[str]:
        """Returns list of query identifier types supported (e.g. ['gstin', 'entity_identifier'])."""
        pass

    @abstractmethod
    async def verify(
        self,
        query_identifier: str,
        identifier_type: str = "auto",
        as_of_date: Optional[date] = None,
        mode: SourceMode = SourceMode.MOCK,
        db: Any = None,
        **kwargs: Any,
    ) -> SourceVerificationResult:
        """
        Executes verification query against the statutory source register.
        Must handle errors safely and return a normalized SourceVerificationResult.
        Transport failures must set connection_status != SUCCESS.
        Entity not found must set connection_status=SUCCESS and verification_status=NOT_FOUND.
        """
        pass
