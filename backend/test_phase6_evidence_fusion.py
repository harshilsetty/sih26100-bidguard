"""Automated Test Suite for SIH 2026 Phase 6.3 — Evidence Fusion Foundation.

Verifies the 12 core requirements of Phase 6.3 Step 1:
1. Bidder-document evidence representation.
2. GSTN evidence representation.
3. Udyam evidence representation.
4. MCA evidence representation.
5. Income Tax evidence representation.
6. Make in India (MII) evidence representation.
7. Multiple sources for the same field remain independently separate.
8. Provenance preservation (document page/quotes vs statutory audit IDs).
9. Strict bidder isolation (zero cross-bidder data leakage).
10. Missing source resilience (graceful handling of partial/absent records).
11. Clear distinguishability between mock statutory records and bidder documents.
12. Read-only API endpoint (/api/v1/tenders/{tender_id}/bidders/{bidder_id}/evidence-fusion).
"""

from uuid import uuid4
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
    MOCK_SOURCE_TYPE_LABEL,
)
from app.schemas.evaluation import ParameterClaim
from app.services.evidence_fusion_service import (
    EvidenceFusionService,
)
from app.services.mock_seeder import seed_mock_sources


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def stub_embeddings():
    """Stub embedding service for test safety."""
    from unittest.mock import patch
    from app.services.embedding_service import get_embedding_service
    stub_service = get_embedding_service(force_stub=True)
    with patch("app.api.v1.bidders.get_embedding_service", return_value=stub_service), \
         patch("app.api.v1.evaluations.get_embedding_service", return_value=stub_service), \
         patch("app.services.evidence_retrieval.get_embedding_service", return_value=stub_service):
        yield


# ===========================================================================
# 1. Bidder-Document Evidence Representation
# ===========================================================================
def test_bidder_document_evidence_representation():
    bidder_id = str(uuid4())
    claim = ParameterClaim(
        parameter="turnover",
        value=8.0,
        unit="Crores",
        document="Bidder_C_Financials.pdf",
        page=3,
        chunk_id="chk-fin-003",
        quote="Management self-attestation claims annual business turnover exceeding INR 8.0 Crores.",
    )

    item = EvidenceFusionService.adapt_parameter_claim(claim, bidder_id=bidder_id)

    assert item.bidder_id == bidder_id
    assert item.evidence_type == EvidenceType.DOCUMENT_CLAIM
    assert item.source_type == SourceType.BIDDER_DOCUMENT
    assert item.source_name == "Bidder_C_Financials.pdf"
    assert item.field_name == "turnover"
    assert item.normalized_value == 8.0
    assert item.unit == "CR"
    assert "8.00 Cr" in item.display_value
    assert item.page_number == 3
    assert item.source_record_id == "chk-fin-003"
    assert item.is_mock is False
    assert "Page 3" in item.provenance_reference
    assert "8.0 Crores" in item.provenance_reference


# ===========================================================================
# 2. GSTN Evidence Representation
# ===========================================================================
@pytest.mark.anyio
async def test_gstn_evidence_representation():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)
        items = await EvidenceFusionService.collect_mock_source_evidence(
            bidder_company_name="Enterprise Tech Solutions Ltd",
            bidder_id=uuid4(),
            db=session,
            entity_identifier="BIDDER-01",
        )
        gstn_items = [it for it in items if it.source_type == SourceType.GSTN]
        assert len(gstn_items) >= 2

        turnover_item = next(it for it in gstn_items if it.field_name == "turnover")
        assert turnover_item.normalized_value == 45.20
        assert turnover_item.unit == "CR"
        assert turnover_item.is_mock is True
        assert turnover_item.page_number is None  # Statutory records never have invented page numbers
        assert turnover_item.source_record_id == "MOCK-GSTN-BIDDER-01"
        assert "GSTIN: 27AAACE1001A1Z1" in turnover_item.provenance_reference
        assert turnover_item.evidence_type == EvidenceType.STATUTORY_REGISTRY


