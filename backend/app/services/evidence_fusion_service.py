"""Evidence Fusion Service.

Phase 6.3 — SIH26100 Evidence Fusion Foundation.
Normalizes, groups, and fuses evidence across Bidder Documents and Mock Statutory Sources:
- BIDDER_DOCUMENT
- GSTN
- UDYAM
- MCA
- INCOME_TAX
- MAKE_IN_INDIA

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. Reuses existing extracted bidder evidence/claims and parameter models (NO second LLM extraction path).
2. Pure aggregation and normalization layer: does NOT make compliance decisions, calculate risk, or detect contradictions.
3. Preserves all sources independently: conflicting values (e.g. Bidder ₹8 Cr vs GSTN ₹3.65 Cr) remain side-by-side.
4. Strict bidder isolation: bidder evidence never leaks across bidder tenants.
5. Strict source provenance: document citations have file/page/quote; statutory records have verification audit IDs.
6. All mock government evidence carries is_mock=True and label "MOCK GOVERNMENT SOURCE — SIH DEMONSTRATION".
"""

import re
import logging
from typing import List, Dict, Any, Optional, Union
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.schemas.evidence_fusion import (
    SourceType,
    EvidenceType,
    EvidenceItem,
    FieldEvidenceGroup,
    BidderEvidenceFusionProfile,
    MOCK_SOURCE_TYPE_LABEL,
)
from app.schemas.evaluation import ParameterClaim, ClauseComplianceEvaluation
from app.models.bidder import Bidder, BidDocument
from app.models.chunk import DocumentChunk
from app.models.evaluation import ComplianceEvaluation as ComplianceEvaluationModel
from app.models.mock_sources import (
    MockGSTNRecord,
    MockUdyamRecord,
    MockMCARecord,
    MockIncomeTaxRecord,
    MockMIIRecord,
)
from app.services.mock_data_generator import SHOWCASE_BIDDERS_CONFIG

logger = logging.getLogger(__name__)

# Canonical field label mappings for clean UI display
FIELD_LABELS: Dict[str, str] = {
    "turnover": "Annual Turnover",
    "local_content_percent": "Make in India (MII) Local Content",
    "pan_status": "PAN Status (Income Tax)",
    "tax_compliance_status": "Tax Compliance Status (ITR)",
    "gstin_status": "GSTIN Registration Status",
    "filing_status": "GST Filing Regularity",
    "enterprise_type": "MSME Classification (Udyam)",
    "udyam_status": "Udyam Registration Status",
    "company_status": "Corporate Registration Status (MCA)",
    "authorized_capital": "Authorized Capital (MCA)",
    "cpu_cores": "Server Compute Infrastructure (CPU Cores)",
    "warranty_years": "Comprehensive OEM Warranty",
    "delivery_days": "Delivery Timeline & SLA",
    "emd_amount": "Earnest Money Deposit (EMD)",
    "bis_and_iso_cert": "Quality Standards & BIS/ISO Certification",
    "similar_contracts_count": "Past Contract Execution Experience",
    "mii_classification": "Make in India Classification",
}

# Unit normalization dictionary
UNIT_MAPPINGS: Dict[str, str] = {
    "crores": "CR",
    "crore": "CR",
    "cr": "CR",
    "inr crores": "CR",
    "inr crore": "CR",
    "percent": "%",
    "percentage": "%",
    "%": "%",
    "cores": "cores",
    "core": "cores",
    "years": "years",
    "year": "years",
    "yr": "years",
    "yrs": "years",
    "days": "days",
    "day": "days",
    "inr": "INR",
    "rs": "INR",
    "rupees": "INR",
}


def normalize_unit(unit_raw: Optional[str]) -> Optional[str]:
    """Standardize unit strings (e.g. 'Crores' -> 'CR', 'percent' -> '%')."""
    if not unit_raw:
        return None
    u_clean = unit_raw.strip().lower()
    return UNIT_MAPPINGS.get(u_clean, unit_raw.strip().upper())


