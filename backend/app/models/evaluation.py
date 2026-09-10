from sqlalchemy import Column, String, Text, Numeric, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import BaseModelMixin


class ComplianceEvaluation(Base, BaseModelMixin):
    __tablename__ = "compliance_evaluations"

    bidder_id = Column(UUID(as_uuid=True), ForeignKey("bidders.id", ondelete="CASCADE"), nullable=False, index=True)
    clause_id = Column(UUID(as_uuid=True), ForeignKey("tender_clauses.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(20), default="REVIEW", nullable=False)  # PASS, FAIL, REVIEW
    confidence_score = Column(Numeric(4, 3), nullable=True)  # 0.000 to 1.000
    claimed_value = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)
    evidence_snippet = Column(Text, nullable=True)
    evidence_page_number = Column(Integer, nullable=True)
    evidence_chunk_id = Column(String(100), nullable=True)

    # Phase 7 OCR Provenance
    extraction_method = Column(String(50), default="DIGITAL_TEXT", nullable=True)
    ocr_confidence = Column(Numeric(4, 3), nullable=True)

    # Detailed deterministic rule check audit
    rule_result = Column(JSON, nullable=True)

    # Contradiction flag & explanation
    contradiction_detected = Column(Boolean, default=False, nullable=False)
    contradiction_details = Column(Text, nullable=True)

    risk_level = Column(String(20), default="MEDIUM", nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL

    # Human Override
    override_status = Column(String(20), nullable=True)  # PASS, FAIL, REVIEW
    override_reason = Column(Text, nullable=True)

    # Relationships
    bidder = relationship("Bidder", back_populates="evaluations")
    clause = relationship("TenderClause", back_populates="evaluations")
