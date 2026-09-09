import os
import uuid
import pytest
import asyncio
from uuid import uuid4
from typing import AsyncGenerator
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, func

from app.core.database import Base, get_db
from app.main import app
from app.models.tender import Tender
from app.models.clause import TenderClause
from app.models.bidder import Bidder, BidDocument
from app.models.chunk import DocumentChunk
from app.models.evaluation import ComplianceEvaluation

# 11 Structured GeM Tender Clauses matching Day 4 benchmark
BENCHMARK_CLAUSES = [
    {
        "clause_code": "TECH-01",
        "category": "TECHNICAL",
        "title": "Server Compute Infrastructure",
        "description": "Rack servers equipped with minimum 64-core processors and 256GB ECC DDR5 RAM",
        "source_text": "The bidder must provide rack servers equipped with minimum 64-core processors and 256GB ECC DDR5 RAM.",
        "is_mandatory": True,
        "page_number": 1,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "cpu_cores", "value": 64, "unit": "cores"},
    },
    {
        "clause_code": "TECH-02",
        "category": "TECHNICAL",
        "title": "Hardware Quality & BIS Standards",
        "description": "BIS certification and ISO 9001:2015 quality standards compliance",
        "source_text": "All hardware components must be certified under BIS and comply with ISO 9001:2015 quality standards.",
        "is_mandatory": True,
        "page_number": 1,
        "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "bis_and_iso_cert", "value": None},
    },
    {
        "clause_code": "TECH-03",
        "category": "TECHNICAL",
        "title": "OEM Warranty Coverage",
        "description": "3-year comprehensive on-site OEM warranty",
        "source_text": "Comprehensive on-site OEM warranty of 3 years shall be provided for all supplied equipment.",
        "is_mandatory": True,
        "page_number": 1,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "warranty_years", "value": 3, "unit": "years"},
    },
    {
        "clause_code": "FIN-01",
        "category": "FINANCIAL",
        "title": "Minimum Average Annual Turnover",
        "description": "Average annual turnover of at least INR 5.0 Crores during last 3 financial years",
        "source_text": "Average annual turnover of the bidder during the last three financial years must be at least INR 5.0 Crores.",
        "is_mandatory": True,
        "page_number": 2,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "average_annual_turnover", "value": 5.0, "unit": "Crores"},
    },
    {
        "clause_code": "FIN-02",
        "category": "FINANCIAL",
        "title": "Audited Balance Sheets Upload",
        "description": "Audited balance sheets and CA certificate with UDIN",
        "source_text": "Audited balance sheets and chartered accountant certificates must be uploaded.",
        "is_mandatory": True,
        "page_number": 2,
        "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "audited_balance_sheets", "value": None},
    },
    {
        "clause_code": "FIN-03",
        "category": "FINANCIAL",
        "title": "Earnest Money Deposit (EMD)",
        "description": "Online bank guarantee of INR 10,00,000",
        "source_text": "Bidder must submit an Earnest Money Deposit of INR 10,00,000 via online bank guarantee.",
        "is_mandatory": True,
        "page_number": 2,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "emd_amount", "value": 1000000, "unit": "INR"},
    },
    {
        "clause_code": "FIN-04",
        "category": "FINANCIAL",
        "title": "EMD Exemption for MSEs",
        "description": "Exemption permissible for registered MSEs",
        "source_text": "EMD exemption is permissible for registered Micro and Small Enterprises (MSEs).",
        "is_mandatory": False,
        "page_number": 2,
        "rule_config": {"type": "CUSTOM", "parameter": "mse_exemption", "value": None},
    },
    {
        "clause_code": "STAT-01",
        "category": "STATUTORY",
        "title": "Make in India (MII) Local Content",
        "description": "Minimum 50 percent local content for Class-I Local Supplier",
        "source_text": "Minimum 50 percent local content is mandatory for qualification under Class-I Local Supplier category.",
        "is_mandatory": True,
        "page_number": 3,
        "rule_config": {"type": "PERCENT_MIN", "parameter": "local_content_percentage", "value": 50, "unit": "%"},
    },
    {
        "clause_code": "STAT-02",
        "category": "STATUTORY",
        "title": "Self-Certification of Local Content",
        "description": "Self-certification indicating percentage of local content",
        "source_text": "Self-certification indicating the percentage of local content must be provided.",
        "is_mandatory": True,
        "page_number": 3,
        "rule_config": {"type": "DOCUMENT_REQUIRED", "parameter": "local_content_self_cert", "value": None},
    },
    {
        "clause_code": "EXP-01",
        "category": "EXPERIENCE",
        "title": "Past Contract Execution",
        "description": "Execution of at least 2 similar enterprise IT contracts in last 3 years",
        "source_text": "Bidder must have successfully executed at least 2 similar enterprise IT contracts in the last 3 years.",
        "is_mandatory": True,
        "page_number": 3,
        "rule_config": {"type": "NUMERIC_MIN", "parameter": "similar_contracts_count", "value": 2, "unit": "contracts"},
    },
    {
        "clause_code": "DEL-01",
        "category": "DELIVERY_SLA",
        "title": "Delivery Timelines",
        "description": "Hardware items delivered and installed within 45 days",
        "source_text": "All hardware items and software licenses must be delivered and installed within 45 days from contract award.",
        "is_mandatory": True,
        "page_number": 4,
        "rule_config": {"type": "NUMERIC_MAX", "parameter": "delivery_time_days", "value": 45, "unit": "days"},
    },
]