# ===========================================================================
# 3. Udyam Evidence Representation
# ===========================================================================
@pytest.mark.anyio
async def test_udyam_evidence_representation():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)
        items = await EvidenceFusionService.collect_mock_source_evidence(
            bidder_company_name="Zenith Cloud Technologies Pvt Ltd",
            bidder_id=uuid4(),
            db=session,
            entity_identifier="BIDDER-03",
        )
        udyam_items = [it for it in items if it.source_type == SourceType.UDYAM]
        assert len(udyam_items) >= 1

        ent_item = next(it for it in udyam_items if it.field_name == "enterprise_type")
        assert ent_item.normalized_value == "MICRO"
        assert ent_item.status == "ACTIVE"
        assert ent_item.is_mock is True
        assert ent_item.page_number is None
        assert ent_item.source_record_id == "MOCK-UDYAM-BIDDER-03"
        assert "UDYAM-KR-03-0010003" in ent_item.provenance_reference


# ===========================================================================
# 4. MCA Evidence Representation
# ===========================================================================
@pytest.mark.anyio
async def test_mca_evidence_representation():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)
        items = await EvidenceFusionService.collect_mock_source_evidence(
            bidder_company_name="Enterprise Tech Solutions Ltd",
            bidder_id=uuid4(),
            db=session,
            entity_identifier="BIDDER-01",
        )
        mca_items = [it for it in items if it.source_type == SourceType.MCA]
        assert len(mca_items) >= 1

        status_item = next(it for it in mca_items if it.field_name == "company_status")
        assert status_item.normalized_value == "ACTIVE"
        assert status_item.is_mock is True
        assert status_item.page_number is None
        assert status_item.source_record_id == "MOCK-MCA-BIDDER-01"
        assert "U72200MH2015PLC261001" in status_item.provenance_reference


# ===========================================================================
# 5. Income Tax Evidence Representation
# ===========================================================================
@pytest.mark.anyio
async def test_income_tax_evidence_representation():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)
        items = await EvidenceFusionService.collect_mock_source_evidence(
            bidder_company_name="Enterprise Tech Solutions Ltd",
            bidder_id=uuid4(),
            db=session,
            entity_identifier="BIDDER-01",
        )
        it_items = [it for it in items if it.source_type == SourceType.INCOME_TAX]
        assert len(it_items) >= 1

        pan_item = next(it for it in it_items if it.field_name == "pan_status")
        assert pan_item.normalized_value == "ACTIVE"
        assert pan_item.is_mock is True
        assert pan_item.page_number is None
        assert pan_item.source_record_id == "MOCK-IT-BIDDER-01"
        assert "PAN: AAACE1001A" in pan_item.provenance_reference


# ===========================================================================
# 6. Make in India (MII) Evidence Representation
# ===========================================================================
@pytest.mark.anyio
async def test_make_in_india_evidence_representation():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)
        items = await EvidenceFusionService.collect_mock_source_evidence(
            bidder_company_name="Enterprise Tech Solutions Ltd",
            bidder_id=uuid4(),
            db=session,
            entity_identifier="BIDDER-01",
        )
        mii_items = [it for it in items if it.source_type == SourceType.MAKE_IN_INDIA]
        assert len(mii_items) >= 1

        content_item = next(it for it in mii_items if it.field_name == "local_content_percent")
        assert content_item.normalized_value == 62.0
        assert content_item.unit == "%"
        assert content_item.status == "VERIFIED_CLASS_I"
        assert content_item.is_mock is True
        assert content_item.page_number is None
        assert content_item.source_record_id == "MOCK-MII-BIDDER-01"
        assert "Make in India Verification ID" in content_item.provenance_reference


