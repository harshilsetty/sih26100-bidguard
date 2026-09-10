"""
app.models.statutory
~~~~~~~~~~~~~~~~~~~~
SQLAlchemy ORM model for storing statutory verification records.
Persists authoritative source facts, transport connection status,
domain verification status, temporal timestamps, and sanitized payloads.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Numeric, ForeignKey, JSON, DateTime, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import BaseModelMixin


class StatutoryVerificationRecord(Base, BaseModelMixin):
    """
    Persistent record of a statutory verification query execution.
    Preserves raw sanitized factual payloads, connection and verification statuses,
    and temporal query constraints for auditability.
    """
    __tablename__ = "statutory_verification_records"

    # Optional tender/bidder associations
    tender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    bidder_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bidders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Unique execution batch/verification identifier
    verification_id = Column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False, index=True)

    # Authority and source identification
    authority = Column(String(50), nullable=False, index=True)  # GSTN, UDYAM, MCA, INCOME_TAX, MII
    source_name = Column(String(100), nullable=False)
    query_identifier = Column(String(100), nullable=False, index=True)
    identifier_type = Column(String(50), nullable=False)  # gstin, pan, cin, udyam_number, etc.
    mode = Column(String(20), nullable=False, default="MOCK")  # MOCK or LIVE

    # Status separation
    connection_status = Column(String(50), nullable=False)  # SUCCESS, TIMEOUT, UNAVAILABLE, RATE_LIMITED, AUTH_FAILURE, ERROR
    verification_status = Column(String(50), nullable=False)  # VERIFIED, NOT_FOUND, INACTIVE, EXPIRED, UNVERIFIED, DISCREPANCY, FAILED

    # Temporal tracking
    retrieved_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    as_of_date = Column(Date, nullable=True)

    # Payload and confidence
    data_payload = Column(JSON, nullable=False, default=dict)
    confidence_score = Column(Numeric(4, 3), nullable=False, default=1.0)
    provenance_note = Column(Text, nullable=False, default="MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION")
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Numeric(10, 2), nullable=False, default=0.0)

    # Relationships
    tender = relationship("Tender")
    bidder = relationship("Bidder")
