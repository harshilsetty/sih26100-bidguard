"""SQLAlchemy ORM models for Mock Government Verification Sources.

Phase 6.1 — SIH26100 Mock Integrated Verification Foundation.
Tables are logically isolated from tender/bidder operational tables:
1. mock_gstn_records
2. mock_udyam_records
3. mock_mca_records
4. mock_income_tax_records
5. mock_mii_records

All records explicitly carry is_mock=True and
source_type="MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION".
"""

from sqlalchemy import Column, String, Float, Boolean, DateTime, JSON, Index, Text
from datetime import datetime, timezone
from app.core.database import Base
from app.models.base import BaseModelMixin

MOCK_SOURCE_TYPE_LABEL = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"


class MockGSTNRecord(Base, BaseModelMixin):
    """Synthetic GSTN (Goods & Services Tax Network) verification records."""
    __tablename__ = "mock_gstn_records"

    verification_id = Column(String(100), nullable=False, unique=True, index=True)
    source = Column(String(50), default="GSTN", nullable=False)
    entity_identifier = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)

    # GSTN specific fields
    gstin = Column(String(15), nullable=False, unique=True, index=True)
    legal_name = Column(String(255), nullable=False)
    registration_status = Column(String(50), nullable=False)
    registration_date = Column(String(20), nullable=False)
    state = Column(String(100), nullable=False)
    verified_turnover = Column(Float, nullable=False)
    taxpayer_type = Column(String(50), default="Regular", nullable=False)
    filing_status = Column(String(50), default="UP_TO_DATE", nullable=False)

    # Verification metadata
    verified_fields = Column(JSON, default=dict, nullable=False)
    verification_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    raw_response = Column(JSON, default=dict, nullable=False)
    is_mock = Column(Boolean, default=True, nullable=False)
    source_type = Column(String(100), default=MOCK_SOURCE_TYPE_LABEL, nullable=False)

    __table_args__ = (
        Index("ix_mock_gstn_entity_status", "entity_identifier", "status"),
    )


class MockUdyamRecord(Base, BaseModelMixin):
    """Synthetic Udyam / MSME verification records."""
    __tablename__ = "mock_udyam_records"

    verification_id = Column(String(100), nullable=False, unique=True, index=True)
    source = Column(String(50), default="UDYAM", nullable=False)
    entity_identifier = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)

    # Udyam specific fields
    udyam_registration_number = Column(String(50), nullable=False, unique=True, index=True)
    enterprise_name = Column(String(255), nullable=False)
    enterprise_type = Column(String(50), nullable=False)  # MICRO, SMALL, MEDIUM
    registration_date = Column(String(20), nullable=False)
    state = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    major_activity = Column(String(50), default="SERVICES", nullable=False)

    # Verification metadata
    verified_fields = Column(JSON, default=dict, nullable=False)
    verification_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    raw_response = Column(JSON, default=dict, nullable=False)
    is_mock = Column(Boolean, default=True, nullable=False)
    source_type = Column(String(100), default=MOCK_SOURCE_TYPE_LABEL, nullable=False)

    __table_args__ = (
        Index("ix_mock_udyam_entity_type", "entity_identifier", "enterprise_type"),
    )


class MockMCARecord(Base, BaseModelMixin):
    """Synthetic Ministry of Corporate Affairs (MCA) corporate registry records."""
    __tablename__ = "mock_mca_records"

    verification_id = Column(String(100), nullable=False, unique=True, index=True)
    source = Column(String(50), default="MCA", nullable=False)
    entity_identifier = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)

    # MCA specific fields
    cin = Column(String(21), nullable=False, unique=True, index=True)
    legal_name = Column(String(255), nullable=False)
    company_status = Column(String(50), nullable=False)  # ACTIVE, STRUCK_OFF, DORMANT
    incorporation_date = Column(String(20), nullable=False)
    registered_state = Column(String(100), nullable=False)
    company_type = Column(String(100), default="Private Limited Company", nullable=False)
    authorized_capital_cr = Column(Float, nullable=True)

    # Verification metadata
    verified_fields = Column(JSON, default=dict, nullable=False)
    verification_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    raw_response = Column(JSON, default=dict, nullable=False)
    is_mock = Column(Boolean, default=True, nullable=False)
    source_type = Column(String(100), default=MOCK_SOURCE_TYPE_LABEL, nullable=False)

    __table_args__ = (
        Index("ix_mock_mca_entity_status", "entity_identifier", "company_status"),
    )


