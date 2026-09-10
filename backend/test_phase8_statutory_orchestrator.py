"""
test_phase8_statutory_orchestrator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Comprehensive test suite for Phase 8.1 Unified Statutory Verification Orchestrator:
1. Canonical adapter contracts (GSTN, Udyam, MCA, Income Tax, MII).
2. Status separation: Connection status vs Domain verification status.
3. Connection SUCCESS + entity NOT_FOUND semantics.
4. Identifier resolution and separation from internal bidder_id.
5. Payload sanitization (redacting sensitive keys).
6. Temporal behavior: as_of_date (date) vs retrieved_at (timezone-aware datetime).
7. Deterministic concurrency using barrier/counter methodology.
8. Adapter failure isolation (unhandled exceptions do not disrupt other sources).
9. REST API endpoints (/verify, /status, /adapters).
10. Strict bidder isolation.
11. Compatibility with EvidenceFusionService facts.
12. Score and recommendation preservation.
"""

import asyncio
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.core.database import AsyncSessionLocal, init_db
from app.schemas.statutory_verification import (
    StatutoryAuthority,
    SourceMode,
    SourceConnectionStatus,
    SourceVerificationStatus,
    SourceVerificationResult,
    StatutoryVerificationQuery,
    BidderStatutoryVerificationSummary,
    STATUTORY_MOCK_BANNER,
)
from app.services.statutory_adapters import (
    BaseSourceAdapter,
    sanitize_payload,
    GSTNSourceAdapter,
    UdyamSourceAdapter,
    MCASourceAdapter,
    IncomeTaxSourceAdapter,
    MIISourceAdapter,
    StatutoryAdapterRegistry,
    get_statutory_registry,
)
from app.services.statutory_orchestrator import (
    StatutoryVerificationOrchestrator,
    get_statutory_orchestrator,
)
from app.models.statutory import StatutoryVerificationRecord
from app.services.mock_seeder import seed_mock_sources
from app.services.evidence_fusion_service import EvidenceFusionService


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_db_and_seeds(anyio_backend):
    """Ensure database and mock sources are initialized and seeded."""
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_mock_sources(session)
        await session.commit()



@pytest.mark.anyio
async def test_sanitize_payload():

    """Verify recursive redaction of sensitive credentials and tokens."""
    payload = {
        "company_name": "Acme Corp",
        "api_key": "super_secret_key_123",
        "nested": {
            "token": "bearer_token_xyz",
            "normal_field": 42,
            "auth_secret": "hidden",
        },
        "list_items": [
            {"password": "pw", "status": "ACTIVE"},
            "plain_string",
        ],
    }
    sanitized = sanitize_payload(payload)

    assert sanitized["company_name"] == "Acme Corp"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert sanitized["nested"]["normal_field"] == 42
    assert sanitized["nested"]["auth_secret"] == "[REDACTED]"
    assert sanitized["list_items"][0]["password"] == "[REDACTED]"
    assert sanitized["list_items"][0]["status"] == "ACTIVE"
    assert sanitized["list_items"][1] == "plain_string"


@pytest.mark.anyio
async def test_adapter_contracts_and_status_separation():
    """Verify each adapter returns clean separation between connection and verification status."""
    async with AsyncSessionLocal() as session:
        registry = get_statutory_registry()
        authorities = registry.list_supported_authorities()
        assert len(authorities) == 5

        # Test GSTN adapter with known seeded entity
        gstn_adapter = registry.get_adapter(StatutoryAuthority.GSTN)
        res = await gstn_adapter.verify(
            query_identifier="27AAACE1001A1Z1",
            identifier_type="gstin",
            db=session,
        )

        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status in [
            SourceVerificationStatus.VERIFIED,
            SourceVerificationStatus.INACTIVE,
        ]
        assert res.authority == StatutoryAuthority.GSTN
        assert res.provenance_note.startswith(STATUTORY_MOCK_BANNER)
        assert res.retrieved_at.tzinfo is not None
        assert "verified_turnover" in res.data_payload


