"""Pydantic schemas and source contracts for Mock Integrated Verification Sources.

Phase 6.1 — SIH26100 Mock Integrated Verification Foundation.
All records are explicitly marked is_mock=True with source_type:
"MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION".
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict


MOCK_SOURCE_TYPE_LABEL = "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION"


class BaseMockVerificationSchema(BaseModel):
    """Common contract across all mock government verification sources."""
    model_config = ConfigDict(from_attributes=True)

    verification_id: str = Field(..., description="Unique deterministic verification audit identifier")
    source: str = Field(..., description="Source code: GSTN, UDYAM, MCA, INCOME_TAX, MII")
    entity_identifier: str = Field(..., description="Showcase or vendor entity identifier (e.g. BIDDER-01)")
    status: str = Field(..., description="Source verification status (e.g. ACTIVE, VERIFIED, CANCELLED)")
    verified_fields: Dict[str, Any] = Field(default_factory=dict, description="Structured verified attributes")
    verification_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_response: Dict[str, Any] = Field(default_factory=dict, description="Simulated raw API payload")
    is_mock: bool = Field(default=True, description="Strict mock flag; always True for synthetic records")
    source_type: str = Field(default=MOCK_SOURCE_TYPE_LABEL, description="Explicit mock source disclaimer")


# ---------------------------------------------------------------------------
# 1. GSTN Schema
# ---------------------------------------------------------------------------

class MockGSTNRecordSchema(BaseMockVerificationSchema):
    gstin: str = Field(..., description="15-character Goods and Services Tax Identification Number")
    legal_name: str = Field(..., description="Registered legal business entity name")
    registration_status: str = Field(..., description="ACTIVE, INACTIVE, CANCELLED, SUSPENDED")
    registration_date: str = Field(..., description="Date of GST registration (YYYY-MM-DD)")
    state: str = Field(..., description="State or Union Territory of registration")
    verified_turnover: float = Field(..., description="Annual verified turnover in Crores (INR)")
    taxpayer_type: str = Field(default="Regular", description="Regular, Composition, etc.")
    filing_status: Optional[str] = Field(default="UP_TO_DATE", description="Filing regularity indicator")


# ---------------------------------------------------------------------------
# 2. Udyam / MSME Schema
# ---------------------------------------------------------------------------

class MockUdyamRecordSchema(BaseMockVerificationSchema):
    udyam_registration_number: str = Field(..., description="UDYAM registration number (e.g. UDYAM-DL-01-0012345)")
    enterprise_name: str = Field(..., description="Registered enterprise name")
    status: str = Field(..., description="ACTIVE, CANCELLED, SUSPENDED")
    enterprise_type: str = Field(..., description="MICRO, SMALL, MEDIUM")
    registration_date: str = Field(..., description="Date of Udyam registration (YYYY-MM-DD)")
    state: str = Field(..., description="State of enterprise")
    district: str = Field(..., description="District of enterprise")
    major_activity: Optional[str] = Field(default="SERVICES", description="SERVICES or MANUFACTURING")


# ---------------------------------------------------------------------------
# 3. MCA Schema
# ---------------------------------------------------------------------------

class MockMCARecordSchema(BaseMockVerificationSchema):
    cin: str = Field(..., description="21-character Corporate Identity Number (CIN)")
    legal_name: str = Field(..., description="Registered company name as per MCA registry")
    company_status: str = Field(..., description="ACTIVE, STRUCK_OFF, DORMANT, UNDER_LIQUIDATION")
    incorporation_date: str = Field(..., description="Date of incorporation (YYYY-MM-DD)")
    registered_state: str = Field(..., description="State of ROC registration")
    company_type: str = Field(default="Private Limited Company", description="Company structure type")
    authorized_capital_cr: Optional[float] = Field(default=None, description="Authorized capital in Crores")


# ---------------------------------------------------------------------------
# 4. Income Tax / PAN Schema
# ---------------------------------------------------------------------------

class MockIncomeTaxRecordSchema(BaseMockVerificationSchema):
    pan: str = Field(..., description="10-character Permanent Account Number")
    entity_name: str = Field(..., description="Entity name matching Income Tax PAN records")
    pan_status: str = Field(..., description="ACTIVE, INOPERATIVE, CANCELLED, INVALID")
    taxpayer_type: str = Field(default="COMPANY", description="COMPANY, FIRM, INDIVIDUAL, TRUST")
    last_itr_filed_fy: Optional[str] = Field(default="2024-25", description="Last ITR filing financial year")
    tax_compliance_status: Optional[str] = Field(default="COMPLIANT", description="COMPLIANT, NOTICE_PENDING, NON_FILER")


# ---------------------------------------------------------------------------
# 5. Make in India (MII) / Local Content Schema
# ---------------------------------------------------------------------------

class MockMIIRecordSchema(BaseMockVerificationSchema):
    product_category: str = Field(..., description="Product category or hardware specification under evaluation")
    verified_local_content: float = Field(..., description="Verified domestic local content percentage (0.0 to 100.0)")
    verification_status: str = Field(..., description="VERIFIED_CLASS_I, VERIFIED_CLASS_II, NON_LOCAL, CONTRADICTION")
    certifying_authority: Optional[str] = Field(default="Statutory Auditor / CA", description="Certification agency")
    certificate_reference: Optional[str] = Field(default=None, description="Audited reference certificate ID")
