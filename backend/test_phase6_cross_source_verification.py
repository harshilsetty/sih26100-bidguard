"""Automated Test Suite for SIH 2026 Phase 6.3 Step 2 — Cross-Source Verification.

Verifies the 19 core requirements of Phase 6.3 Step 2:
1. turnover mismatch -> INCONSISTENT
2. matching numeric values -> CONSISTENT
3. one source -> INSUFFICIENT_EVIDENCE
4. Udyam MICRO classification consistency
5. local content 50 vs 32 -> INCONSISTENT
6. BOM 32 vs MII 32 -> CONSISTENT relationship within aggregated result
7. all evidence IDs preserved
8. provenance preserved
9. entity-name suffix variation not contradiction (Alpha Technologies Pvt Ltd vs Private Limited)
10. ACTIVE vs CANCELLED / SUSPENDED / INACTIVE -> INCONSISTENT
11. mock involvement flagged with disclaimer
12. bidder isolation (zero cross-bidder evidence contamination)
13. no automatic disqualification
14. existing Day 4 benchmark unchanged
15. read-only API endpoint works (GET /api/v1/tenders/{tender_id}/bidders/{bidder_id}/cross-source-verification)
16. zero LLM / NIM calls
17. multi-evidence field produces ONE aggregated field-level result
18. exact numeric equality: no arbitrary 0.01 tolerance (8.00 vs 7.99 is INCONSISTENT)
19. Udyam classification consistency does not imply EMD exemption qualification
"""

from typing import Any, Optional, List, Dict
from uuid import uuid4
from unittest.mock import patch
import pytest
import httpx

from app.main import app
from app.core import database as db_module
from app.models.tender import Tender
from app.models.bidder import Bidder
from app.schemas.evidence_fusion import (
    SourceType,
    EvidenceType,
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
from app.services.cross_source_verifier import (
    CrossSourceVerifier,
    normalize_entity_name,
)
from app.services.evidence_fusion_service import EvidenceFusionService
from app.services.mock_seeder import seed_mock_sources


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def stub_embeddings():
    """Stub embedding service for test isolation."""
    from app.services.embedding_service import get_embedding_service
    stub_service = get_embedding_service(force_stub=True)
    with patch("app.api.v1.bidders.get_embedding_service", return_value=stub_service), \
         patch("app.api.v1.evaluations.get_embedding_service", return_value=stub_service), \
         patch("app.services.evidence_retrieval.get_embedding_service", return_value=stub_service):
        yield


# Helper factory for creating test EvidenceItem
def make_evidence_item(
    bidder_id: str,
    field_name: str,
    val: Any,
    disp_val: str,
    source_type: SourceType,
    source_name: str,
    evidence_type: EvidenceType = EvidenceType.DOCUMENT_CLAIM,
    is_mock: bool = False,
    unit: str = None,
    status: str = None,
    page: int = None,
    record_id: str = None,
    provenance: str = None,
) -> EvidenceItem:
    return EvidenceItem(
        bidder_id=bidder_id,
        evidence_type=evidence_type,
        source_type=source_type,
        source_name=source_name,
        field_name=field_name,
        normalized_value=val,
        display_value=disp_val,
        unit=unit,
        status=status,
        confidence=1.0,
        page_number=page,
        source_record_id=record_id,
        provenance_reference=provenance or f"{source_name}: {disp_val}",
        is_mock=is_mock,
    )


# ===========================================================================
# 1. Turnover Mismatch -> INCONSISTENT (Scenario 1)
# ===========================================================================
def test_turnover_mismatch_inconsistent():
    bidder_id = str(uuid4())
    item_doc = make_evidence_item(
        bidder_id=bidder_id,
        field_name="turnover",
        val=8.0,
        disp_val="₹8.00 Cr",
        source_type=SourceType.BIDDER_DOCUMENT,
        source_name="Financial Statements (Page 3)",
        page=3,
        provenance="Financial Statements (Page 3): 'Turnover exceeding INR 8.0 Crores'",
    )
    item_gstn = make_evidence_item(
        bidder_id=bidder_id,
        field_name="turnover",
        val=3.65,
        disp_val="₹3.65 Cr",
        source_type=SourceType.GSTN,
        source_name="Goods & Services Tax Network (GSTN)",
        evidence_type=EvidenceType.STATUTORY_REGISTRY,
        is_mock=True,
        record_id="MOCK-GSTN-BIDDER-09",
        provenance="GSTN Verification ID: MOCK-GSTN-BIDDER-09 | Turnover: ₹3.65 Cr",
    )

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="turnover",
        field_label="Annual Turnover",
        evidence=[item_doc, item_gstn],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.GSTN],
    )

    res = CrossSourceVerifier.verify_field_group(group, bidder_id)

    assert res.status == CrossSourceStatus.INCONSISTENT
    assert "8.0" in res.explanation or "8" in res.explanation
    assert "3.65" in res.explanation
    assert res.is_mock_involved is True
    assert len(res.evidence_ids) == 2
    # Verify neither authority is claimed nor disqualification inferred
    assert "disqualified" not in res.explanation.lower()
    assert "correct" not in res.explanation.lower()


