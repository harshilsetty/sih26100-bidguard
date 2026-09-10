"""Pydantic schemas for Cross-Source Verification.

Phase 6.3 Step 2 — SIH26100 Cross-Source Verification Layer.
Compares evidence items within a BidderEvidenceFusionProfile across Bidder Documents
and Mock Government Sources (GSTN, UDYAM, MCA, INCOME_TAX, MAKE_IN_INDIA).

Core Rules & Guardrails:
1. Field-level aggregated result: One verification result per canonical field.
2. Preserves every evidence ID and provenance reference across all compared items.
3. Multi-evidence field comparison: Discrepancy details explain agreeing vs differing subgroups.
4. Udyam / MSE semantics: Verifies classification consistency only; does NOT infer EMD exemption eligibility.
5. Exact normalized numeric comparison: No arbitrary tolerance (e.g. no 0.01 tolerance).
6. Purely deterministic: No LLM/NIM calls, no source authority ranking, no winner/loser determination.
7. Mock disclosure: Explicitly flags mock government sources.
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict

MOCK_SOURCE_DISCLAIMER = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"


class CrossSourceStatus(str, Enum):
    """Deterministic comparison outcomes."""
    CONSISTENT = "CONSISTENT"
    INCONSISTENT = "INCONSISTENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class DiscrepancyDetail(BaseModel):
    """Detailed relationship between compared evidence items within a field."""
    model_config = ConfigDict(from_attributes=True)

    source_a: str = Field(..., description="Source code or name of first evidence item")
    evidence_id_a: str = Field(..., description="Unique ID of first evidence item")
    value_a: Optional[Union[float, int, str, bool]] = Field(None, description="Normalized value of first item")
    display_value_a: str = Field(..., description="Display string of first item")

    source_b: str = Field(..., description="Source code or name of second evidence item")
    evidence_id_b: str = Field(..., description="Unique ID of second evidence item")
    value_b: Optional[Union[float, int, str, bool]] = Field(None, description="Normalized value of second item")
    display_value_b: str = Field(..., description="Display string of second item")

    agrees: bool = Field(..., description="Whether these two specific evidence items agree")
    notes: str = Field(..., description="Human-readable description of comparison relationship")


class CrossSourceVerificationResult(BaseModel):
    """Deterministic, aggregated field-level cross-source comparison result."""
    model_config = ConfigDict(from_attributes=True)

    bidder_id: str = Field(..., description="Bidder identifier or UUID")
    field_name: str = Field(..., description="Canonical parameter identifier (e.g. turnover, local_content_percent)")
    field_label: str = Field(..., description="Human-friendly parameter label")
    status: CrossSourceStatus = Field(..., description="Aggregated field verification status")
    evidence_ids: List[str] = Field(default_factory=list, description="All preserved evidence IDs evaluated for this field")
    compared_sources: List[str] = Field(default_factory=list, description="List of source types compared")
    normalized_values: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Preserved values per evidence item with source_type, normalized_value, display_value, and evidence_id"
    )
    explanation: str = Field(..., description="Traceable explanation of comparison findings")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence that the comparison determination is correct (NOT source authority)"
    )
    provenance_references: List[str] = Field(
        default_factory=list,
        description="Traceable citations for all evidence items evaluated"
    )
    is_mock_involved: bool = Field(
        default=False,
        description="True if any compared evidence item comes from a synthetic mock source"
    )
    discrepancy_details: List[DiscrepancyDetail] = Field(
        default_factory=list,
        description="Pairwise/subgroup comparison relationships detailing consistency or divergence"
    )


class BidderCrossSourceVerificationReport(BaseModel):
    """Complete cross-source verification report for a single bidder."""
    model_config = ConfigDict(from_attributes=True)

    bidder_id: str = Field(..., description="Bidder identifier or UUID")
    company_name: str = Field(..., description="Enterprise legal or trade name")
    tender_id: Optional[str] = Field(None, description="Associated tender UUID if applicable")
    entity_identifier: Optional[str] = Field(None, description="Showcase or registry identifier (e.g. BIDDER-01)")
    results: List[CrossSourceVerificationResult] = Field(
        default_factory=list,
        description="Field-level cross-source verification determinations"
    )
    total_fields_verified: int = Field(0, description="Total fields evaluated")
    consistent_count: int = Field(0, description="Count of fields evaluated as CONSISTENT")
    inconsistent_count: int = Field(0, description="Count of fields evaluated as INCONSISTENT")
    insufficient_evidence_count: int = Field(0, description="Count of fields evaluated as INSUFFICIENT_EVIDENCE")
    not_comparable_count: int = Field(0, description="Count of fields evaluated as NOT_COMPARABLE")
    is_mock_involved: bool = Field(
        default=False,
        description="True if any evaluated evidence item originated from a synthetic mock source"
    )
    disclaimer: str = Field(
        default=MOCK_SOURCE_DISCLAIMER,
        description="Mandatory disclaimer: MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp of report generation"
    )