# ===========================================================================
# 7. Multiple Sources for Same Field Remain Separate
# ===========================================================================
def test_multiple_sources_for_same_field_remain_separate():
    bidder_id = str(uuid4())

    # Source 1: Bidder Document (claims 8.0 Cr)
    doc_item = EvidenceItem(
        bidder_id=bidder_id,
        evidence_type=EvidenceType.DOCUMENT_CLAIM,
        source_type=SourceType.BIDDER_DOCUMENT,
        source_name="Bidder_Proposal_Page3.pdf",
        field_name="turnover",
        normalized_value=8.0,
        display_value="₹8.00 Cr",
        unit="CR",
        page_number=3,
        source_record_id="chunk-01",
        provenance_reference="Bidder_Proposal_Page3.pdf Page 3: 'Turnover INR 8.0 Cr'",
        is_mock=False,
    )

    # Source 2: GSTN Statutory Record (verified 3.65 Cr)
    gstn_item = EvidenceItem(
        bidder_id=bidder_id,
        evidence_type=EvidenceType.STATUTORY_REGISTRY,
        source_type=SourceType.GSTN,
        source_name="Goods & Services Tax Network (GSTN)",
        field_name="turnover",
        normalized_value=3.65,
        display_value="₹3.65 Cr",
        unit="CR",
        status="ACTIVE",
        page_number=None,
        source_record_id="MOCK-GSTN-BIDDER-10",
        provenance_reference="GSTN Verification ID: MOCK-GSTN-BIDDER-10",
        is_mock=True,
    )

    # Group evidence by field
    groups = EvidenceFusionService.group_evidence_by_field([doc_item, gstn_item], bidder_id)

    assert "turnover" in groups
    grp = groups["turnover"]
    assert grp.source_count == 2
    assert len(grp.evidence) == 2

    # Verify both items remain distinct and neither overwrote the other
    src_types = [e.source_type for e in grp.evidence]
    values = [e.normalized_value for e in grp.evidence]

    assert SourceType.BIDDER_DOCUMENT in src_types
    assert SourceType.GSTN in src_types
    assert 8.0 in values
    assert 3.65 in values


# ===========================================================================
# 8. Provenance Preservation
# ===========================================================================
def test_provenance_is_preserved():
    bidder_id = str(uuid4())

    doc_item = EvidenceItem(
        bidder_id=bidder_id,
        evidence_type=EvidenceType.DOCUMENT_CLAIM,
        source_type=SourceType.BIDDER_DOCUMENT,
        source_name="Technical_Spec.pdf",
        field_name="cpu_cores",
        normalized_value=64,
        display_value="64 cores",
        unit="cores",
        page_number=1,
        source_record_id="chunk-01",
        provenance_reference="Technical_Spec.pdf (Page 1): 'minimum 64-core processors'",
        is_mock=False,
    )

    stat_item = EvidenceItem(
        bidder_id=bidder_id,
        evidence_type=EvidenceType.STATUTORY_REGISTRY,
        source_type=SourceType.MAKE_IN_INDIA,
        source_name="Make in India Authority",
        field_name="local_content_percent",
        normalized_value=50.0,
        display_value="50.0%",
        unit="%",
        status="VERIFIED_CLASS_I",
        page_number=None,
        source_record_id="MOCK-MII-BIDDER-01",
        provenance_reference="MII Verification ID: MOCK-MII-BIDDER-01 | Authority: Statutory Auditor",
        is_mock=True,
    )

    # Assert document provenance
    assert doc_item.page_number == 1
    assert "Page 1" in doc_item.provenance_reference
    assert doc_item.is_mock is False

    # Assert statutory provenance (NEVER has invented page number)
    assert stat_item.page_number is None
    assert stat_item.source_record_id == "MOCK-MII-BIDDER-01"
    assert "MOCK-MII-BIDDER-01" in stat_item.provenance_reference
    assert stat_item.is_mock is True