TEST_DB_PATH = "test_api_vslice.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def stub_embeddings():
    from unittest.mock import patch
    from app.services.embedding_service import get_embedding_service
    stub_service = get_embedding_service(force_stub=True)
    with patch("app.api.v1.bidders.get_embedding_service", return_value=stub_service), \
         patch("app.api.v1.evaluations.get_embedding_service", return_value=stub_service), \
         patch("app.services.evidence_retrieval.get_embedding_service", return_value=stub_service):
        yield



@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Create all tables in test database and clean up after."""
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

    async def _init():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())
    app.dependency_overrides[get_db] = override_get_db

    yield

    app.dependency_overrides.clear()
    asyncio.run(test_engine.dispose())
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass


async def _create_test_tender_with_clauses(session: AsyncSession, title: str = "Enterprise Server Procurement") -> Tender:
    tender = Tender(
        title=title,
        gem_tender_id="GEM/2026/B/8912450",
        file_name="tender_document.pdf",
        total_pages=4,
        extraction_status="READY",
        next_clause_seq={"TECH": 4, "FIN": 5, "STAT": 3, "EXP": 2, "DEL": 2, "GEN": 1},
    )
    session.add(tender)
    await session.flush()

    for item in BENCHMARK_CLAUSES:
        clause = TenderClause(
            tender_id=tender.id,
            clause_code=item["clause_code"],
            category=item["category"],
            title=item["title"],
            description=item["description"],
            source_text=item["source_text"],
            page_number=item["page_number"],
            is_mandatory=item["is_mandatory"],
            rule_config=item["rule_config"],
            is_confirmed=True,
        )
        session.add(clause)

    await session.commit()
    await session.refresh(tender)
    return tender


@pytest.mark.anyio
async def test_01_full_api_vertical_slice_lifecycle():
    """Test 1: Full vertical slice HTTP lifecycle:
    POST demo bidders
    → POST evaluation/run
    → GET matrix
    → GET evaluation/detail
    → POST override
    → verify matrix reflects override.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create tender in DB
        async with TestSessionLocal() as session:
            tender = await _create_test_tender_with_clauses(session, "Lifecycle Test Tender")
            tender_id = tender.id

        # 2. POST demo bidders
        resp_bidders = await client.post(f"/api/v1/tenders/{tender_id}/bidders/demo")
        assert resp_bidders.status_code == 200
        bidders_data = resp_bidders.json()
        assert bidders_data["bidders_count"] == 3
        assert len(bidders_data["bidders"]) == 3

        # 3. POST evaluation/run
        resp_eval = await client.post(
            f"/api/v1/tenders/{tender_id}/evaluations/run",
            json={"use_live_llm": False},
        )
        assert resp_eval.status_code == 200
        eval_data = resp_eval.json()
        assert eval_data["bidders_evaluated"] == 3
        assert eval_data["total_evaluations"] == 33  # 3 bidders * 11 clauses

        # 4. GET matrix
        resp_matrix = await client.get(f"/api/v1/tenders/{tender_id}/evaluations/matrix")
        assert resp_matrix.status_code == 200
        matrix_data = resp_matrix.json()
        assert len(matrix_data["bidders"]) == 3
        assert len(matrix_data["clauses"]) == 11
        assert matrix_data["summary"]["total_officer_overrides"] == 0

        # Pick an evaluation to inspect: Bidder B on TECH-01 (should be FAIL)
        bidder_b_id = next(b["id"] for b in matrix_data["bidders"] if "Bidder B" in b["company_name"])
        cell_tech01 = matrix_data["matrix"][bidder_b_id]["TECH-01"]
        assert cell_tech01["status"] == "FAIL"
        assert cell_tech01["original_status"] == "FAIL"
        eval_id = cell_tech01["evaluation_id"]

        # 5. GET evaluation/detail
        resp_detail = await client.get(f"/api/v1/tenders/{tender_id}/evaluations/{eval_id}")
        assert resp_detail.status_code == 200
        detail_data = resp_detail.json()
        assert detail_data["clause_code"] == "TECH-01"
        assert detail_data["status"] == "FAIL"
        assert detail_data["override_status"] is None

        # 6. POST override
        justification = "Procurement Committee approved dual-socket concession based on Addendum 3."
        resp_override = await client.post(
            f"/api/v1/tenders/{tender_id}/evaluations/{eval_id}/override",
            json={"override_status": "PASS", "override_reason": justification},
        )
        assert resp_override.status_code == 200
        override_data = resp_override.json()
        assert override_data["status"] == "PASS"  # effective status is now PASS
        assert override_data["original_status"] == "FAIL"  # original status preserved
        assert override_data["override_status"] == "PASS"
        assert override_data["override_reason"] == justification

        # 7. Verify matrix reflects override
        resp_matrix_after = await client.get(f"/api/v1/tenders/{tender_id}/evaluations/matrix")
        assert resp_matrix_after.status_code == 200
        matrix_after = resp_matrix_after.json()
        updated_cell = matrix_after["matrix"][bidder_b_id]["TECH-01"]
        assert updated_cell["status"] == "PASS"
        assert updated_cell["original_status"] == "FAIL"
        assert updated_cell["override_status"] == "PASS"
        assert updated_cell["override_reason"] == justification
        assert matrix_after["summary"]["total_officer_overrides"] == 1


