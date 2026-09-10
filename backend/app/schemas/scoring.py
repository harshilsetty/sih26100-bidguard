"""Pydantic schemas for Compliance Scoring, Risk Assessment, and Bidder Ranking.

Phase 6.4 — SIH26100 Compliance Score + Risk + Bidder Ranking Layer.

Core Architecture & Locked Rules:
1. 100-Point Scoring Model:
   - Tender Compliance = 50 points
   - Statutory Consistency = 20 points
   - Evidence Completeness = 15 points
   - Contradictions = 15 points
2. Independent Evidence Completeness:
   - Evaluates whether required evidence is available/sufficient (1.0 = sufficient, 0.5 = partial/ambiguous, 0.0 = missing).
   - Independent of PASS/FAIL compliance status.
3. Exact Contradiction Deductions:
   - Start at 15.0.
   - Minor contradiction = -3.0 points.
   - Major contradiction = -7.5 points.
   - Formula: max(0.0, 15.0 - (major_count * 7.5) - (minor_count * 3.0)).
4. Statutory NOT_COMPARABLE Handling:
   - Excluded from applicable statutory denominator.
5. Fixed Ranking Order:
   - overall_score DESC -> risk_level severity ASC (LOW < MEDIUM < HIGH) -> bidder_id ASC.
   - Strictly decision support for the Procurement Officer (NEVER winner selection).
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

DECISION_SUPPORT_DISCLAIMER = (
    "AI-assisted procurement decision support. "
    "Final qualification and selection remain with the Procurement Officer."
)


class RiskLevel(str, Enum):
    """Risk severity classifications."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ContradictionSeverity(str, Enum):
    """Deterministic contradiction severity classifications."""
    NONE = "NONE"
    MINOR = "MINOR"
    MAJOR = "MAJOR"


class ScoreBreakdown(BaseModel):
    """Exact four-component breakdown of the 100-point scoring model."""
    model_config = ConfigDict(from_attributes=True)

    tender_compliance: float = Field(
        ...,
        ge=0.0,
        le=50.0,
        description="Earned points from tender clause compliance (out of 50.0)"
    )
    statutory_consistency: float = Field(
        ...,
        ge=0.0,
        le=20.0,
        description="Earned points from statutory cross-source verification (out of 20.0)"
    )
    evidence_completeness: float = Field(
        ...,
        ge=0.0,
        le=15.0,
        description="Earned points from evidence availability and sufficiency (out of 15.0)"
    )
    contradiction_score: float = Field(
        ...,
        ge=0.0,
        le=15.0,
        description="Earned points after deterministic deductions for contradictions (out of 15.0)"
    )


class ScoreSummary(BaseModel):
    """Summary counts of evaluations and verification outcomes."""
    model_config = ConfigDict(from_attributes=True)

    pass_count: int = Field(0, description="Total clauses evaluated as PASS")
    fail_count: int = Field(0, description="Total clauses evaluated as FAIL")
    review_count: int = Field(0, description="Total clauses evaluated as REVIEW")
    inconsistency_count: int = Field(0, description="Total statutory checks evaluated as INCONSISTENT")
    major_contradiction_count: int = Field(0, description="Count of major contradictions detected")
    minor_contradiction_count: int = Field(0, description="Count of minor contradictions detected")


class BidderComplianceScoreResponse(BaseModel):
    """Comprehensive, explainable compliance score and risk determination for a bidder."""
    model_config = ConfigDict(from_attributes=True)

    bidder_id: str = Field(..., description="Unique bidder identifier or UUID")
    tender_id: Optional[str] = Field(None, description="Tender identifier or UUID")
    company_name: str = Field(..., description="Enterprise legal or trade name")
    overall_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Overall compliance score out of 100.0 (rounded to 2 decimal places)"
    )
    risk_level: RiskLevel = Field(..., description="Assessed risk level: LOW, MEDIUM, or HIGH")
    breakdown: ScoreBreakdown = Field(..., description="Component breakdown out of 100.0")
    risk_triggers: List[str] = Field(
        default_factory=list,
        description="Explicit justifications for safety risk overrides (e.g. major contradictions, mandatory fail)"
    )
    summary: ScoreSummary = Field(..., description="Evaluation and contradiction counts")
    calculation_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed formulas and intermediate calculations for full transparency"
    )
    disclaimer: str = Field(
        default=DECISION_SUPPORT_DISCLAIMER,
        description="Mandatory procurement decision support notice"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp of score generation"
    )


class RankedBidderItem(BaseModel):
    """Individual ranked bidder item for tender comparison and shortlist view."""
    model_config = ConfigDict(from_attributes=True)

    rank: int = Field(..., ge=1, description="Deterministic rank position (1-based)")
    bidder_id: str = Field(..., description="Bidder identifier or UUID")
    company_name: str = Field(..., description="Enterprise legal or trade name")
    overall_score: float = Field(..., ge=0.0, le=100.0, description="Overall compliance score out of 100.0")
    risk_level: RiskLevel = Field(..., description="Risk level: LOW, MEDIUM, or HIGH")
    breakdown: ScoreBreakdown = Field(..., description="Four-part score breakdown")
    recommendation: str = Field(
        default="Recommended for Officer Review",
        description="Decision-support advisory recommendation (never winner or auto-qualification)"
    )
    warning_count: int = Field(0, description="Total count of non-compliant or contradictory flags")
    key_warnings: List[str] = Field(
        default_factory=list,
        description="Key alert summaries (e.g. 'Turnover mismatch: ₹8 Cr vs ₹3.65 Cr')"
    )


class TenderBidderRankingResponse(BaseModel):
    """Complete comparative ranking report for all bidders under a tender."""
    model_config = ConfigDict(from_attributes=True)

    tender_id: str = Field(..., description="Tender UUID")
    tender_title: str = Field(..., description="Tender title or description")
    total_bidders: int = Field(..., description="Total bidders evaluated and ranked")
    rankings: List[RankedBidderItem] = Field(
        default_factory=list,
        description="Bidders sorted by score DESC -> risk ASC -> bidder_id ASC"
    )
    disclaimer: str = Field(
        default=DECISION_SUPPORT_DISCLAIMER,
        description="Mandatory procurement decision support notice"
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp of ranking report generation"
    )
