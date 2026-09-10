"""Pydantic schemas and source contracts for Evidence Fusion.

Phase 6.3 — SIH26100 Evidence Fusion Foundation.
Normalizes evidence items across Bidder Documents and Mock Government Sources:
- BIDDER_DOCUMENT
- GSTN
- UDYAM
- MCA
- INCOME_TAX
- MAKE_IN_INDIA

Guarantees:
1. Strict provenance preservation per source type (page numbers for documents, audit verification IDs for statutory records).
2. Explicit source identity with both source_type and is_mock.
3. Multiple sources for the same field remain independently traceable and never overwrite each other.
4. Statutory sources explicitly labeled: "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION".
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict

MOCK_SOURCE_TYPE_LABEL = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"


class SourceType(str, Enum):
    """Authoritative and document source classifications."""
    BIDDER_DOCUMENT = "BIDDER_DOCUMENT"
    GSTN = "GSTN"
    UDYAM = "UDYAM"
    MCA = "MCA"
    INCOME_TAX = "INCOME_TAX"
    MAKE_IN_INDIA = "MAKE_IN_INDIA"


class EvidenceType(str, Enum):
    """Type of evidence record."""
    DOCUMENT_CLAIM = "DOCUMENT_CLAIM"
    STATUTORY_REGISTRY = "STATUTORY_REGISTRY"


class EvidenceItem(BaseModel):
    """Normalized atomic evidence item with full provenance and source boundary protection."""
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier for this evidence item")
    bidder_id: str = Field(..., description="Bidder identifier or UUID")
    evidence_type: EvidenceType = Field(..., description="Classification: DOCUMENT_CLAIM or STATUTORY_REGISTRY")
    source_type: SourceType = Field(..., description="Source: BIDDER_DOCUMENT, GSTN, UDYAM, MCA, INCOME_TAX, MAKE_IN_INDIA")
    source_name: str = Field(..., description="Human-readable source name, document file name, or registry authority")
    field_name: str = Field(..., description="Canonical field identifier (e.g. turnover, local_content_percent, pan_status)")
    normalized_value: Optional[Union[float, int, str, bool]] = Field(None, description="Standardized scalar or boolean value")
    display_value: str = Field(..., description="Human-readable formatted display value (e.g. '₹8.00 Cr', '55%')")
    unit: Optional[str] = Field(None, description="Standardized unit (e.g. 'CR', '%', 'cores', 'years', 'INR')")
    status: Optional[str] = Field(None, description="Operational or registry status (e.g. 'ACTIVE', 'VERIFIED_CLASS_I')")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")

    # Document-specific provenance (None for statutory sources)
    document_id: Optional[str] = Field(None, description="Database UUID of bid document if from document")
    page_number: Optional[int] = Field(None, description="1-based page number in document (optional; not used for statutory)")

    # Statutory registry-specific provenance (None for document claims)
    source_record_id: Optional[str] = Field(None, description="External verification ID (e.g. MOCK-GSTN-BIDDER-01)")
    raw_reference: Optional[Dict[str, Any]] = Field(None, description="Additional source payload metadata")

    # Verifiable chain of custody / citation
    provenance_reference: str = Field(..., description="Audit citation: document name + page + quote, or verification ID + registry")
    is_mock: bool = Field(..., description="True for synthetic demonstration data, False for submitted documents")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp")


class FieldEvidenceGroup(BaseModel):
    """Grouped evidence items for a specific canonical field under a single bidder."""
    model_config = ConfigDict(from_attributes=True)

    bidder_id: str = Field(..., description="Bidder identifier or UUID")
    field_name: str = Field(..., description="Canonical parameter identifier")
    field_label: str = Field(..., description="Human-friendly label for UI display")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Independent evidence items from various sources")
    source_count: int = Field(0, description="Total number of evidence items collected for this field")
    sources_present: List[SourceType] = Field(default_factory=list, description="List of distinct sources contributing evidence")


class BidderEvidenceFusionProfile(BaseModel):
    """Complete multi-source evidence fusion profile for a bidder."""
    model_config = ConfigDict(from_attributes=True)

    bidder_id: str = Field(..., description="Bidder identifier or UUID")
    company_name: str = Field(..., description="Bidder enterprise display name")
    tender_id: Optional[str] = Field(None, description="Associated tender UUID if applicable")
    entity_identifier: Optional[str] = Field(None, description="Resolved showcase/registry identifier (e.g. BIDDER-01)")
    field_groups: Dict[str, FieldEvidenceGroup] = Field(default_factory=dict, description="Grouped evidence keyed by canonical field_name")
    total_evidence_items: int = Field(0, description="Aggregate count of evidence items")
    sources_present: List[str] = Field(default_factory=list, description="Distinct source codes represented in this profile")
    disclaimer: str = Field(default=MOCK_SOURCE_TYPE_LABEL, description="Mandatory synthetic mock data notice")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="Timestamp of profile generation")