@pytest.mark.anyio
async def test_02_demo_bidders_idempotency():
    """Test 2: Demo bidder loading MUST be idempotent.
    Running twice must not duplicate bidders, documents, chunks, or evaluations.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with TestSessionLocal() as session:
            tender = await _create_test_tender_with_clauses(session, "Idempotency Test Tender")
            tender_id = tender.id

        # First load
        resp1 = await client.post(f"/api/v1/tenders/{tender_id}/bidders/demo")
        assert resp1.status_code == 200
        assert resp1.json()["bidders_count"] == 3

        # Run evaluation once
        await client.post(f"/api/v1/tenders/{tender_id}/evaluations/run", json={"use_live_llm": False})

        # Second load (MUST be completely idempotent)
        resp2 = await client.post(f"/api/v1/tenders/{tender_id}/bidders/demo")
        assert resp2.status_code == 200
        assert resp2.json()["bidders_count"] == 3

        # Verify DB counts: exactly 3 bidders, 3 documents, 12 chunks
        async with TestSessionLocal() as session:
            bidders_cnt = (await session.execute(
                select(func.count(Bidder.id)).where(Bidder.tender_id == tender_id)
            )).scalar()
            assert bidders_cnt == 3

            docs_cnt = (await session.execute(
                select(func.count(BidDocument.id))
                .join(Bidder, BidDocument.bidder_id == Bidder.id)
                .where(Bidder.tender_id == tender_id)
            )).scalar()
            assert docs_cnt == 3

            chunks_cnt = (await session.execute(
                select(func.count(DocumentChunk.id))
                .join(Bidder, DocumentChunk.bidder_id == Bidder.id)
                .where(Bidder.tender_id == tender_id)
            )).scalar()
            assert chunks_cnt == 12  # 4 pages * 3 bidders = 12 chunks

            evals_cnt = (await session.execute(
                select(func.count(ComplianceEvaluation.id))
                .join(Bidder, ComplianceEvaluation.bidder_id == Bidder.id)
                .where(Bidder.tender_id == tender_id)
            )).scalar()
            assert evals_cnt == 33  # 3 bidders * 11 clauses


@pytest.mark.anyio
async def test_03_officer_override_preservation_regression():
    """Test 3: Preserve officer overrides across re-evaluations:
    evaluate → override → evaluate again
    MUST leave the officer override intact.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with TestSessionLocal() as session:
            tender = await _create_test_tender_with_clauses(session, "Override Preservation Tender")
            tender_id = tender.id

        # 1. Load bidders & evaluate
        await client.post(f"/api/v1/tenders/{tender_id}/bidders/demo")
        await client.post(f"/api/v1/tenders/{tender_id}/evaluations/run", json={"use_live_llm": False})

        # 2. Fetch matrix and find Bidder B FIN-01 (Turnover failure)
        matrix = (await client.get(f"/api/v1/tenders/{tender_id}/evaluations/matrix")).json()
        bidder_b_id = next(b["id"] for b in matrix["bidders"] if "Bidder B" in b["company_name"])
        eval_id = matrix["matrix"][bidder_b_id]["FIN-01"]["evaluation_id"]

        # 3. Apply officer override
        justification = "Relaxation granted by Competent Authority under Start-up / MSME exemption order #44."
        override_resp = await client.post(
            f"/api/v1/tenders/{tender_id}/evaluations/{eval_id}/override",
            json={"override_status": "PASS", "override_reason": justification},
        )
        assert override_resp.status_code == 200

        # 4. RE-RUN EVALUATION (Simulates officer triggering re-check)
        reeval_resp = await client.post(
            f"/api/v1/tenders/{tender_id}/evaluations/run",
            json={"use_live_llm": False},
        )
        assert reeval_resp.status_code == 200

        # 5. Verify the officer override was PRESERVED in detail and in matrix
        detail_after = (await client.get(f"/api/v1/tenders/{tender_id}/evaluations/{eval_id}")).json()
        assert detail_after["override_status"] == "PASS"
        assert detail_after["override_reason"] == justification
        assert detail_after["status"] == "PASS"
        assert detail_after["original_status"] == "FAIL"

        matrix_after = (await client.get(f"/api/v1/tenders/{tender_id}/evaluations/matrix")).json()
        cell_after = matrix_after["matrix"][bidder_b_id]["FIN-01"]
        assert cell_after["override_status"] == "PASS"
        assert cell_after["override_reason"] == justification
        assert cell_after["status"] == "PASS"
        assert cell_after["original_status"] == "FAIL"


