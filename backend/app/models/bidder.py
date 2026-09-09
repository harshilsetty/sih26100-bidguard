from sqlalchemy import Column, String, Numeric, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import BaseModelMixin


class Bidder(Base, BaseModelMixin):
    __tablename__ = "bidders"

    tender_id = Column(UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)
    company_name = Column(String(300), nullable=False)
    overall_risk_score = Column(Numeric(5, 2), nullable=True)  # 0 to 100
    final_status = Column(String(50), default="UNDER_REVIEW", nullable=False)  # QUALIFIED, DISQUALIFIED, UNDER_REVIEW

    # Relationships
    tender = relationship("Tender", back_populates="bidders")
    documents = relationship("BidDocument", back_populates="bidder", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="bidder", cascade="all, delete-orphan")
    evaluations = relationship("ComplianceEvaluation", back_populates="bidder", cascade="all, delete-orphan")


class BidDocument(Base, BaseModelMixin):
    __tablename__ = "bid_documents"

    bidder_id = Column(UUID(as_uuid=True), ForeignKey("bidders.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(300), nullable=False)
    file_path = Column(String(1000), nullable=False)
    doc_type = Column(String(100), nullable=True)  # e.g., TECHNICAL_PROPOSAL, FINANCIAL_STATEMENT, etc.
    total_pages = Column(Integer, default=0, nullable=False)
    empty_pages_count = Column(Integer, default=0, nullable=False)
    extraction_status = Column(String(50), default="PENDING", nullable=False)  # PENDING, EXTRACTED, EMPTY_SCANNED, FAILED
    error_message = Column(Text, nullable=True)

    # Relationships
    bidder = relationship("Bidder", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
