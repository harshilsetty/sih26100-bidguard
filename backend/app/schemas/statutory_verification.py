"""
app.schemas.statutory_verification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pydantic contracts and schemas for Phase 8.1 Unified Statutory Verification Orchestrator.
Defines clean separation between connection status and verification status,
temporal fields, query parameters, and multi-source verification results.
"""

from datetime import datetime, date, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

STATUTORY_MOCK_BANNER = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"


class StatutoryAuthority(str, Enum):
    """Statutory authorities currently supported in Phase 8.1."""
    GSTN = "GSTN"
    UDYAM = "UDYAM"
    MCA = "MCA"
    INCOME_TAX = "INCOME_TAX"
    MII = "MII"


class SourceMode(str, Enum):
    """Operational mode of the statutory source adapter."""
    MOCK = "MOCK"
    LIVE = "LIVE"


class SourceConnectionStatus(str, Enum):
    """
    Network/transport-level connection status.
    Independent of whether the queried entity exists or complies.
    """
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_FAILURE = "AUTH_FAILURE"
    ERROR = "ERROR"


class SourceVerificationStatus(str, Enum):
    """
    Domain/entity-level verification outcome reported by the statutory authority.
    Note: Connection SUCCESS + entity NOT_FOUND is completely valid.
    """
    VERIFIED = "VERIFIED"
    NOT_FOUND = "NOT_FOUND"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"
    UNVERIFIED = "UNVERIFIED"
    DISCREPANCY = "DISCREPANCY"
    FAILED = "FAILED"


class SourceVerificationResult(BaseModel):
    """
    Standardized payload returned by any statutory source adapter.
    """
    verification_id: str = Field(..., description="Unique UUID for this verification execution")
    authority: StatutoryAuthority = Field(..., description="Statutory authority name")
    source_name: str = Field(..., description="Human-readable name of statutory source")
    query_identifier: str = Field(..., description="Statutory identifier queried (e.g. GSTIN, PAN, CIN)")
    identifier_type: str = Field(..., description="Type of query identifier: gstin, pan, cin, udyam_number, etc.")
    mode: SourceMode = Field(default=SourceMode.MOCK, description="MOCK or LIVE mode indicator")
    connection_status: SourceConnectionStatus = Field(..., description="Transport connection outcome")
    verification_status: SourceVerificationStatus = Field(..., description="Domain verification outcome")
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware timestamp when data was fetched"
    )
    as_of_date: Optional[date] = Field(
        default=None,
        description="Optional historical snapshot date requested for evaluation"
    )
    data_payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized source-native factual attributes"
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Source confidence score (1.0 for authoritative statutory register)"
    )
    provenance_note: str = Field(
        default=STATUTORY_MOCK_BANNER,
        description="Audit provenance disclaimer"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error or timeout detail if connection_status != SUCCESS or verification_status == FAILED"
    )
    execution_time_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Roundtrip query execution latency in milliseconds"
    )


class StatutoryVerificationQuery(BaseModel):
    """
    Query contract for triggering single or multi-source statutory verification.
    """
    bidder_id: Optional[str] = Field(
        default=None,
        description="Internal bidder ID (UUID) if running in context of a tender bidder"
    )
    tender_id: Optional[str] = Field(
        default=None,
        description="Internal tender ID (UUID) if running in context of a tender"
    )
    authorities: Optional[List[StatutoryAuthority]] = Field(
        default=None,
        description="List of authorities to query. If None, queries all available adapters"
    )
    identifiers: Dict[str, str] = Field(
        default_factory=dict,
        description="Statutory identifiers dictionary: gstin, pan, cin, udyam_number, etc."
    )
    as_of_date: Optional[date] = Field(
        default=None,
        description="Optional snapshot cutoff date for temporal compliance check"
    )
    mode: SourceMode = Field(
        default=SourceMode.MOCK,
        description="Execution mode (MOCK default for demo/testing)"
    )


class BidderStatutoryVerificationSummary(BaseModel):
    """
    Aggregated summary across all queried statutory authorities for a bidder/query.
    """
    bidder_id: Optional[str] = None
    tender_id: Optional[str] = None
    results: List[SourceVerificationResult] = Field(default_factory=list)
    total_sources: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    as_of_date: Optional[date] = None
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = STATUTORY_MOCK_BANNER