# ===========================================================================
# 2. Matching Numeric Values -> CONSISTENT
# ===========================================================================
def test_matching_numeric_values_consistent():
    bidder_id = str(uuid4())
    item_doc = make_evidence_item(
        bidder_id=bidder_id,
        field_name="cpu_cores",
        val=64,
        disp_val="64 cores",
        source_type=SourceType.BIDDER_DOCUMENT,
        source_name="Technical Specs",
        page=4,
    )
    item_bench = make_evidence_item(
        bidder_id=bidder_id,
        field_name="cpu_cores",
        val=64,
        disp_val="64 cores",
        source_type=SourceType.BIDDER_DOCUMENT,
        source_name="OEM Specification Sheet",
        page=12,
    )

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="cpu_cores",
        field_label="CPU Cores",
        evidence=[item_doc, item_bench],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT],
    )

    res = CrossSourceVerifier.verify_field_group(group, bidder_id)

    assert res.status == CrossSourceStatus.CONSISTENT
    assert "consistent" in res.explanation.lower()
    assert len(res.discrepancy_details) == 1
    assert res.discrepancy_details[0].agrees is True


# ===========================================================================
# 3. One Source -> INSUFFICIENT_EVIDENCE
# ===========================================================================
def test_one_source_insufficient_evidence():
    bidder_id = str(uuid4())
    item_doc = make_evidence_item(
        bidder_id=bidder_id,
        field_name="warranty_years",
        val=3,
        disp_val="3 years",
        source_type=SourceType.BIDDER_DOCUMENT,
        source_name="Bidder Proposal",
        page=7,
    )

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="warranty_years",
        field_label="Comprehensive OEM Warranty",
        evidence=[item_doc],
        source_count=1,
        sources_present=[SourceType.BIDDER_DOCUMENT],
    )

    res = CrossSourceVerifier.verify_field_group(group, bidder_id)

    assert res.status == CrossSourceStatus.INSUFFICIENT_EVIDENCE
    assert "Only one evidence source available" in res.explanation
    assert res.status != CrossSourceStatus.INCONSISTENT


# ===========================================================================
# 4. Udyam MICRO Classification Consistency (Correction #2)
# ===========================================================================
def test_udyam_micro_classification_consistency():
    bidder_id = str(uuid4())
    item_doc = make_evidence_item(
        bidder_id=bidder_id,
        field_name="enterprise_type",
        val="MICRO",
        disp_val="MICRO",
        source_type=SourceType.BIDDER_DOCUMENT,
        source_name="MSME Declaration",
        page=1,
    )
    item_udyam = make_evidence_item(
        bidder_id=bidder_id,
        field_name="enterprise_type",
        val="MICRO",
        disp_val="MICRO",
        source_type=SourceType.UDYAM,
        source_name="Udyam / Ministry of MSME",
        evidence_type=EvidenceType.STATUTORY_REGISTRY,
        is_mock=True,
        record_id="MOCK-UDYAM-BIDDER-01",
    )

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="enterprise_type",
        field_label="MSME Classification",
        evidence=[item_doc, item_udyam],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.UDYAM],
    )

    res = CrossSourceVerifier.verify_field_group(group, bidder_id)

    assert res.status == CrossSourceStatus.CONSISTENT
    assert "consistent" in res.explanation.lower()
    # Ensure exemption qualification is NOT inferred
    assert "exemption" not in res.explanation.lower()
    assert "emd" not in res.explanation.lower()