class MockIncomeTaxRecord(Base, BaseModelMixin):
    """Synthetic Income Tax Department PAN & tax compliance records."""
    __tablename__ = "mock_income_tax_records"

    verification_id = Column(String(100), nullable=False, unique=True, index=True)
    source = Column(String(50), default="INCOME_TAX", nullable=False)
    entity_identifier = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)

    # Income Tax specific fields
    pan = Column(String(10), nullable=False, unique=True, index=True)
    entity_name = Column(String(255), nullable=False)
    pan_status = Column(String(50), nullable=False)  # ACTIVE, INOPERATIVE, CANCELLED, INVALID
    taxpayer_type = Column(String(50), default="COMPANY", nullable=False)
    last_itr_filed_fy = Column(String(20), default="2024-25", nullable=False)
    tax_compliance_status = Column(String(50), default="COMPLIANT", nullable=False)

    # Verification metadata
    verified_fields = Column(JSON, default=dict, nullable=False)
    verification_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    raw_response = Column(JSON, default=dict, nullable=False)
    is_mock = Column(Boolean, default=True, nullable=False)
    source_type = Column(String(100), default=MOCK_SOURCE_TYPE_LABEL, nullable=False)

    __table_args__ = (
        Index("ix_mock_it_entity_status", "entity_identifier", "pan_status"),
    )


class MockMIIRecord(Base, BaseModelMixin):
    """Synthetic Make in India (MII) / Local Content verification records."""
    __tablename__ = "mock_mii_records"

    verification_id = Column(String(100), nullable=False, unique=True, index=True)
    source = Column(String(50), default="MII", nullable=False)
    entity_identifier = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)

    # MII specific fields
    product_category = Column(String(255), nullable=False)
    verified_local_content = Column(Float, nullable=False)
    verification_status = Column(String(50), nullable=False)  # VERIFIED_CLASS_I, VERIFIED_CLASS_II, NON_LOCAL, CONTRADICTION
    certifying_authority = Column(String(255), default="Statutory Auditor / CA", nullable=False)
    certificate_reference = Column(String(100), nullable=True)

    # Verification metadata
    verified_fields = Column(JSON, default=dict, nullable=False)
    verification_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    raw_response = Column(JSON, default=dict, nullable=False)
    is_mock = Column(Boolean, default=True, nullable=False)
    source_type = Column(String(100), default=MOCK_SOURCE_TYPE_LABEL, nullable=False)

    __table_args__ = (
        Index("ix_mock_mii_entity_content", "entity_identifier", "verified_local_content"),
    )


class MockDebarmentRecord(Base, BaseModelMixin):
    """Synthetic Debarment / Blacklisting records."""
    __tablename__ = "mock_debarment_records"

    verification_id = Column(String(100), nullable=False, unique=True, index=True)
    source = Column(String(50), default="DEBARMENT", nullable=False)
    entity_identifier = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False, index=True)

    # Identifier fields
    pan = Column(String(10), nullable=True, index=True)
    cin = Column(String(21), nullable=True, index=True)
    gstin = Column(String(15), nullable=True, index=True)
    udyam_registration_number = Column(String(50), nullable=True, index=True)

    # Debarment specific fields
    firm_name = Column(String(255), nullable=False, index=True)
    order_number = Column(String(100), nullable=False)
    authority_name = Column(String(255), nullable=False)
    reason = Column(Text, nullable=False)
    start_date = Column(String(20), nullable=True, index=True)
    end_date = Column(String(20), nullable=True, index=True)

    # Verification metadata
    verified_fields = Column(JSON, default=dict, nullable=False)
    verification_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    raw_response = Column(JSON, default=dict, nullable=False)
    is_mock = Column(Boolean, default=True, nullable=False)
    source_type = Column(String(100), default=MOCK_SOURCE_TYPE_LABEL, nullable=False)

    __table_args__ = (
        Index("ix_mock_debarment_pan", "pan"),
        Index("ix_mock_debarment_cin", "cin"),
        Index("ix_mock_debarment_dates", "start_date", "end_date"),
    )