def normalize_value(val: Any) -> Optional[Union[float, int, str, bool]]:
    """Standardize scalar value while preserving original semantic type."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        # Round float to 2 decimals for clean representation
        return round(float(val), 2) if isinstance(val, float) else val
    val_str = str(val).strip()
    # Try converting numeric string
    try:
        if "." in val_str:
            return round(float(val_str), 2)
        return int(val_str)
    except (ValueError, TypeError):
        return val_str


def format_display_value(val: Any, unit: Optional[str] = None, field: str = "") -> str:
    """Produce human-readable formatted string for display."""
    if val is None:
        return "Not Declared / Not Found"
    if isinstance(val, bool):
        return "Confirmed Present" if val else "Not Confirmed"

    unit_norm = normalize_unit(unit)
    if "turnover" in field or unit_norm == "CR":
        try:
            return f"₹{float(val):.2f} Cr"
        except (ValueError, TypeError):
            return f"{val} {unit_norm or ''}".strip()

    if unit_norm == "%" or "percent" in field:
        try:
            return f"{float(val):.1f}%"
        except (ValueError, TypeError):
            return f"{val}%"

    if unit_norm == "INR" or "emd" in field:
        try:
            return f"₹{float(val):,.0f}"
        except (ValueError, TypeError):
            return f"{val} INR"

    if unit_norm:
        return f"{val} {unit_norm}"

    return str(val)


class EvidenceFusionService:
    """Service for collecting, normalizing, and grouping multi-source procurement evidence."""

    @staticmethod
    def resolve_bidder_entity_identifier(
        bidder_company_name: str,
        explicit_identifier: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve a bidder's canonical entity identifier (e.g. 'BIDDER-01') without assuming exact display names."""
        if explicit_identifier:
            return explicit_identifier.strip().upper()

        name = bidder_company_name or ""

        # 1. Direct regex match on company name (e.g. "(Bidder A)", "BIDDER-01", "Bidder 10")
        m_bidder = re.search(r"bidder\s*([a-j0-9]+)", name, re.IGNORECASE)
        if m_bidder:
            code = m_bidder.group(1).upper()
            letter_map = {
                "A": "BIDDER-01",
                "B": "BIDDER-09",
                "C": "BIDDER-10",
                "1": "BIDDER-01",
                "01": "BIDDER-01",
                "2": "BIDDER-02",
                "02": "BIDDER-02",
                "3": "BIDDER-03",
                "03": "BIDDER-03",
                "4": "BIDDER-04",
                "04": "BIDDER-04",
                "5": "BIDDER-05",
                "05": "BIDDER-05",
                "6": "BIDDER-06",
                "06": "BIDDER-06",
                "7": "BIDDER-07",
                "07": "BIDDER-07",
                "8": "BIDDER-08",
                "08": "BIDDER-08",
                "9": "BIDDER-09",
                "09": "BIDDER-09",
                "10": "BIDDER-10",
            }
            if code in letter_map:
                return letter_map[code]

        # 2. Normalized corporate name matching against SHOWCASE_BIDDERS_CONFIG
        clean_name = re.sub(r"\(.*?\)", "", name).strip().lower()
        clean_name = re.sub(r"(\bpvt\b|\bltd\b|\bprivate\b|\blimited\b|\bco\b|\bcompany\b)", "", clean_name).strip()

        for config in SHOWCASE_BIDDERS_CONFIG:
            cfg_name = config["company_name"].lower()
            cfg_clean = re.sub(r"(\bpvt\b|\bltd\b|\bprivate\b|\blimited\b|\bco\b|\bcompany\b)", "", cfg_name).strip()
            if clean_name and (clean_name in cfg_clean or cfg_clean in clean_name):
                return config["entity_identifier"]

        return None

    @classmethod
    def adapt_parameter_claim(
        cls,
        claim: ParameterClaim,
        bidder_id: str,
    ) -> EvidenceItem:
        """Adapt an existing ParameterClaim into a normalized EvidenceItem."""
        norm_val = normalize_value(claim.value)
        norm_unit = normalize_unit(claim.unit)
        disp_val = format_display_value(norm_val, norm_unit, claim.parameter)
        doc_name = claim.document or "Bidder Submission Document"
        provenance = f"{doc_name} (Page {claim.page}): '{claim.quote.strip()}'"

        return EvidenceItem(
            bidder_id=str(bidder_id),
            evidence_type=EvidenceType.DOCUMENT_CLAIM,
            source_type=SourceType.BIDDER_DOCUMENT,
            source_name=doc_name,
            field_name=claim.parameter,
            normalized_value=norm_val,
            display_value=disp_val,
            unit=norm_unit,
            status=None,
            confidence=1.0,
            document_id=None,
            page_number=claim.page,
            source_record_id=claim.chunk_id,
            provenance_reference=provenance,
            is_mock=False,
        )

    @classmethod
    def adapt_compliance_evaluation(
        cls,
        eval_obj: Union[ComplianceEvaluationModel, Any],
        bidder_id: str,
        doc_name: Optional[str] = None,
    ) -> Optional[EvidenceItem]:
        """Adapt an existing ComplianceEvaluation record into a normalized EvidenceItem."""
        rule_res = getattr(eval_obj, "rule_result", None) or {}
        clause = getattr(eval_obj, "clause", None)

        # Identify target field name
        field = rule_res.get("parameter")
        if not field and clause:
            rule_cfg = getattr(clause, "rule_config", None) or {}
            field = rule_cfg.get("parameter")
        if not field and clause:
            from app.services.ai_evidence_interpreter import identify_target_parameter
            field = identify_target_parameter(clause)
        if not field:
            field = "general"

        raw_val = rule_res.get("actual_value")
        raw_unit = rule_res.get("unit")
        claimed_str = getattr(eval_obj, "claimed_value", None)

        if raw_val is None and claimed_str:
            # Try to parse claimed_value string (e.g. "6.85 Crores", "55 %")
            m_val = re.search(r"([\d.]+)\s*([a-zA-Z%]+)?", claimed_str)
            if m_val:
                raw_val = m_val.group(1)
                raw_unit = m_val.group(2) or raw_unit

        norm_val = normalize_value(raw_val)
        norm_unit = normalize_unit(raw_unit)
        disp_val = claimed_str or format_display_value(norm_val, norm_unit, field)

        page_num = getattr(eval_obj, "evidence_page_number", None)
        snippet = (getattr(eval_obj, "evidence_snippet", None) or "").strip()
        doc_label = doc_name or "Bidder Technical Proposal"
        provenance = f"{doc_label}"
        if page_num:
            provenance += f" (Page {page_num})"
        if snippet:
            provenance += f": '{snippet[:120]}...'" if len(snippet) > 120 else f": '{snippet}'"

        return EvidenceItem(
            bidder_id=str(bidder_id),
            evidence_type=EvidenceType.DOCUMENT_CLAIM,
            source_type=SourceType.BIDDER_DOCUMENT,
            source_name=doc_label,
            field_name=field,
            normalized_value=norm_val,
            display_value=disp_val,
            unit=norm_unit,
            status=None,
            confidence=float(getattr(eval_obj, "confidence_score", 1.0) or 1.0),
            document_id=None,
            page_number=page_num,
            source_record_id=getattr(eval_obj, "evidence_chunk_id", None),
            provenance_reference=provenance,
            is_mock=False,
        )

    @classmethod
    async def collect_bidder_document_evidence(
        cls,
        bidder_id: Union[UUID, str],
        db: AsyncSession,
    ) -> List[EvidenceItem]:
        """Collect all document-derived evidence items for a bidder from existing evaluations and chunks."""
        b_uuid = UUID(str(bidder_id))
        items: List[EvidenceItem] = []

        # 1. Query existing ComplianceEvaluation records for this bidder
        stmt_eval = (
            select(ComplianceEvaluationModel)
            .where(ComplianceEvaluationModel.bidder_id == b_uuid)
        )
        evals = (await db.execute(stmt_eval)).scalars().all()

        for ev in evals:
            item = cls.adapt_compliance_evaluation(ev, bidder_id=str(b_uuid))
            if item:
                items.append(item)

        # 2. Extract multi-chunk claims from bidder document chunks using deterministic rules
        # This captures multi-page claims (e.g. Bidder C Page 1 local content 55%, Page 2 BOM 32%)
        stmt_chunks = (
            select(DocumentChunk)
            .where(DocumentChunk.bidder_id == b_uuid)
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        chunks = (await db.execute(stmt_chunks)).scalars().all()

        # Check for multiple claims within chunks (without calling any external LLM)
        existing_signatures = {(it.field_name, it.page_number, it.normalized_value) for it in items}

        for c in chunks:
            text = c.content or ""
            doc_label = f"Document Chunk (Page {c.page_number})"

            # Turnover patterns
            for m in re.finditer(r"(?:turnover|turn\s*over)[^.\n]*?INR\s*([\d.]+)\s*Crores?", text, re.IGNORECASE):
                val = float(m.group(1))
                sig = ("turnover", c.page_number, round(val, 2))
                if sig not in existing_signatures:
                    existing_signatures.add(sig)
                    items.append(EvidenceItem(
                        bidder_id=str(b_uuid),
                        evidence_type=EvidenceType.DOCUMENT_CLAIM,
                        source_type=SourceType.BIDDER_DOCUMENT,
                        source_name=doc_label,
                        field_name="turnover",
                        normalized_value=round(val, 2),
                        display_value=f"₹{val:.2f} Cr",
                        unit="CR",
                        page_number=c.page_number,
                        source_record_id=str(c.id),
                        provenance_reference=f"{doc_label}: '{m.group(0).strip()}'",
                        is_mock=False,
                    ))

            # Local content patterns
            for m in re.finditer(r"(?:local\s*content|domestic\s*value)[^.\n]*?(\d+)\s*(?:percent|%)", text, re.IGNORECASE):
                val = float(m.group(1))
                sig = ("local_content_percent", c.page_number, round(val, 2))
                if sig not in existing_signatures:
                    existing_signatures.add(sig)
                    items.append(EvidenceItem(
                        bidder_id=str(b_uuid),
                        evidence_type=EvidenceType.DOCUMENT_CLAIM,
                        source_type=SourceType.BIDDER_DOCUMENT,
                        source_name=doc_label,
                        field_name="local_content_percent",
                        normalized_value=round(val, 2),
                        display_value=f"{val:.1f}%",
                        unit="%",
                        page_number=c.page_number,
                        source_record_id=str(c.id),
                        provenance_reference=f"{doc_label}: '{m.group(0).strip()}'",
                        is_mock=False,
                    ))

        return items

    @classmethod
    async def collect_mock_source_evidence(
        cls,
        bidder_company_name: str,
        bidder_id: Union[UUID, str],
        db: AsyncSession,
        entity_identifier: Optional[str] = None,
    ) -> List[EvidenceItem]:
        """Collect statutory evidence from isolated synthetic registries (GSTN, Udyam, MCA, Income Tax, MII)."""
        resolved_id = cls.resolve_bidder_entity_identifier(bidder_company_name, entity_identifier)
        clean_name = re.sub(r"\(.*?\)", "", bidder_company_name).strip()

        items: List[EvidenceItem] = []
        b_id_str = str(bidder_id)

        # -------------------------------------------------------------------
        # 1. GSTN
        # -------------------------------------------------------------------
        gstn_query = select(MockGSTNRecord)
        if resolved_id:
            gstn_query = gstn_query.where(MockGSTNRecord.entity_identifier == resolved_id)
        else:
            gstn_query = gstn_query.where(MockGSTNRecord.legal_name.ilike(f"%{clean_name}%"))

        gstn_rec = (await db.execute(gstn_query)).scalars().first()
        if gstn_rec:
            # Turnover
            items.append(EvidenceItem(
                bidder_id=b_id_str,
                evidence_type=EvidenceType.STATUTORY_REGISTRY,
                source_type=SourceType.GSTN,
                source_name="Goods & Services Tax Network (GSTN)",
                field_name="turnover",
                normalized_value=round(float(gstn_rec.verified_turnover), 2),
                display_value=f"₹{gstn_rec.verified_turnover:.2f} Cr",
                unit="CR",
                status=gstn_rec.registration_status,
                confidence=1.0,
                page_number=None,  # Do NOT invent page numbers for statutory records
                source_record_id=gstn_rec.verification_id,
                raw_reference={"gstin": gstn_rec.gstin, "taxpayer_type": gstn_rec.taxpayer_type},
                provenance_reference=(
                    f"GSTN Verification ID: {gstn_rec.verification_id} | "
                    f"GSTIN: {gstn_rec.gstin} | State: {gstn_rec.state} | Status: {gstn_rec.registration_status}"
                ),
                is_mock=True,
            ))
            # GSTIN Status
            items.append(EvidenceItem(
                bidder_id=b_id_str,
                evidence_type=EvidenceType.STATUTORY_REGISTRY,
                source_type=SourceType.GSTN,
                source_name="Goods & Services Tax Network (GSTN)",
                field_name="gstin_status",
                normalized_value=gstn_rec.registration_status,
                display_value=gstn_rec.registration_status,
                unit=None,
                status=gstn_rec.registration_status,
                confidence=1.0,
                page_number=None,
                source_record_id=gstn_rec.verification_id,
                provenance_reference=f"GSTN Verification ID: {gstn_rec.verification_id} | Registration: {gstn_rec.registration_status}",
                is_mock=True,
            ))
            # Filing Status
            items.append(EvidenceItem(
                bidder_id=b_id_str,
                evidence_type=EvidenceType.STATUTORY_REGISTRY,
                source_type=SourceType.GSTN,
                source_name="Goods & Services Tax Network (GSTN)",
                field_name="filing_status",
                normalized_value=gstn_rec.filing_status,
                display_value=gstn_rec.filing_status,
                unit=None,
                status=gstn_rec.filing_status,
                confidence=1.0,
                page_number=None,
                source_record_id=gstn_rec.verification_id,
                provenance_reference=f"GSTN Verification ID: {gstn_rec.verification_id} | Filing Regularity: {gstn_rec.filing_status}",
                is_mock=True,
            ))

        # -------------------------------------------------------------------
        # 2. Udyam / MSME
        # -------------------------------------------------------------------
        udyam_query = select(MockUdyamRecord)
        if resolved_id:
            udyam_query = udyam_query.where(MockUdyamRecord.entity_identifier == resolved_id)
        else:
            udyam_query = udyam_query.where(MockUdyamRecord.enterprise_name.ilike(f"%{clean_name}%"))

        udyam_rec = (await db.execute(udyam_query)).scalars().first()
        if udyam_rec:
            items.append(EvidenceItem(
                bidder_id=b_id_str,
                evidence_type=EvidenceType.STATUTORY_REGISTRY,
                source_type=SourceType.UDYAM,
                source_name="Udyam / Ministry of MSME",
                field_name="enterprise_type",
                normalized_value=udyam_rec.enterprise_type,
                display_value=udyam_rec.enterprise_type,
                unit=None,
                status=udyam_rec.status,
                confidence=1.0,
                page_number=None,
                source_record_id=udyam_rec.verification_id,
                raw_reference={"udyam_reg": udyam_rec.udyam_registration_number, "scale": udyam_rec.enterprise_type},
                provenance_reference=(
                    f"Udyam Verification ID: {udyam_rec.verification_id} | "
                    f"Reg: {udyam_rec.udyam_registration_number} | Scale: {udyam_rec.enterprise_type} | Status: {udyam_rec.status}"
                ),
                is_mock=True,
            ))
            items.append(EvidenceItem(
                bidder_id=b_id_str,
                evidence_type=EvidenceType.STATUTORY_REGISTRY,
                source_type=SourceType.UDYAM,
                source_name="Udyam / Ministry of MSME",
                field_name="udyam_status",
                normalized_value=udyam_rec.status,
                display_value=udyam_rec.status,
                unit=None,
                status=udyam_rec.status,
                confidence=1.0,
                page_number=None,
                source_record_id=udyam_rec.verification_id,
                provenance_reference=f"Udyam Verification ID: {udyam_rec.verification_id} | Registration Status: {udyam_rec.status}",
                is_mock=True,
            ))

        # -------------------------------------------------------------------
        # 3. MCA Corporate Registry
        # -------------------------------------------------------------------
        mca_query = select(MockMCARecord)
        if resolved_id:
            mca_query = mca_query.where(MockMCARecord.entity_identifier == resolved_id)
        else:
            mca_query = mca_query.where(MockMCARecord.legal_name.ilike(f"%{clean_name}%"))

        mca_rec = (await db.execute(mca_query)).scalars().first()
        if mca_rec:
            items.append(EvidenceItem(
                bidder_id=b_id_str,
                evidence_type=EvidenceType.STATUTORY_REGISTRY,
                source_type=SourceType.MCA,
                source_name="Ministry of Corporate Affairs (MCA)",
                field_name="company_status",
                normalized_value=mca_rec.company_status,
                display_value=mca_rec.company_status,
                unit=None,
                status=mca_rec.company_status,
                confidence=1.0,
                page_number=None,
                source_record_id=mca_rec.verification_id,
                raw_reference={"cin": mca_rec.cin, "company_type": mca_rec.company_type},
                provenance_reference=(
                    f"MCA Verification ID: {mca_rec.verification_id} | "
                    f"CIN: {mca_rec.cin} | State: {mca_rec.registered_state} | Status: {mca_rec.company_status}"
                ),
                is_mock=True,
            ))
            if mca_rec.authorized_capital_cr is not None:
                items.append(EvidenceItem(
                    bidder_id=b_id_str,
                    evidence_type=EvidenceType.STATUTORY_REGISTRY,
                    source_type=SourceType.MCA,
                    source_name="Ministry of Corporate Affairs (MCA)",
                    field_name="authorized_capital",
                    normalized_value=round(float(mca_rec.authorized_capital_cr), 2),
                    display_value=f"₹{mca_rec.authorized_capital_cr:.2f} Cr",
                    unit="CR",
                    status=mca_rec.company_status,
                    confidence=1.0,
                    page_number=None,
                    source_record_id=mca_rec.verification_id,
                    provenance_reference=f"MCA Verification ID: {mca_rec.verification_id} | Authorized Capital: ₹{mca_rec.authorized_capital_cr:.2f} Cr",
                    is_mock=True,
                ))

        # -------------------------------------------------------------------
        # 4. Income Tax / PAN
        # -------------------------------------------------------------------
        it_query = select(MockIncomeTaxRecord)
        if resolved_id:
            it_query = it_query.where(MockIncomeTaxRecord.entity_identifier == resolved_id)
        else:
            it_query = it_query.where(MockIncomeTaxRecord.entity_name.ilike(f"%{clean_name}%"))

        it_rec = (await db.execute(it_query)).scalars().first()
        if it_rec:
            items.append(EvidenceItem(
                bidder_id=b_id_str,
                evidence_type=EvidenceType.STATUTORY_REGISTRY,
                source_type=SourceType.INCOME_TAX,
                source_name="Income Tax Department (PAN/ITR)",
                field_name="pan_status",
                normalized_value=it_rec.pan_status,
                display_value=it_rec.pan_status,
                unit=None,
                status=it_rec.pan_status,
                confidence=1.0,
                page_number=None,
                source_record_id=it_rec.verification_id,
                raw_reference={"pan": it_rec.pan, "taxpayer_type": it_rec.taxpayer_type},
                provenance_reference=(
                    f"Income Tax Verification ID: {it_rec.verification_id} | "
                    f"PAN: {it_rec.pan} | Status: {it_rec.pan_status} | Compliance: {it_rec.tax_compliance_status}"
                ),
                is_mock=True,
            ))
            items.append(EvidenceItem(
                bidder_id=b_id_str,
                evidence_type=EvidenceType.STATUTORY_REGISTRY,
                source_type=SourceType.INCOME_TAX,
                source_name="Income Tax Department (PAN/ITR)",
                field_name="tax_compliance_status",
                normalized_value=it_rec.tax_compliance_status,
                display_value=it_rec.tax_compliance_status,
                unit=None,
                status=it_rec.tax_compliance_status,
                confidence=1.0,
                page_number=None,
                source_record_id=it_rec.verification_id,
                provenance_reference=(
                    f"Income Tax Verification ID: {it_rec.verification_id} | "
                    f"Last ITR FY: {it_rec.last_itr_filed_fy} | Compliance: {it_rec.tax_compliance_status}"
                ),
                is_mock=True,
            ))

        # -------------------------------------------------------------------
        # 5. Make in India (MII) / Local Content
        # -------------------------------------------------------------------
        mii_query = select(MockMIIRecord)
        if resolved_id:
            mii_query = mii_query.where(MockMIIRecord.entity_identifier == resolved_id)
        else:
            mii_query = mii_query.where(MockMIIRecord.entity_identifier.ilike(f"%{clean_name}%"))

        mii_rec = (await db.execute(mii_query)).scalars().first()
        if mii_rec:
            items.append(EvidenceItem(
                bidder_id=b_id_str,
                evidence_type=EvidenceType.STATUTORY_REGISTRY,
                source_type=SourceType.MAKE_IN_INDIA,
                source_name="Make in India (MII) Statutory Verification",
                field_name="local_content_percent",
                normalized_value=round(float(mii_rec.verified_local_content), 1),
                display_value=f"{mii_rec.verified_local_content:.1f}%",
                unit="%",
                status=mii_rec.verification_status,
                confidence=1.0,
                page_number=None,
                source_record_id=mii_rec.verification_id,
                raw_reference={
                    "product_category": mii_rec.product_category,
                    "certifying_authority": mii_rec.certifying_authority,
                },
                provenance_reference=(
                    f"Make in India Verification ID: {mii_rec.verification_id} | "
                    f"Classification: {mii_rec.verification_status} | "
                    f"Authority: {mii_rec.certifying_authority} | Ref: {mii_rec.certificate_reference or 'N/A'}"
                ),
                is_mock=True,
            ))
            items.append(EvidenceItem(
                bidder_id=b_id_str,
                evidence_type=EvidenceType.STATUTORY_REGISTRY,
                source_type=SourceType.MAKE_IN_INDIA,
                source_name="Make in India (MII) Statutory Verification",
                field_name="mii_classification",
                normalized_value=mii_rec.verification_status,
                display_value=mii_rec.verification_status,
                unit=None,
                status=mii_rec.verification_status,
                confidence=1.0,
                page_number=None,
                source_record_id=mii_rec.verification_id,
                provenance_reference=f"MII Verification ID: {mii_rec.verification_id} | Classification: {mii_rec.verification_status}",
                is_mock=True,
            ))

        return items

    @classmethod
    def group_evidence_by_field(
        cls,
        items: List[EvidenceItem],
        bidder_id: str,
    ) -> Dict[str, FieldEvidenceGroup]:
        """Group evidence items by canonical field name while preserving distinct source identities."""
        groups: Dict[str, FieldEvidenceGroup] = {}

        for it in items:
            field = it.field_name
            if field not in groups:
                label = FIELD_LABELS.get(field, field.replace("_", " ").title())
                groups[field] = FieldEvidenceGroup(
                    bidder_id=str(bidder_id),
                    field_name=field,
                    field_label=label,
                    evidence=[],
                    source_count=0,
                    sources_present=[],
                )
            groups[field].evidence.append(it)

        # Update metadata counts for each group
        for field, grp in groups.items():
            grp.source_count = len(grp.evidence)
            distinct_sources = list(dict.fromkeys(e.source_type for e in grp.evidence))
            grp.sources_present = distinct_sources

        return groups

    @classmethod
    async def get_evidence_for_field(
        cls,
        bidder_id: Union[UUID, str],
        field_name: str,
        db: AsyncSession,
        bidder_company_name: Optional[str] = None,
        entity_identifier: Optional[str] = None,
    ) -> List[EvidenceItem]:
        """Retrieve all independent evidence items for a specific canonical field for a bidder."""
        profile = await cls.fuse_bidder_evidence(
            bidder_id=bidder_id,
            db=db,
            company_name_override=bidder_company_name,
            entity_identifier=entity_identifier,
        )
        group = profile.field_groups.get(field_name)
        return group.evidence if group else []

    @classmethod
    async def fuse_bidder_evidence(
        cls,
        bidder_id: Union[UUID, str],
        db: AsyncSession,
        tender_id: Optional[Union[UUID, str]] = None,
        company_name_override: Optional[str] = None,
        entity_identifier: Optional[str] = None,
    ) -> BidderEvidenceFusionProfile:
        """Construct the complete multi-source EvidenceFusionProfile for a bidder.

        Guarantees:
        - Bidder document claims and statutory registry records are collected and normalized.
        - Multiple sources for the same field remain separate (no overwriting).
        - Source identities, provenance, and mock disclaimers are preserved.
        - Bidder isolation is maintained.
        - Missing sources do not crash fusion.
        - Zero compliance scoring or contradiction decisions made in this step.
        """
        b_uuid = UUID(str(bidder_id))
        bidder_stmt = select(Bidder).where(Bidder.id == b_uuid)
        bidder = (await db.execute(bidder_stmt)).scalar_one_or_none()

        company_name = company_name_override or (bidder.company_name if bidder else f"Bidder-{str(bidder_id)[:8]}")
        t_id = str(tender_id or (bidder.tender_id if bidder else "")) or None

        resolved_identifier = cls.resolve_bidder_entity_identifier(company_name, entity_identifier)

        # 1. Collect bidder document evidence
        doc_evidence = await cls.collect_bidder_document_evidence(b_uuid, db)

        # 2. Collect mock statutory evidence
        stat_evidence = await cls.collect_mock_source_evidence(
            bidder_company_name=company_name,
            bidder_id=b_uuid,
            db=db,
            entity_identifier=resolved_identifier,
        )

        # Combine all evidence items
        all_items = doc_evidence + stat_evidence

        # Group by canonical field
        field_groups = cls.group_evidence_by_field(all_items, str(b_uuid))

        # Distinct source codes present
        sources_present = list(dict.fromkeys(e.source_type.value for e in all_items))

        return BidderEvidenceFusionProfile(
            bidder_id=str(b_uuid),
            company_name=company_name,
            tender_id=t_id,
            entity_identifier=resolved_identifier,
            field_groups=field_groups,
            total_evidence_items=len(all_items),
            sources_present=sources_present,
            disclaimer=MOCK_SOURCE_TYPE_LABEL,
        )
