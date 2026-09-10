from enum import Enum
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RecommendationCategory(str, Enum):
    """Permitted advisory categories for AI procurement recommendations."""
    RECOMMENDED_FOR_OFFICER_REVIEW = "RECOMMENDED_FOR_OFFICER_REVIEW"
    REQUIRES_ADDITIONAL_EVIDENCE = "REQUIRES_ADDITIONAL_EVIDENCE"
    HIGH_RISK_OFFICER_REVIEW = "HIGH_RISK_OFFICER_REVIEW"


class RecommendationSource(str, Enum):
    """Origin of the recommendation."""
    AI = "AI"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class OfficerAction(str, Enum):
    """Advisory actions recorded by a Procurement Officer during bid review."""
    ACKNOWLEDGED = "ACKNOWLEDGED"
    NEEDS_ADDITIONAL_EVIDENCE = "NEEDS_ADDITIONAL_EVIDENCE"
    OVERRIDE_REVIEW = "OVERRIDE_REVIEW"
    FINAL_OFFICER_DECISION = "FINAL_OFFICER_DECISION"


class EvidenceReference(BaseModel):
    """Grounding reference linking an AI finding or reason back to verified evidence."""
    reference_id: str = Field(..., description="Unique evidence chunk ID, verification ID, or clause reference")
    clause_code: Optional[str] = Field(None, description="Tender clause code, e.g. TECH-01, FIN-01")
    source_type: str = Field(..., description="Source classification: BIDDER_DOCUMENT or MOCK_GOVERNMENT_SOURCE")
    source_name: str = Field(..., description="Name of source document or government registry")
    page: Optional[int] = Field(None, description="Document page number if applicable")
    verification_id: Optional[str] = Field(None, description="Mock source cross-verification ID if applicable")
    summary: str = Field(..., description="Brief factual excerpt or verification finding")


class AIRecommendationResponse(BaseModel):
    """Strict structured AI recommendation and explainable procurement decision support."""
    model_config = ConfigDict(protected_namespaces=())

    recommendation_id: UUID
    tender_id: UUID
    bidder_id: UUID
    bidder_name: str

    recommendation: RecommendationCategory
    recommendation_source: RecommendationSource
    confidence: str = Field("HIGH", description="Confidence in the explanation/recommendation: HIGH, MEDIUM, LOW")

    overall_score: float
    risk_level: str

    executive_summary: str
    key_reasons: List[str] = Field(default_factory=list)
    positive_findings: List[str] = Field(default_factory=list)
    risk_findings: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)
    priority_actions: List[str] = Field(default_factory=list)
    supporting_references: List[EvidenceReference] = Field(default_factory=list)

    model_identifier: str
    generated_at: datetime
    disclaimer: str = (
        "AI-assisted procurement decision support. "
        "Final qualification and selection remain with the Procurement Officer."
    )


class OfficerReviewRequest(BaseModel):
    """Procurement Officer review action with mandatory non-empty justification."""
    action: OfficerAction
    justification: str = Field(..., min_length=5, description="Mandatory officer explanation for this action")
    recommendation_id: Optional[UUID] = None


class AuditRecordItem(BaseModel):
    """Representation of an append-only audit event."""
    model_config = ConfigDict(protected_namespaces=())

    id: UUID
    tender_id: UUID
    bidder_id: UUID
    evaluation_id: Optional[UUID] = None
    recommendation_id: UUID
    event_type: str
    recommendation_type: RecommendationCategory
    recommendation_source: RecommendationSource
    score_at_recommendation: float
    risk_at_recommendation: str
    recommendation_summary: str
    key_reasons: List[str] = Field(default_factory=list)
    evidence_references: List[EvidenceReference] = Field(default_factory=list)
    positive_findings: List[str] = Field(default_factory=list)
    risk_findings: List[str] = Field(default_factory=list)
    priority_actions: List[str] = Field(default_factory=list)
    model_identifier: str
    officer_action: Optional[OfficerAction] = None
    officer_comment: Optional[str] = None
    action_timestamp: datetime
    disclaimer: str
    created_at: datetime


class AuditTrailResponse(BaseModel):
    """Chronological append-only audit trail for a bidder under a tender."""
    tender_id: UUID
    bidder_id: UUID
    records: List[AuditRecordItem] = Field(default_factory=list)