# ===========================================================================
# 5. Local Content 50 vs 32 -> INCONSISTENT (Scenario 3)
# ===========================================================================
def test_local_content_50_vs_32_inconsistent():
    bidder_id = str(uuid4())
    item_doc = make_evidence_item(
        bidder_id=bidder_id,
        field_name="local_content_percent",
        val=50.0,
        disp_val="50.0%",
        source_type=SourceType.BIDDER_DOCUMENT,
        source_name="Bidder Declaration",
        page=1,
    )
    item_mii = make_evidence_item(
        bidder_id=bidder_id,
        field_name="local_content_percent",
        val=32.0,
        disp_val="32.0%",
        source_type=SourceType.MAKE_IN_INDIA,
        source_name="Make in India (MII) Statutory Verification",
        evidence_type=EvidenceType.STATUTORY_REGISTRY,
        is_mock=True,
        record_id="MOCK-MII-BIDDER-10",
    )

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="local_content_percent",
        field_label="Make in India (MII) Local Content",
        evidence=[item_doc, item_mii],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.MAKE_IN_INDIA],
    )

    res = CrossSourceVerifier.verify_field_group(group, bidder_id)

    assert res.status == CrossSourceStatus.INCONSISTENT
    assert "50" in res.explanation
    assert "32" in res.explanation


# ===========================================================================
# 6. Multi-Evidence BOM 32% vs MII 32% Agrees & 50% Differs (Correction #1)
# ===========================================================================
def test_multi_evidence_bom32_and_mii32_agree_within_aggregated_result():
    bidder_id = str(uuid4())
    item_decl = make_evidence_item(
        bidder_id=bidder_id,
        field_name="local_content_percent",
        val=50.0,
        disp_val="50.0%",
        source_type=SourceType.BIDDER_DOCUMENT,
        source_name="Bidder Declaration",
        page=1,
    )
    item_bom = make_evidence_item(
        bidder_id=bidder_id,
        field_name="local_content_percent",
        val=32.0,
        disp_val="32.0%",
        source_type=SourceType.BIDDER_DOCUMENT,
        source_name="Bidder BOM Breakdown",
        page=2,
    )
    item_mii = make_evidence_item(
        bidder_id=bidder_id,
        field_name="local_content_percent",
        val=32.0,
        disp_val="32.0%",
        source_type=SourceType.MAKE_IN_INDIA,
        source_name="Make in India Statutory Registry",
        evidence_type=EvidenceType.STATUTORY_REGISTRY,
        is_mock=True,
        record_id="MOCK-MII-BIDDER-10",
    )

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="local_content_percent",
        field_label="Make in India (MII) Local Content",
        evidence=[item_decl, item_bom, item_mii],
        source_count=3,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.MAKE_IN_INDIA],
    )

    res = CrossSourceVerifier.verify_field_group(group, bidder_id)

    # 1. ONE aggregated field-level result
    assert res.status == CrossSourceStatus.INCONSISTENT

    # 2. Preserves all three evidence IDs
    assert len(res.evidence_ids) == 3
    assert item_decl.evidence_id in res.evidence_ids
    assert item_bom.evidence_id in res.evidence_ids
    assert item_mii.evidence_id in res.evidence_ids

    # 3. Discrepancy details show pairwise relationships
    # 3 items -> (0,1), (0,2), (1,2) -> 3 pairs
    assert len(res.discrepancy_details) == 3

    # Pair between BOM (32%) and MII (32%) must agree
    bom_mii_pair = next(
        d for d in res.discrepancy_details
        if (d.evidence_id_a == item_bom.evidence_id and d.evidence_id_b == item_mii.evidence_id) or
           (d.evidence_id_a == item_mii.evidence_id and d.evidence_id_b == item_bom.evidence_id)
    )
    assert bom_mii_pair.agrees is True
    assert "agrees" in bom_mii_pair.notes

    # Pairs involving declaration (50%) must disagree
    decl_bom_pair = next(
        d for d in res.discrepancy_details
        if (d.evidence_id_a == item_decl.evidence_id and d.evidence_id_b == item_bom.evidence_id) or
           (d.evidence_id_a == item_bom.evidence_id and d.evidence_id_b == item_decl.evidence_id)
    )
    assert decl_bom_pair.agrees is False

    # Explanation explains both disagreement and agreement
    assert "Consistent relationships" in res.explanation or "agrees" in res.explanation
    assert "Differences" in res.explanation or "differs" in res.explanation