@pytest.mark.anyio
async def test_04_officer_override_requires_non_empty_justification():
    """Test 4: Override requires non-empty officer justification.
    Never allow an empty or whitespace-only override reason.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with TestSessionLocal() as session:
            tender = await _create_test_tender_with_clauses(session, "Justification Validation Tender")
            tender_id = tender.id

        await client.post(f"/api/v1/tenders/{tender_id}/bidders/demo")
        await client.post(f"/api/v1/tenders/{tender_id}/evaluations/run", json={"use_live_llm": False})

        matrix = (await client.get(f"/api/v1/tenders/{tender_id}/evaluations/matrix")).json()
        bidder_b_id = next(b["id"] for b in matrix["bidders"] if "Bidder B" in b["company_name"])
        eval_id = matrix["matrix"][bidder_b_id]["TECH-03"]["evaluation_id"]

        # Empty reason
        resp_empty = await client.post(
            f"/api/v1/tenders/{tender_id}/evaluations/{eval_id}/override",
            json={"override_status": "PASS", "override_reason": ""},
        )
        assert resp_empty.status_code == 422

        # Whitespace-only reason
        resp_spaces = await client.post(
            f"/api/v1/tenders/{tender_id}/evaluations/{eval_id}/override",
            json={"override_status": "PASS", "override_reason": "    "},
        )
        assert resp_spaces.status_code == 422

        # Too short reason (length < 3)
        resp_short = await client.post(
            f"/api/v1/tenders/{tender_id}/evaluations/{eval_id}/override",
            json={"override_status": "PASS", "override_reason": "ok"},
        )
        assert resp_short.status_code == 422


@pytest.mark.anyio
async def test_05_tender_and_bidder_boundary_isolation():
    """Test 5: Validate tender ownership and boundary isolation.
    Do not allow a bidder/evaluation from tender A to be accessed or modified via tender B.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create Tender 1 and Tender 2
        async with TestSessionLocal() as session:
            tender1 = await _create_test_tender_with_clauses(session, "Tender 1 - Ministry IT")
            tender2 = await _create_test_tender_with_clauses(session, "Tender 2 - Railway Telecom")
            t1_id = tender1.id
            t2_id = tender2.id

        # Load demo bidders on Tender 1
        await client.post(f"/api/v1/tenders/{t1_id}/bidders/demo")
        await client.post(f"/api/v1/tenders/{t1_id}/evaluations/run", json={"use_live_llm": False})

        # Fetch Bidder and Evaluation ID from Tender 1
        t1_bidders = (await client.get(f"/api/v1/tenders/{t1_id}/bidders")).json()
        b1_id = t1_bidders[0]["id"]

        t1_matrix = (await client.get(f"/api/v1/tenders/{t1_id}/evaluations/matrix")).json()
        e1_id = t1_matrix["matrix"][b1_id]["TECH-01"]["evaluation_id"]

        # Attempt to access Tender 1's bidder through Tender 2
        resp_cross_bidder = await client.get(f"/api/v1/tenders/{t2_id}/bidders/{b1_id}")
        assert resp_cross_bidder.status_code == 404

        # Attempt to delete Tender 1's bidder through Tender 2
        resp_cross_del = await client.delete(f"/api/v1/tenders/{t2_id}/bidders/{b1_id}")
        assert resp_cross_del.status_code == 404

        # Attempt to access Tender 1's evaluation through Tender 2
        resp_cross_eval = await client.get(f"/api/v1/tenders/{t2_id}/evaluations/{e1_id}")
        assert resp_cross_eval.status_code == 404

        # Attempt to override Tender 1's evaluation through Tender 2
        resp_cross_override = await client.post(
            f"/api/v1/tenders/{t2_id}/evaluations/{e1_id}/override",
            json={"override_status": "PASS", "override_reason": "Illegitimate cross-tender override attempt"},
        )
        assert resp_cross_override.status_code == 404