@pytest.mark.anyio
async def test_connection_success_with_entity_not_found():
    """Verify that querying a non-existent entity results in connection SUCCESS and verification NOT_FOUND."""
    async with AsyncSessionLocal() as session:
        gstn_adapter = GSTNSourceAdapter()
        res = await gstn_adapter.verify(
            query_identifier="NON_EXISTENT_GSTIN_99999",
            identifier_type="gstin",
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.NOT_FOUND
        assert res.data_payload == {}
        assert "not found" in (res.error_message or "").lower()

        udyam_adapter = UdyamSourceAdapter()
        u_res = await udyam_adapter.verify(
            query_identifier="UDYAM-XX-00-9999999",
            identifier_type="udyam_number",
            db=session,
        )
        assert u_res.connection_status == SourceConnectionStatus.SUCCESS
        assert u_res.verification_status == SourceVerificationStatus.NOT_FOUND


@pytest.mark.anyio
async def test_temporal_behavior_as_of_date():
    """Verify temporal handling: as_of_date (date) and retrieved_at (timezone-aware datetime)."""
    async with AsyncSessionLocal() as session:
        gstn_adapter = GSTNSourceAdapter()
        # Query with historical as_of_date
        past_date = date(2020, 1, 1)
        res = await gstn_adapter.verify(
            query_identifier="27AAACE1001A1Z1",
            as_of_date=past_date,
            db=session,
        )
        assert res.as_of_date == past_date
        assert isinstance(res.as_of_date, date)
        assert isinstance(res.retrieved_at, datetime)
        assert res.retrieved_at.tzinfo is not None


@pytest.mark.anyio
async def test_identifier_resolution_and_isolation():
    """Verify orchestrator maps distinct query identifiers and keeps bidder_id separate."""
    orchestrator = get_statutory_orchestrator()

    identifiers = {
        "gstin": "27AAACE1001A1Z1",
        "udyam_number": "UDYAM-DL-01-0012345",
        "cin": "U72900DL2018PTC123456",
        "pan": "AAACE1234F",
        "certificate_reference": "MII-2024-001",
    }

    gstn_id, g_type = orchestrator.resolve_query_identifier(
        StatutoryAuthority.GSTN, identifiers, fallback_name="Acme Tech"
    )
    assert gstn_id == "27AAACE1001A1Z1"
    assert g_type == "gstin"

    pan_id, p_type = orchestrator.resolve_query_identifier(
        StatutoryAuthority.INCOME_TAX, identifiers, fallback_name="Acme Tech"
    )
    assert pan_id == "AAACE1234F"
    assert p_type == "pan"

    # Verify fallback to company_name when specific key missing
    empty_ids: Dict[str, str] = {}
    fallback_id, f_type = orchestrator.resolve_query_identifier(
        StatutoryAuthority.GSTN, empty_ids, fallback_name="Fallback Bidder Pvt Ltd"
    )
    assert fallback_id == "Fallback Bidder Pvt Ltd"
    assert f_type == "company_name"


@pytest.mark.anyio
async def test_deterministic_concurrency_barrier():
    """
    Verify deterministic concurrent execution of source adapters
    using an active concurrency counter and asyncio.Barrier.
    Proves that peak concurrency >= 3 without relying on arbitrary sleep durations.
    """
    barrier = asyncio.Barrier(3)
    active_concurrent = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    class ConcurrencyProbeAdapter(BaseSourceAdapter):
        def __init__(self, auth: StatutoryAuthority, name: str):
            self._auth = auth
            self._name = name

        @property
        def authority(self) -> StatutoryAuthority:
            return self._auth

        @property
        def source_name(self) -> str:
            return self._name

        def get_supported_identifier_types(self) -> List[str]:
            return ["test_id"]

        async def verify(self, query_identifier: str, **kwargs: Any) -> SourceVerificationResult:
            nonlocal active_concurrent, max_concurrent
            async with lock:
                active_concurrent += 1
                if active_concurrent > max_concurrent:
                    max_concurrent = active_concurrent

            # Synchronize across all 3 concurrent tasks at the barrier
            await barrier.wait()

            async with lock:
                active_concurrent -= 1

            return SourceVerificationResult(
                verification_id=str(uuid.uuid4()),
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=query_identifier,
                identifier_type="test_id",
                connection_status=SourceConnectionStatus.SUCCESS,
                verification_status=SourceVerificationStatus.VERIFIED,
                retrieved_at=datetime.now(timezone.utc),
            )

    probe_registry = StatutoryAdapterRegistry()
    probe_registry._adapters.clear()
    probe_registry.register(ConcurrencyProbeAdapter(StatutoryAuthority.GSTN, "Probe GSTN"))
    probe_registry.register(ConcurrencyProbeAdapter(StatutoryAuthority.UDYAM, "Probe Udyam"))
    probe_registry.register(ConcurrencyProbeAdapter(StatutoryAuthority.MCA, "Probe MCA"))

    orchestrator = StatutoryVerificationOrchestrator(registry=probe_registry)
    query = StatutoryVerificationQuery(
        identifiers={"test_id": "VAL123"},
        authorities=[StatutoryAuthority.GSTN, StatutoryAuthority.UDYAM, StatutoryAuthority.MCA],
    )

    summary = await orchestrator.verify_statutory_sources(query, persist=False)

    assert summary.total_sources == 3
    assert summary.successful_connections == 3
    # Proves all 3 tasks reached the execution barrier concurrently
    assert max_concurrent == 3


@pytest.mark.anyio
async def test_adapter_failure_isolation():
    """Verify that an adapter throwing an unhandled exception does not crash other adapters."""
    class CrashingAdapter(BaseSourceAdapter):
        @property
        def authority(self) -> StatutoryAuthority:
            return StatutoryAuthority.GSTN

        @property
        def source_name(self) -> str:
            return "Crashing Source"

        def get_supported_identifier_types(self) -> List[str]:
            return ["any"]

        async def verify(self, *args, **kwargs) -> SourceVerificationResult:
            raise RuntimeError("Fatal hardware or socket breakdown")

    custom_registry = StatutoryAdapterRegistry()
    custom_registry.register(CrashingAdapter())

    orchestrator = StatutoryVerificationOrchestrator(registry=custom_registry)
    async with AsyncSessionLocal() as session:
        query = StatutoryVerificationQuery(
            identifiers={"gstin": "CRASH_ME"},
            authorities=[StatutoryAuthority.GSTN, StatutoryAuthority.UDYAM],
        )
        summary = await orchestrator.verify_statutory_sources(query, db=session, persist=False)

        assert summary.total_sources == 2
        crash_res = next(r for r in summary.results if r.authority == StatutoryAuthority.GSTN)
        assert crash_res.connection_status == SourceConnectionStatus.ERROR
        assert crash_res.verification_status == SourceVerificationStatus.FAILED
        assert "Fatal hardware or socket breakdown" in (crash_res.error_message or "")

        # Other adapter (Udyam) must still have executed cleanly
        udyam_res = next(r for r in summary.results if r.authority == StatutoryAuthority.UDYAM)
        assert udyam_res.connection_status == SourceConnectionStatus.SUCCESS


@pytest.mark.anyio
async def test_rest_api_endpoints():
    """Verify REST endpoints: /adapters, /verify, /status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /api/v1/statutory/adapters
        res = await client.get("/api/v1/statutory/adapters")
        assert res.status_code == 200
        adapters = res.json()
        assert len(adapters) >= 5
        authorities = {a["authority"] for a in adapters}
        assert {"GSTN", "UDYAM", "MCA", "INCOME_TAX", "MII"}.issubset(authorities)

        # 2. POST /api/v1/statutory/verify
        verify_req = {
            "identifiers": {
                "gstin": "27AAACE1001A1Z1",
                "pan": "AAACE1001A",
            },
            "authorities": ["GSTN", "INCOME_TAX"],
            "as_of_date": "2024-06-30",
        }
        post_res = await client.post("/api/v1/statutory/verify", json=verify_req)
        assert post_res.status_code == 200
        summary_data = post_res.json()
        assert summary_data["total_sources"] == 2
        assert len(summary_data["results"]) == 2
        assert summary_data["as_of_date"] == "2024-06-30"

        # 3. GET /api/v1/statutory/status
        status_res = await client.get("/api/v1/statutory/status?authority=GSTN&limit=5")
        assert status_res.status_code == 200
        status_list = status_res.json()
        assert isinstance(status_list, list)


@pytest.mark.anyio
async def test_bidder_isolation_and_persistence():
    """Verify statutory records are persisted with bidder/tender context and don't leak."""
    from app.models.tender import Tender
    from app.models.bidder import Bidder

    orchestrator = get_statutory_orchestrator()
    async with AsyncSessionLocal() as session:
        # Create test tender and bidders to satisfy DB FK constraints
        tender = Tender(title=f"Statutory Test Tender {uuid.uuid4()}")
        session.add(tender)
        await session.flush()

        bidder_a = Bidder(company_name="Bidder A Tech", tender_id=tender.id)
        bidder_b = Bidder(company_name="Bidder B Systems", tender_id=tender.id)
        session.add_all([bidder_a, bidder_b])
        await session.commit()

        # Run query for Bidder A
        q_a = StatutoryVerificationQuery(
            bidder_id=str(bidder_a.id),
            tender_id=str(tender.id),
            authorities=[StatutoryAuthority.GSTN],
            identifiers={"gstin": "27AAACE1001A1Z1"},
        )
        await orchestrator.verify_statutory_sources(q_a, db=session, persist=True)

        # Run query for Bidder B with a non-existent identifier
        q_b = StatutoryVerificationQuery(
            bidder_id=str(bidder_b.id),
            tender_id=str(tender.id),
            authorities=[StatutoryAuthority.GSTN],
            identifiers={"gstin": "NON_EXISTENT_B"},
        )
        await orchestrator.verify_statutory_sources(q_b, db=session, persist=True)
        await session.commit()

        # Query records for Bidder A
        stmt_a = select(StatutoryVerificationRecord).where(
            StatutoryVerificationRecord.bidder_id == bidder_a.id
        )
        recs_a = (await session.execute(stmt_a)).scalars().all()
        assert len(recs_a) >= 1
        for r in recs_a:
            assert r.bidder_id == bidder_a.id
            assert r.query_identifier == "27AAACE1001A1Z1"

        # Query records for Bidder B
        stmt_b = select(StatutoryVerificationRecord).where(
            StatutoryVerificationRecord.bidder_id == bidder_b.id
        )
        recs_b = (await session.execute(stmt_b)).scalars().all()
        assert len(recs_b) >= 1
        for r in recs_b:
            assert r.bidder_id == bidder_b.id
            assert r.query_identifier == "NON_EXISTENT_B"
            assert r.verification_status == SourceVerificationStatus.NOT_FOUND.value


@pytest.mark.anyio
async def test_evidence_fusion_compatibility():
    """
    Verify that the factual attributes returned by Phase 8.1 adapters are
    compatible and consistent with the facts collected by EvidenceFusionService.
    """
    async with AsyncSessionLocal() as session:
        # 1. Collect statutory facts via EvidenceFusionService
        fusion_items = await EvidenceFusionService.collect_mock_source_evidence(
            bidder_company_name="Enterprise Tech Solutions Ltd",
            bidder_id="e6c17247-38fa-44f7-84cb-bc2450e20fcc",
            db=session,
            entity_identifier="BIDDER-01",
        )
        gstn_fusion = next((i for i in fusion_items if i.field_name == "turnover"), None)
        assert gstn_fusion is not None

        # 2. Collect statutory facts via Phase 8.1 GSTNSourceAdapter
        gstn_adapter = GSTNSourceAdapter()
        adapter_res = await gstn_adapter.verify(
            query_identifier="BIDDER-01",
            identifier_type="entity_identifier",
            db=session,
        )
        assert adapter_res.connection_status == SourceConnectionStatus.SUCCESS
        assert adapter_res.verification_status == SourceVerificationStatus.VERIFIED

        # Compare turnover
        fusion_turnover = float(gstn_fusion.normalized_value)
        adapter_turnover = float(adapter_res.data_payload["verified_turnover"])
        assert fusion_turnover == adapter_turnover