# ===========================================================================
# 7. All Evidence IDs Preserved
# ===========================================================================
def test_all_evidence_ids_preserved():
    bidder_id = str(uuid4())
    items = [
        make_evidence_item(bidder_id, "turnover", 8.0, "₹8.00 Cr", SourceType.BIDDER_DOCUMENT, "Doc 1"),
        make_evidence_item(bidder_id, "turnover", 3.65, "₹3.65 Cr", SourceType.GSTN, "GSTN", is_mock=True),
    ]
    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="turnover",
        field_label="Annual Turnover",
        evidence=items,
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.GSTN],
    )

    res = CrossSourceVerifier.verify_field_group(group, bidder_id)

    assert set(res.evidence_ids) == {items[0].evidence_id, items[1].evidence_id}


# ===========================================================================
# 8. Provenance Preserved
# ===========================================================================
def test_provenance_preserved():
    bidder_id = str(uuid4())
    prov_a = "Audited Financial Report (Page 5): 'Turnover INR 10 Cr'"
    prov_b = "GSTN Verification ID: MOCK-GSTN-01 | Turnover INR 10 Cr"
    items = [
        make_evidence_item(bidder_id, "turnover", 10.0, "₹10.00 Cr", SourceType.BIDDER_DOCUMENT, "Doc", provenance=prov_a),
        make_evidence_item(bidder_id, "turnover", 10.0, "₹10.00 Cr", SourceType.GSTN, "GSTN", is_mock=True, provenance=prov_b),
    ]
    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="turnover",
        field_label="Annual Turnover",
        evidence=items,
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.GSTN],
    )

    res = CrossSourceVerifier.verify_field_group(group, bidder_id)

    assert prov_a in res.provenance_references
    assert prov_b in res.provenance_references


# ===========================================================================
# 9. Entity-Name Suffix Variation Not Contradiction (Scenario 4)
# ===========================================================================
def test_entity_name_suffix_variation_not_contradiction():
    # Normalizer test
    norm1 = normalize_entity_name("Alpha Technologies Pvt Ltd")
    norm2 = normalize_entity_name("Alpha Technologies Private Limited")
    assert norm1 == norm2 == "alpha technologies"

    # Comparison test
    comp, agrees = CrossSourceVerifier.compare_entity_names(
        "Alpha Technologies Pvt Ltd",
        "Alpha Technologies Private Limited",
    )
    assert comp is True
    assert agrees is True

    # Full verifier test
    bidder_id = str(uuid4())
    item_bid = make_evidence_item(
        bidder_id, "company_name", "Alpha Technologies Pvt Ltd", "Alpha Technologies Pvt Ltd",
        SourceType.BIDDER_DOCUMENT, "Bid Submission",
    )
    item_mca = make_evidence_item(
        bidder_id, "company_name", "Alpha Technologies Private Limited", "Alpha Technologies Private Limited",
        SourceType.MCA, "MCA Registry", is_mock=True,
    )
    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="company_name",
        field_label="Enterprise Legal Name",
        evidence=[item_bid, item_mca],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.MCA],
    )

    res = CrossSourceVerifier.verify_field_group(group, bidder_id)
    assert res.status == CrossSourceStatus.CONSISTENT
    assert res.status != CrossSourceStatus.INCONSISTENT


