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


def validate_bidder_identity_consistency(
    record_pan: Optional[str] = None,
    record_cin: Optional[str] = None,
    query_pan: Optional[str] = None,
    query_cin: Optional[str] = None,
    query_gstin: Optional[str] = None,
    query_udyam: Optional[str] = None,
    record_udyam: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """
    Validates that a located statutory record does not conflict with authoritative bidder identity.
    Hierarchy: PAN > CIN > GSTIN > Udyam > entity_identifier.

    Returns:
        (is_consistent, conflict_reason)
        If an identity conflict is detected with authoritative evidence, returns (False, reason).
        If consistent or no conflicting authoritative evidence exists, returns (True, None).
    """
    norm_rec_pan = record_pan.strip().upper() if record_pan and str(record_pan).strip() else None
    norm_rec_cin = record_cin.strip().upper() if record_cin and str(record_cin).strip() else None
    norm_rec_udyam = record_udyam.strip().upper() if record_udyam and str(record_udyam).strip() else None

    # Expected PAN from query or derived from 15-char GSTIN (chars 2:12)
    expected_pan = query_pan.strip().upper() if query_pan and str(query_pan).strip() else None
    if not expected_pan and query_gstin and str(query_gstin).strip():
        gstin_str = str(query_gstin).strip().upper()
        if len(gstin_str) == 15:
            expected_pan = gstin_str[2:12]

    # Check PAN conflict
    if expected_pan and norm_rec_pan:
        if expected_pan != norm_rec_pan:
            return (
                False,
                f"Authoritative PAN conflict: query PAN '{expected_pan}' does not match registry record PAN '{norm_rec_pan}'",
            )

    # Check CIN conflict
    expected_cin = query_cin.strip().upper() if query_cin and str(query_cin).strip() else None
    if expected_cin and norm_rec_cin:
        if expected_cin != norm_rec_cin:
            return (
                False,
                f"Authoritative CIN conflict: query CIN '{expected_cin}' does not match registry record CIN '{norm_rec_cin}'",
            )

    # Check Udyam conflict
    expected_udyam = query_udyam.strip().upper() if query_udyam and str(query_udyam).strip() else None
    if expected_udyam and norm_rec_udyam:
        if expected_udyam != norm_rec_udyam:
            return (
                False,
                f"Authoritative Udyam conflict: query Udyam '{expected_udyam}' does not match registry record Udyam '{norm_rec_udyam}'",
            )

    return (True, None)


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
