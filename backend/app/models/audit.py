import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Numeric, ForeignKey, JSON, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import BaseModelMixin


class RecommendationAuditRecord(Base, BaseModelMixin):
    """
    Append-only, immutable audit record preserving AI recommendations,
    deterministic fallbacks, and subsequent Procurement Officer review actions.
    Never update or delete existing historical rows.
    """
    __tablename__ = "recommendation_audit_records"

    tender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bidder_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bidders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("compliance_evaluations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Identifies the recommendation batch / grouping
    recommendation_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Event classification: "RECOMMENDATION_GENERATED" or "OFFICER_REVIEW"
    event_type = Column(String(50), nullable=False, default="RECOMMENDATION_GENERATED")

    # Recommendation classification: RECOMMENDED_FOR_OFFICER_REVIEW, REQUIRES_ADDITIONAL_EVIDENCE, HIGH_RISK_OFFICER_REVIEW
    recommendation_type = Column(String(50), nullable=False)

    # Recommendation origin: AI or DETERMINISTIC_FALLBACK
    recommendation_source = Column(String(50), nullable=False)

    # Score and risk snapshot at the time of this record
    score_at_recommendation = Column(Numeric(5, 2), nullable=False)
    risk_at_recommendation = Column(String(50), nullable=False)

    # Structured summary and explanation details
    recommendation_summary = Column(Text, nullable=False)
    key_reasons = Column(JSON, nullable=True)  # List[str]
    evidence_references = Column(JSON, nullable=True)  # List[dict]
    positive_findings = Column(JSON, nullable=True)  # List[str]
    risk_findings = Column(JSON, nullable=True)  # List[str]
    missing_evidence = Column(JSON, nullable=True)  # List[str]
    contradictions = Column(JSON, nullable=True)  # List[str]
    priority_actions = Column(JSON, nullable=True)  # List[str]

    # Model or engine identifier
    model_identifier = Column(String(100), nullable=False)  # e.g., "openai/gpt-oss-20b" or "deterministic-engine"

    # Officer review action if event_type == "OFFICER_REVIEW"
    officer_action = Column(String(50), nullable=True)  # ACKNOWLEDGED, NEEDS_ADDITIONAL_EVIDENCE, OVERRIDE_REVIEW, FINAL_OFFICER_DECISION
    officer_comment = Column(Text, nullable=True)

    # Timestamp of the specific action
    action_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Statutory decision support disclaimer
    disclaimer = Column(
        Text,
        nullable=False,
        default="AI-assisted procurement decision support. Final qualification and selection remain with the Procurement Officer.",
    )

    # Relationships
    tender = relationship("Tender")
    bidder = relationship("Bidder")
    evaluation = relationship("ComplianceEvaluation")