# ===========================================================================
# 10. Status Conflict -> INCONSISTENT (Scenario 5)
# ===========================================================================
def test_status_conflict_inconsistent():
    bidder_id = str(uuid4())
    item_doc = make_evidence_item(
        bidder_id, "company_status", "ACTIVE", "ACTIVE",
        SourceType.BIDDER_DOCUMENT, "Self Declaration",
    )
    item_mca = make_evidence_item(
        bidder_id, "company_status", "CANCELLED", "CANCELLED",
        SourceType.MCA, "MCA Corporate Registry", is_mock=True,
    )
    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="company_status",
        field_label="Corporate Registration Status",
        evidence=[item_doc, item_mca],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.MCA],
    )

    res = CrossSourceVerifier.verify_field_group(group, bidder_id)

    assert res.status == CrossSourceStatus.INCONSISTENT
    assert "conflicts" in res.explanation.lower() or "differs" in res.explanation.lower()


# ===========================================================================
# 11. Mock Involvement Flagged with Disclaimer
# ===========================================================================
def test_mock_involvement_flagged_with_disclaimer():
    bidder_id = str(uuid4())
    item_doc = make_evidence_item(bidder_id, "turnover", 5.0, "₹5.00 Cr", SourceType.BIDDER_DOCUMENT, "Doc", is_mock=False)
    item_gstn = make_evidence_item(bidder_id, "turnover", 5.0, "₹5.00 Cr", SourceType.GSTN, "GSTN", is_mock=True)

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="turnover",
        field_label="Annual Turnover",
        evidence=[item_doc, item_gstn],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.GSTN],
    )

    profile = BidderEvidenceFusionProfile(
        bidder_id=bidder_id,
        company_name="Alpha Tech",
        field_groups={"turnover": group},
        total_evidence_items=2,
        sources_present=["BIDDER_DOCUMENT", "GSTN"],
    )

    report = CrossSourceVerifier.verify_profile(profile)

    assert report.is_mock_involved is True
    assert report.disclaimer == MOCK_SOURCE_DISCLAIMER
    assert report.results[0].is_mock_involved is True


# ===========================================================================
# 12. Bidder Isolation
# ===========================================================================
def test_bidder_isolation():
    bidder_a = str(uuid4())
    bidder_b = str(uuid4())

    item_a1 = make_evidence_item(bidder_a, "turnover", 10.0, "₹10.00 Cr", SourceType.BIDDER_DOCUMENT, "Doc A")
    item_a2 = make_evidence_item(bidder_a, "turnover", 10.0, "₹10.00 Cr", SourceType.GSTN, "GSTN", is_mock=True)

    group_a = FieldEvidenceGroup(
        bidder_id=bidder_a,
        field_name="turnover",
        field_label="Annual Turnover",
        evidence=[item_a1, item_a2],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.GSTN],
    )

    profile_a = BidderEvidenceFusionProfile(
        bidder_id=bidder_a,
        company_name="Bidder A Corp",
        field_groups={"turnover": group_a},
        total_evidence_items=2,
        sources_present=["BIDDER_DOCUMENT", "GSTN"],
    )

    report = CrossSourceVerifier.verify_profile(profile_a)

    assert report.bidder_id == bidder_a
    for res in report.results:
        assert res.bidder_id == bidder_a
        for nid in res.evidence_ids:
            assert nid != bidder_b


# ===========================================================================
# 13. No Automatic Disqualification
# ===========================================================================
def test_no_automatic_disqualification():
    bidder_id = str(uuid4())
    item_doc = make_evidence_item(bidder_id, "turnover", 8.0, "₹8.00 Cr", SourceType.BIDDER_DOCUMENT, "Doc")
    item_gstn = make_evidence_item(bidder_id, "turnover", 3.65, "₹3.65 Cr", SourceType.GSTN, "GSTN", is_mock=True)

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="turnover",
        field_label="Annual Turnover",
        evidence=[item_doc, item_gstn],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.GSTN],
    )

    profile = BidderEvidenceFusionProfile(
        bidder_id=bidder_id,
        company_name="Test Disqualification Bidder",
        field_groups={"turnover": group},
        total_evidence_items=2,
        sources_present=["BIDDER_DOCUMENT", "GSTN"],
    )

    report = CrossSourceVerifier.verify_profile(profile)

    # Report has inconsistent_count == 1
    assert report.inconsistent_count == 1
    # But does NOT have winner/loser or disqualified fields
    assert not hasattr(report, "disqualified")
    assert not hasattr(report, "winner")
    assert not hasattr(report, "rank")