@pytest.mark.anyio
async def test_06_day4_regressions_via_api():
    """Test 6: Verify Day 4 regressions through the API:
    - Bidder C STAT-01 contradiction does not leak into unrelated clauses.
    - Bidder B TECH-01 extracts the correct CPU claim (32.0 cores).
    - No bidder can retrieve another bidder's chunks.
    - PASS/FAIL/REVIEW results match verified synthetic benchmark.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with TestSessionLocal() as session:
            tender = await _create_test_tender_with_clauses(session, "Benchmark Verification Tender")
            tender_id = tender.id

        await client.post(f"/api/v1/tenders/{tender_id}/bidders/demo")
        eval_resp = await client.post(
            f"/api/v1/tenders/{tender_id}/evaluations/run",
            json={"use_live_llm": False},
        )
        assert eval_resp.status_code == 200

        matrix_resp = await client.get(f"/api/v1/tenders/{tender_id}/evaluations/matrix")
        matrix = matrix_resp.json()

        bidder_a = next(b for b in matrix["bidders"] if "Bidder A" in b["company_name"])
        bidder_b = next(b for b in matrix["bidders"] if "Bidder B" in b["company_name"])
        bidder_c = next(b for b in matrix["bidders"] if "Bidder C" in b["company_name"])

        # 1. Exact synthetic benchmark compliance counts verified
        # Bidder A: 11 PASS, 0 FAIL, 0 REVIEW
        assert bidder_a["pass_count"] == 11
        assert bidder_a["fail_count"] == 0
        assert bidder_a["review_count"] == 0
        assert bidder_a["final_status"] == "QUALIFIED"

        # Bidder B: 1 PASS, 9 FAIL, 1 REVIEW
        assert bidder_b["pass_count"] == 1
        assert bidder_b["fail_count"] == 9
        assert bidder_b["review_count"] == 1
        assert bidder_b["final_status"] == "DISQUALIFIED"

        # Bidder C: 3 PASS, 5 FAIL, 3 REVIEW
        assert bidder_c["pass_count"] == 3
        assert bidder_c["fail_count"] == 5
        assert bidder_c["review_count"] == 3

        # 2. Bidder B TECH-01 extracts correct CPU claim
        b_tech01 = matrix["matrix"][bidder_b["id"]]["TECH-01"]
        assert b_tech01["status"] == "FAIL"
        assert b_tech01["claimed_value"] == "32.0 cores"
        assert "shortfall" in b_tech01["reasoning"].lower()

        # 3. Bidder C STAT-01 contradiction does NOT leak into TECH-01 or DEL-01
        c_stat01 = matrix["matrix"][bidder_c["id"]]["STAT-01"]
        assert c_stat01["status"] == "REVIEW"
        assert c_stat01["contradiction_detected"] is True

        c_tech01 = matrix["matrix"][bidder_c["id"]]["TECH-01"]
        assert c_tech01["status"] == "FAIL"
        assert c_tech01["contradiction_detected"] is False  # Contradiction MUST NOT leak

        c_del01 = matrix["matrix"][bidder_c["id"]]["DEL-01"]
        assert c_del01["status"] == "FAIL"
        assert c_del01["contradiction_detected"] is False  # Contradiction MUST NOT leak