# ===========================================================================
# 9. Strict Bidder Isolation
# ===========================================================================
@pytest.mark.anyio
async def test_bidder_isolation_is_preserved():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)
        bidder_a_id = uuid4()
        bidder_b_id = uuid4()

        # Fuse for Bidder A (BIDDER-01)
        profile_a = await EvidenceFusionService.fuse_bidder_evidence(
            bidder_id=bidder_a_id,
            db=session,
            company_name_override="Enterprise Tech Solutions Ltd (Bidder A)",
        )

        # Fuse for Bidder B (BIDDER-09)
        profile_b = await EvidenceFusionService.fuse_bidder_evidence(
            bidder_id=bidder_b_id,
            db=session,
            company_name_override="Legacy Hardware Trading Co (Bidder B)",
        )

        assert profile_a.bidder_id == str(bidder_a_id)
        assert profile_b.bidder_id == str(bidder_b_id)
        assert profile_a.entity_identifier == "BIDDER-01"
        assert profile_b.entity_identifier == "BIDDER-09"

        # Check turnover isolation
        turnover_a = profile_a.field_groups["turnover"].evidence
        turnover_b = profile_b.field_groups["turnover"].evidence

        vals_a = [e.normalized_value for e in turnover_a]
        vals_b = [e.normalized_value for e in turnover_b]

        # Bidder A has 45.20 Cr in GSTN; Bidder B has 4.80 Cr in GSTN
        assert 45.20 in vals_a
        assert 4.80 not in vals_a

        assert 4.80 in vals_b
        assert 45.20 not in vals_b


# ===========================================================================
# 10. Missing Source Resilience
# ===========================================================================
@pytest.mark.anyio
async def test_missing_source_evidence_does_not_crash():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        unknown_bidder_id = uuid4()

        # Bidder with no match in mock registries and no documents
        profile = await EvidenceFusionService.fuse_bidder_evidence(
            bidder_id=unknown_bidder_id,
            db=session,
            company_name_override="Unregistered Unknown Startup LLP",
        )

        assert profile.bidder_id == str(unknown_bidder_id)
        assert profile.total_evidence_items == 0
        assert len(profile.field_groups) == 0
        assert profile.sources_present == []
        assert profile.disclaimer == MOCK_SOURCE_TYPE_LABEL


# ===========================================================================
# 11. Mock vs Bidder Evidence Clearly Distinguishable
# ===========================================================================
@pytest.mark.anyio
async def test_mock_vs_bidder_evidence_clearly_distinguishable():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)
        bidder_id = uuid4()
        profile = await EvidenceFusionService.fuse_bidder_evidence(
            bidder_id=bidder_id,
            db=session,
            company_name_override="Enterprise Tech Solutions Ltd (Bidder A)",
        )

        assert profile.disclaimer == MOCK_SOURCE_TYPE_LABEL

        for field_name, group in profile.field_groups.items():
            for ev in group.evidence:
                if ev.source_type == SourceType.BIDDER_DOCUMENT:
                    assert ev.is_mock is False
                    assert ev.evidence_type == EvidenceType.DOCUMENT_CLAIM
                else:
                    assert ev.is_mock is True
                    assert ev.evidence_type == EvidenceType.STATUTORY_REGISTRY
                    assert ev.source_record_id is not None
                    assert ev.page_number is None


# ===========================================================================
# 12. Read-Only API Endpoint
# ===========================================================================
@pytest.mark.anyio
async def test_api_evidence_fusion_endpoint():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)

        # 1. Create tender and bidder directly in DB
        tender = Tender(
            title="Evidence Fusion Verification Tender",
            gem_tender_id=f"GEM/2026/B/FUSION-{uuid4().hex[:6]}",
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
        # 2. Request evidence fusion profile
        fusion_resp = await client.get(f"/api/v1/tenders/{tender_id}/bidders/{bidder_id}/evidence-fusion")
        assert fusion_resp.status_code == 200
        data = fusion_resp.json()

        assert data["bidder_id"] == str(bidder_id)
        assert "Enterprise Tech Solutions" in data["company_name"]
        assert data["entity_identifier"] == "BIDDER-01"
        assert "field_groups" in data
        assert "turnover" in data["field_groups"]
        assert data["total_evidence_items"] > 0
        assert data["disclaimer"] == MOCK_SOURCE_TYPE_LABEL

        # 3. Request for non-existent bidder returns 404
        fake_bidder_id = str(uuid4())
        missing_resp = await client.get(f"/api/v1/tenders/{tender_id}/bidders/{fake_bidder_id}/evidence-fusion")
        assert missing_resp.status_code == 404