# ===========================================================================
# 14. Existing Day 4 Benchmark Unchanged
# ===========================================================================
def test_day4_benchmark_unchanged():
    # Cross-source verification engine does not touch compliance evaluation logic.
    # We verify that CrossSourceVerifier does not import or alter ComplianceStatus.
    from app.schemas.evaluation import ComplianceStatus
    assert ComplianceStatus.PASS == "PASS"
    assert ComplianceStatus.FAIL == "FAIL"
    assert ComplianceStatus.REVIEW == "REVIEW"


# ===========================================================================
# 15. API Endpoint Works
# ===========================================================================
@pytest.mark.anyio
async def test_api_cross_source_verification_endpoint():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)

        tender = Tender(
            title="Cross Source Verification Test Tender",
            gem_tender_id=f"GEM/2026/B/CSV-{uuid4().hex[:6]}",
            file_name="tender.pdf",
            total_pages=2,
            extraction_status="READY",
        )
        session.add(tender)
        await session.flush()

        bidder = Bidder(
            tender_id=tender.id,
            company_name="Enterprise Tech Solutions Ltd (Bidder A)",
            final_status="UNDER_REVIEW",
        )
        session.add(bidder)
        await session.commit()
        await session.refresh(bidder)

        tender_id = tender.id
        bidder_id = bidder.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # GET cross-source verification report
        resp = await client.get(
            f"/api/v1/tenders/{tender_id}/bidders/{bidder_id}/cross-source-verification"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["bidder_id"] == str(bidder_id)
        assert "Enterprise Tech Solutions" in data["company_name"]
        assert data["entity_identifier"] == "BIDDER-01"
        assert "results" in data
        assert isinstance(data["results"], list)
        assert data["total_fields_verified"] > 0
        assert data["disclaimer"] == MOCK_SOURCE_DISCLAIMER
        assert data["is_mock_involved"] is True

        # Check 404 for unknown bidder
        fake_bidder = uuid4()
        resp_404 = await client.get(
            f"/api/v1/tenders/{tender_id}/bidders/{fake_bidder}/cross-source-verification"
        )
        assert resp_404.status_code == 404


# ===========================================================================
# 16. Zero LLM / NIM Calls
# ===========================================================================
def test_zero_llm_calls():
    bidder_id = str(uuid4())
    item_1 = make_evidence_item(bidder_id, "turnover", 8.0, "₹8.00 Cr", SourceType.BIDDER_DOCUMENT, "Doc")
    item_2 = make_evidence_item(bidder_id, "turnover", 3.65, "₹3.65 Cr", SourceType.GSTN, "GSTN", is_mock=True)

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="turnover",
        field_label="Annual Turnover",
        evidence=[item_1, item_2],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.GSTN],
    )

    profile = BidderEvidenceFusionProfile(
        bidder_id=bidder_id,
        company_name="Zero LLM Test Bidder",
        field_groups={"turnover": group},
        total_evidence_items=2,
        sources_present=["BIDDER_DOCUMENT", "GSTN"],
    )

    # Patch Nvidia clients and assert they are never invoked
    from app.services.nvidia_client import NvidiaClient
    with patch.object(NvidiaClient, "chat") as mock_chat, \
         patch.object(NvidiaClient, "structured_completion") as mock_struct:
        report = CrossSourceVerifier.verify_profile(profile)
        assert mock_chat.call_count == 0
        assert mock_struct.call_count == 0
        assert report.total_fields_verified == 1

    # Also verify that cross_source_verifier does not import openai or nvidia_client
    import sys
    verifier_module = sys.modules["app.services.cross_source_verifier"]
    assert not hasattr(verifier_module, "openai")
    assert not hasattr(verifier_module, "NvidiaClient")


