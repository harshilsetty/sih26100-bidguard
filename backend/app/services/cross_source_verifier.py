"""Cross-Source Verifier Service.

Phase 6.3 Step 2 — SIH26100 Cross-Source Verification Layer.
Deterministically compares evidence items within a BidderEvidenceFusionProfile across
Bidder Documents and Mock Government Sources (GSTN, UDYAM, MCA, INCOME_TAX, MAKE_IN_INDIA).

CRITICAL ARCHITECTURAL CONSTRAINTS & MANDATORY CORRECTIONS:
1. Multi-Evidence Field Comparison (Correction #1):
   - A field may contain multiple evidence items (e.g. local content: declaration 50%, BOM 32%, MII 32%).
   - Produces ONE aggregated field-level result.
   - Preserves ALL evidence IDs and provenance citations.
   - Detailed discrepancy_details itemizes pairwise agreement/divergence without discarding agreeing evidence.
2. Udyam / MSE Semantics (Correction #2):
   - Verifies classification/evidence consistency only (e.g. Bidder MICRO vs Udyam MICRO = CONSISTENT).
   - DO NOT infer EMD exemption qualification inside the verifier.
3. Numeric Comparison (Correction #3):
   - Uses exact normalized numeric comparison.
   - NO arbitrary universal tolerance (no 0.01 tolerance; 8.00 != 7.99).
4. Determinism & Zero LLM:
   - Purely deterministic; NO external LLM/NIM calls.
   - Identifies whether evidence agrees or differs without asserting truth or authority.
5. No Disqualification:
   - Does NOT determine whether a bidder should win or lose.
   - Compliance decisions remain untouched.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timezone

from app.schemas.evidence_fusion import (
    SourceType,
    EvidenceItem,
    FieldEvidenceGroup,
    BidderEvidenceFusionProfile,
    MOCK_SOURCE_TYPE_LABEL,
)
from app.schemas.cross_source_verification import (
    CrossSourceStatus,
    DiscrepancyDetail,
    CrossSourceVerificationResult,
    BidderCrossSourceVerificationReport,
    MOCK_SOURCE_DISCLAIMER,
)

logger = logging.getLogger(__name__)

# Canonical numeric field names
NUMERIC_FIELDS = {
    "turnover",
    "local_content_percent",
    "cpu_cores",
    "warranty_years",
    "delivery_days",
    "emd_amount",
    "authorized_capital",
    "similar_contracts_count",
}

# Status fields
STATUS_FIELDS = {
    "gstin_status",
    "company_status",
    "pan_status",
    "tax_compliance_status",
    "udyam_status",
    "filing_status",
}

# Categorical fields
CATEGORICAL_FIELDS = {
    "enterprise_type",
    "mii_classification",
}

# Equivalent positive status terms
STATUS_EQUIVALENCE_MAP = {
    "ACTIVE": "ACTIVE",
    "VERIFIED": "ACTIVE",
    "COMPLIANT": "ACTIVE",
    "REGISTERED": "ACTIVE",
    "REGULAR": "ACTIVE",
    "VALID": "ACTIVE",
    "CANCELLED": "CANCELLED",
    "SUSPENDED": "SUSPENDED",
    "INACTIVE": "INACTIVE",
    "STRUCK_OFF": "STRUCK_OFF",
    "DEFAULTING": "NON_COMPLIANT",
    "NON_COMPLIANT": "NON_COMPLIANT",
}

# MSME enterprise scale normalizations
ENTERPRISE_SCALE_MAP = {
    "MICRO": "MICRO",
    "SMALL": "SMALL",
    "MEDIUM": "MEDIUM",
}

# MII classifications
MII_CLASS_MAP = {
    "CLASS_1": "CLASS_1",
    "CLASS_I": "CLASS_1",
    "CLASS_I_LOCAL_SUPPLIER": "CLASS_1",
    "VERIFIED_CLASS_I": "CLASS_1",
    "CLASS_2": "CLASS_2",
    "CLASS_II": "CLASS_2",
    "CLASS_II_LOCAL_SUPPLIER": "CLASS_2",
    "VERIFIED_CLASS_II": "CLASS_2",
    "NON_LOCAL": "NON_LOCAL",
    "NON_LOCAL_SUPPLIER": "NON_LOCAL",
}


def normalize_entity_name(name: str) -> str:
    """Normalize corporate names conservatively by removing punctuation, extra spaces, and common legal suffixes."""
    if not name:
        return ""
    # Lowercase
    s = name.strip().lower()
    # Remove parenthetical additions like "(Bidder A)"
    s = re.sub(r"\(.*?\)", "", s)
    # Remove punctuation
    s = re.sub(r"[^\w\s]", " ", s)
    # Standardize common legal suffixes
    legal_suffixes = [
        r"\bprivate\s+limited\b",
        r"\bpvt\s+ltd\b",
        r"\bpvt\s+limited\b",
        r"\bprivate\s+ltd\b",
        r"\blimited\b",
        r"\bltd\b",
        r"\bllp\b",
        r"\binc\b",
        r"\bcorp\b",
        r"\bcorporation\b",
        r"\bcompany\b",
        r"\bco\b",
    ]
    for suf in legal_suffixes:
        s = re.sub(suf, "", s)
    # Normalize whitespace
    s = " ".join(s.split())
    return s


class CrossSourceVerifier:
    """Deterministic, traceable Cross-Source Verification Engine."""

    @classmethod
    def compare_numeric_values(
        cls,
        val_a: Any,
        val_b: Any,
    ) -> Tuple[bool, bool]:
        """Compare two numeric values using exact normalized numeric comparison (Correction #3).
        
        Returns:
            (comparable, agrees)
        """
        try:
            num_a = float(val_a)
            num_b = float(val_b)
        except (ValueError, TypeError):
            return False, False

        # Exact numeric equality (no arbitrary tolerance)
        return True, num_a == num_b

    @classmethod
    def compare_status_values(
        cls,
        val_a: Any,
        val_b: Any,
    ) -> Tuple[bool, bool]:
        """Compare two status values according to status equivalence and known conflict semantics.
        
        Returns:
            (comparable, agrees)
        """
        if val_a is None or val_b is None:
            return False, False

        s_a = str(val_a).strip().upper().replace(" ", "_")
        s_b = str(val_b).strip().upper().replace(" ", "_")

        norm_a = STATUS_EQUIVALENCE_MAP.get(s_a, s_a)
        norm_b = STATUS_EQUIVALENCE_MAP.get(s_b, s_b)

        return True, norm_a == norm_b

    @classmethod
    def compare_categorical_values(
        cls,
        field_name: str,
        val_a: Any,
        val_b: Any,
    ) -> Tuple[bool, bool]:
        """Compare categorical fields (enterprise_type, mii_classification) conservatively.
        
        Correction #2: Compares classification consistency only; does NOT infer EMD exemption qualification.
        
        Returns:
            (comparable, agrees)
        """
        if val_a is None or val_b is None:
            return False, False

        s_a = str(val_a).strip().upper().replace(" ", "_")
        s_b = str(val_b).strip().upper().replace(" ", "_")

        if field_name == "enterprise_type":
            cat_a = ENTERPRISE_SCALE_MAP.get(s_a, s_a)
            cat_b = ENTERPRISE_SCALE_MAP.get(s_b, s_b)
            return True, cat_a == cat_b

        if field_name == "mii_classification":
            cat_a = MII_CLASS_MAP.get(s_a, s_a)
            cat_b = MII_CLASS_MAP.get(s_b, s_b)
            return True, cat_a == cat_b

        return True, s_a == s_b

    @classmethod
    def compare_entity_names(
        cls,
        name_a: str,
        name_b: str,
    ) -> Tuple[bool, bool]:
        """Compare two corporate / entity names with suffix normalization.
        
        Alpha Technologies Pvt Ltd vs Alpha Technologies Private Limited -> CONSISTENT.
        If normalization cannot establish clear identity, flags not comparable rather than false contradiction.
        
        Returns:
            (comparable, agrees)
        """
        norm_a = normalize_entity_name(name_a)
        norm_b = normalize_entity_name(name_b)

        if not norm_a or not norm_b:
            return False, False

        if norm_a == norm_b:
            return True, True

        # Check if one is a clean substring / prefix of another
        if norm_a in norm_b or norm_b in norm_a:
            # High lexical overlap
            return True, True

        return True, False

    @classmethod
    def compare_evidence_pair(
        cls,
        field_name: str,
        item_a: EvidenceItem,
        item_b: EvidenceItem,
    ) -> Tuple[bool, bool, str]:
        """Compare two atomic EvidenceItems for a specific field.
        
        Returns:
            (comparable, agrees, notes)
        """
        val_a = item_a.normalized_value
        val_b = item_b.normalized_value

        src_a_label = item_a.source_name or item_a.source_type.value
        src_b_label = item_b.source_name or item_b.source_type.value

        # Numeric field comparison
        if field_name in NUMERIC_FIELDS or (
            isinstance(val_a, (int, float)) and isinstance(val_b, (int, float))
        ):
            comp, agrees = cls.compare_numeric_values(val_a, val_b)
            if not comp:
                return False, False, f"Non-numeric values found in numeric field '{field_name}': {val_a} vs {val_b}"
            if agrees:
                notes = f"{src_a_label} ({item_a.display_value}) agrees with {src_b_label} ({item_b.display_value})"
            else:
                notes = f"{src_a_label} ({item_a.display_value}) differs from {src_b_label} ({item_b.display_value})"
            return comp, agrees, notes

        # Status field comparison
        if field_name in STATUS_FIELDS or "status" in field_name:
            # Fall back to item.status if normalized_value is None
            s_val_a = val_a if val_a is not None else item_a.status
            s_val_b = val_b if val_b is not None else item_b.status
            comp, agrees = cls.compare_status_values(s_val_a, s_val_b)
            if not comp:
                return False, False, f"Missing status values for comparison in field '{field_name}'"
            if agrees:
                notes = f"{src_a_label} status ({item_a.display_value}) matches {src_b_label} status ({item_b.display_value})"
            else:
                notes = f"{src_a_label} status ({item_a.display_value}) conflicts with {src_b_label} status ({item_b.display_value})"
            return comp, agrees, notes

        # Categorical field comparison
        if field_name in CATEGORICAL_FIELDS:
            comp, agrees = cls.compare_categorical_values(field_name, val_a, val_b)
            if not comp:
                return False, False, f"Missing categorical values for field '{field_name}'"
            if agrees:
                notes = f"{src_a_label} classification ({item_a.display_value}) is consistent with {src_b_label} ({item_b.display_value})"
            else:
                notes = f"{src_a_label} classification ({item_a.display_value}) differs from {src_b_label} ({item_b.display_value})"
            return comp, agrees, notes

        # Entity name comparison
        if "name" in field_name or "company" in field_name:
            comp, agrees = cls.compare_entity_names(str(val_a), str(val_b))
            if not comp:
                return False, False, f"Cannot compare entity names: '{val_a}' vs '{val_b}'"
            if agrees:
                notes = f"{src_a_label} name ('{item_a.display_value}') is equivalent to {src_b_label} ('{item_b.display_value}')"
            else:
                notes = f"{src_a_label} name ('{item_a.display_value}') differs from {src_b_label} ('{item_b.display_value}')"
            return comp, agrees, notes

        # Default fallback string comparison
        if val_a is not None and val_b is not None:
            s_a = str(val_a).strip().lower()
            s_b = str(val_b).strip().lower()
            agrees = (s_a == s_b)
            notes = (
                f"{src_a_label} ('{item_a.display_value}') matches {src_b_label} ('{item_b.display_value}')"
                if agrees
                else f"{src_a_label} ('{item_a.display_value}') differs from {src_b_label} ('{item_b.display_value}')"
            )
            return True, agrees, notes

        return False, False, f"Values not comparable in field '{field_name}'"

    @classmethod
    def verify_field_group(
        cls,
        field_group: FieldEvidenceGroup,
        bidder_id: str,
    ) -> CrossSourceVerificationResult:
        """Verify evidence items within a single FieldEvidenceGroup according to Correction #1.
        
        1. Preserves every evidence ID and provenance citation.
        2. Aggregates multi-evidence relationships into ONE field-level result.
        3. Details agreeing vs differing subgroups in discrepancy_details.
        4. Detects INCONSISTENT if any comparable pair disagrees.
        """
        evidence_list = field_group.evidence or []
        evidence_ids = [e.evidence_id for e in evidence_list]
        compared_sources = list(dict.fromkeys(e.source_type.value for e in evidence_list))
        provenance_refs = [e.provenance_reference for e in evidence_list]
        is_mock_involved = any(e.is_mock for e in evidence_list)

        normalized_values = [
            {
                "evidence_id": e.evidence_id,
                "source_type": e.source_type.value,
                "source_name": e.source_name,
                "normalized_value": e.normalized_value,
                "display_value": e.display_value,
                "unit": e.unit,
                "is_mock": e.is_mock,
            }
            for e in evidence_list
        ]

        # Case 1: Insufficient evidence (< 2 items)
        if len(evidence_list) < 2:
            single_val = evidence_list[0].display_value if evidence_list else "None"
            single_src = evidence_list[0].source_name if evidence_list else "None"
            return CrossSourceVerificationResult(
                bidder_id=str(bidder_id),
                field_name=field_group.field_name,
                field_label=field_group.field_label,
                status=CrossSourceStatus.INSUFFICIENT_EVIDENCE,
                evidence_ids=evidence_ids,
                compared_sources=compared_sources,
                normalized_values=normalized_values,
                explanation=(
                    f"Only one evidence source available ({single_src}: {single_val}). "
                    "Cross-source verification requires at least two independent evidence items."
                ),
                confidence=1.0,
                provenance_references=provenance_refs,
                is_mock_involved=is_mock_involved,
                discrepancy_details=[],
            )

        # Case 2: Multi-evidence comparison across all distinct pairs
        discrepancies: List[DiscrepancyDetail] = []
        any_inconsistent = False
        any_comparable = False
        agreeing_pairs: List[str] = []
        differing_pairs: List[str] = []

        n = len(evidence_list)
        for i in range(n):
            for j in range(i + 1, n):
                item_a = evidence_list[i]
                item_b = evidence_list[j]

                comp, agrees, note = cls.compare_evidence_pair(
                    field_group.field_name,
                    item_a,
                    item_b,
                )

                if comp:
                    any_comparable = True
                    src_a = item_a.source_name or item_a.source_type.value
                    src_b = item_b.source_name or item_b.source_type.value

                    detail = DiscrepancyDetail(
                        source_a=src_a,
                        evidence_id_a=item_a.evidence_id,
                        value_a=item_a.normalized_value,
                        display_value_a=item_a.display_value,
                        source_b=src_b,
                        evidence_id_b=item_b.evidence_id,
                        value_b=item_b.normalized_value,
                        display_value_b=item_b.display_value,
                        agrees=agrees,
                        notes=note,
                    )
                    discrepancies.append(detail)

                    if not agrees:
                        any_inconsistent = True
                        differing_pairs.append(
                            f"{src_a} ({item_a.display_value}) differs from {src_b} ({item_b.display_value})"
                        )
                    else:
                        agreeing_pairs.append(
                            f"{src_a} ({item_a.display_value}) agrees with {src_b} ({item_b.display_value})"
                        )

        # Determine aggregate status
        if not any_comparable:
            return CrossSourceVerificationResult(
                bidder_id=str(bidder_id),
                field_name=field_group.field_name,
                field_label=field_group.field_label,
                status=CrossSourceStatus.NOT_COMPARABLE,
                evidence_ids=evidence_ids,
                compared_sources=compared_sources,
                normalized_values=normalized_values,
                explanation=(
                    f"Evidence items across {len(evidence_list)} sources could not be reliably compared "
                    f"due to type or formatting divergence."
                ),
                confidence=0.5,
                provenance_references=provenance_refs,
                is_mock_involved=is_mock_involved,
                discrepancy_details=discrepancies,
            )

        if any_inconsistent:
            # Construct comprehensive explanation detailing conflicting and agreeing subgroups
            explanation_parts = [
                f"Discrepancy detected across {len(evidence_list)} evidence items."
            ]
            if differing_pairs:
                explanation_parts.append(f"Differences: {'; '.join(differing_pairs)}.")
            if agreeing_pairs:
                explanation_parts.append(f"Consistent relationships: {'; '.join(agreeing_pairs)}.")

            return CrossSourceVerificationResult(
                bidder_id=str(bidder_id),
                field_name=field_group.field_name,
                field_label=field_group.field_label,
                status=CrossSourceStatus.INCONSISTENT,
                evidence_ids=evidence_ids,
                compared_sources=compared_sources,
                normalized_values=normalized_values,
                explanation=" ".join(explanation_parts),
                confidence=1.0,  # High confidence that the normalized values differ
                provenance_references=provenance_refs,
                is_mock_involved=is_mock_involved,
                discrepancy_details=discrepancies,
            )

        # All comparable pairs agree
        explanation = (
            f"All {len(evidence_list)} evidence items from {len(compared_sources)} sources are consistent "
            f"({', '.join(e.display_value for e in evidence_list[:2])})."
        )
        return CrossSourceVerificationResult(
            bidder_id=str(bidder_id),
            field_name=field_group.field_name,
            field_label=field_group.field_label,
            status=CrossSourceStatus.CONSISTENT,
            evidence_ids=evidence_ids,
            compared_sources=compared_sources,
            normalized_values=normalized_values,
            explanation=explanation,
            confidence=1.0,
            provenance_references=provenance_refs,
            is_mock_involved=is_mock_involved,
            discrepancy_details=discrepancies,
        )

    @classmethod
    def verify_profile(
        cls,
        profile: BidderEvidenceFusionProfile,
    ) -> BidderCrossSourceVerificationReport:
        """Run deterministic cross-source verification across all field groups in an EvidenceFusionProfile."""
        results: List[CrossSourceVerificationResult] = []

        consistent_count = 0
        inconsistent_count = 0
        insufficient_count = 0
        not_comparable_count = 0
        overall_mock_involved = False

        for field_name, group in profile.field_groups.items():
            res = cls.verify_field_group(group, bidder_id=profile.bidder_id)
            results.append(res)

            if res.status == CrossSourceStatus.CONSISTENT:
                consistent_count += 1
            elif res.status == CrossSourceStatus.INCONSISTENT:
                inconsistent_count += 1
            elif res.status == CrossSourceStatus.INSUFFICIENT_EVIDENCE:
                insufficient_count += 1
            elif res.status == CrossSourceStatus.NOT_COMPARABLE:
                not_comparable_count += 1

            if res.is_mock_involved:
                overall_mock_involved = True

        return BidderCrossSourceVerificationReport(
            bidder_id=str(profile.bidder_id),
            company_name=profile.company_name,
            tender_id=profile.tender_id,
            entity_identifier=profile.entity_identifier,
            results=results,
            total_fields_verified=len(results),
            consistent_count=consistent_count,
            inconsistent_count=inconsistent_count,
            insufficient_evidence_count=insufficient_count,
            not_comparable_count=not_comparable_count,
            is_mock_involved=overall_mock_involved,
            disclaimer=MOCK_SOURCE_DISCLAIMER,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