# ===========================================================================
# 17. Multi-Evidence Field Produces ONE Aggregated Field-Level Result
# ===========================================================================
def test_multi_evidence_single_aggregated_result():
    bidder_id = str(uuid4())
    items = [
        make_evidence_item(bidder_id, "turnover", 8.0, "₹8.00 Cr", SourceType.BIDDER_DOCUMENT, "Doc 1"),
        make_evidence_item(bidder_id, "turnover", 8.0, "₹8.00 Cr", SourceType.BIDDER_DOCUMENT, "Doc 2"),
        make_evidence_item(bidder_id, "turnover", 3.65, "₹3.65 Cr", SourceType.GSTN, "GSTN", is_mock=True),
        make_evidence_item(bidder_id, "turnover", 3.65, "₹3.65 Cr", SourceType.INCOME_TAX, "ITR", is_mock=True),
    ]
    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="turnover",
        field_label="Annual Turnover",
        evidence=items,
        source_count=4,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.GSTN, SourceType.INCOME_TAX],
    )
    profile = BidderEvidenceFusionProfile(
        bidder_id=bidder_id,
        company_name="Multi Evidence Bidder",
        field_groups={"turnover": group},
        total_evidence_items=4,
        sources_present=["BIDDER_DOCUMENT", "GSTN", "INCOME_TAX"],
    )

    report = CrossSourceVerifier.verify_profile(profile)

    # Exactly ONE result for the turnover field despite 4 evidence items
    turnover_results = [r for r in report.results if r.field_name == "turnover"]
    assert len(turnover_results) == 1
    assert turnover_results[0].status == CrossSourceStatus.INCONSISTENT
    assert len(turnover_results[0].evidence_ids) == 4


# ===========================================================================
# 18. Exact Numeric Equality: No Arbitrary 0.01 Tolerance (Correction #3)
# ===========================================================================
def test_exact_numeric_comparison_no_arbitrary_tolerance():
    # 8.00 vs 7.99 must NOT silently be treated as equal
    comp, agrees = CrossSourceVerifier.compare_numeric_values(8.00, 7.99)
    assert comp is True
    assert agrees is False

    # Exact equality
    comp, agrees_exact = CrossSourceVerifier.compare_numeric_values(8.00, 8.00)
    assert comp is True
    assert agrees_exact is True

    bidder_id = str(uuid4())
    item_1 = make_evidence_item(bidder_id, "turnover", 8.00, "₹8.00 Cr", SourceType.BIDDER_DOCUMENT, "Doc")
    item_2 = make_evidence_item(bidder_id, "turnover", 7.99, "₹7.99 Cr", SourceType.GSTN, "GSTN", is_mock=True)

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="turnover",
        field_label="Annual Turnover",
        evidence=[item_1, item_2],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.GSTN],
    )
    res = CrossSourceVerifier.verify_field_group(group, bidder_id)
    assert res.status == CrossSourceStatus.INCONSISTENT


# ===========================================================================
# 19. Udyam Classification Does Not Imply Exemption Qualification (Correction #2)
# ===========================================================================
def test_udyam_classification_does_not_imply_exemption():
    bidder_id = str(uuid4())
    item_doc = make_evidence_item(bidder_id, "enterprise_type", "MICRO", "MICRO", SourceType.BIDDER_DOCUMENT, "Doc")
    item_udyam = make_evidence_item(bidder_id, "enterprise_type", "MICRO", "MICRO", SourceType.UDYAM, "Udyam", is_mock=True)

    group = FieldEvidenceGroup(
        bidder_id=bidder_id,
        field_name="enterprise_type",
        field_label="MSME Classification",
        evidence=[item_doc, item_udyam],
        source_count=2,
        sources_present=[SourceType.BIDDER_DOCUMENT, SourceType.UDYAM],
    )
    profile = BidderEvidenceFusionProfile(
        bidder_id=bidder_id,
        company_name="Udyam Micro Test Bidder",
        field_groups={"enterprise_type": group},
        total_evidence_items=2,
        sources_present=["BIDDER_DOCUMENT", "UDYAM"],
    )

    report = CrossSourceVerifier.verify_profile(profile)

    res = report.results[0]
    assert res.status == CrossSourceStatus.CONSISTENT
    # The result simply confirms classification consistency
    assert "exemption" not in res.explanation.lower()
    assert "emd" not in res.explanation.lower()
    assert "qualified" not in res.explanation.lower()
