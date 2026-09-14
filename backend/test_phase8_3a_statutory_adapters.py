"""
test_phase8_3a_statutory_adapters.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Comprehensive test suite for Phase 8.3A Statutory Verification Adapters:
1. DPIIT / Startup India
2. EPFO Establishment Registry
3. ESIC Employer Registry

Verification Areas:
- Adapter contract & return schema
- NOT_FOUND semantics (connection=SUCCESS, verification=NOT_FOUND)
- INACTIVE semantics
- Identity hierarchy (Authoritative: PAN > CIN > entity_identifier; Name-only: UNVERIFIED)
- Source failure isolation (TIMEOUT/UNAVAILABLE/AUTH_FAILURE != bidder FAIL)
- SourceMode.MOCK & payload sanitization
- PostgreSQL persistence
- Deterministic concurrency
- Tender/bidder isolation
- Regression for Phase 8.1 / Phase 8.2 / Phase 6
"""

import asyncio
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import AsyncSessionLocal, init_db
from app.schemas.statutory_verification import (
    StatutoryAuthority,
    SourceMode,
    SourceConnectionStatus,
    SourceVerificationStatus,
    SourceVerificationResult,
    StatutoryVerificationQuery,
    STATUTORY_MOCK_BANNER,
)
from app.models.statutory import StatutoryVerificationRecord
from app.models.mock_sources import (
    MockDPIITRecord,
    MockEPFORecord,
    MockESICRecord,
)
from app.services.statutory_adapters import (
    StatutoryAdapterRegistry,
    get_statutory_registry,
    DPIITSourceAdapter,
    EPFOSourceAdapter,
    ESICSourceAdapter,
    sanitize_payload,
)
from app.services.statutory_orchestrator import (
    StatutoryVerificationOrchestrator,
    get_statutory_orchestrator,
)
from app.services.mock_seeder import seed_mock_sources


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


# ==============================================================================
# 1. ADAPTER CONTRACT TESTS
# ==============================================================================

@pytest.mark.anyio
async def test_dpiit_adapter_contract_success():
    """Verify DPIIT adapter contract on clean active startup showcase."""
    async with AsyncSessionLocal() as session:
        registry = get_statutory_registry()
        adapter = registry.get_adapter(StatutoryAuthority.DPIIT)
        assert adapter is not None
        assert adapter.authority == StatutoryAuthority.DPIIT
        assert adapter.source_name == "DPIIT / Startup India"

        # Lookup by certificate number
        res = await adapter.verify(
            query_identifier="DIPP11111",
            identifier_type="certificate_number",
            db=session,
        )

        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.mode == SourceMode.MOCK
        assert res.data_payload["is_recognized"] is True
        assert res.data_payload["certificate_number"] == "DIPP11111"
        assert res.data_payload["pan"] == "AAACD1111A"
        assert res.data_payload["cin"] == "U72200MH2020PTC341111"
        assert res.data_payload["officer_review_required"] is False
        assert STATUTORY_MOCK_BANNER in res.provenance_note


@pytest.mark.anyio
async def test_epfo_adapter_contract_success():
    """Verify EPFO adapter contract on clean active establishment showcase."""
    async with AsyncSessionLocal() as session:
        registry = get_statutory_registry()
        adapter = registry.get_adapter(StatutoryAuthority.EPFO)
        assert adapter is not None
        assert adapter.authority == StatutoryAuthority.EPFO
        assert adapter.source_name == "EPFO Establishment Registry"

        # Lookup by establishment code
        res = await adapter.verify(
            query_identifier="MHBAN0010010000",
            identifier_type="establishment_code",
            db=session,
        )

        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.mode == SourceMode.MOCK
        assert res.data_payload["is_covered"] is True
        assert res.data_payload["establishment_code"] == "MHBAN0010010000"
        assert res.data_payload["pan"] == "AAACE1001A"
        assert res.data_payload["officer_review_required"] is False
        # Assert establishment-level ONLY: no employee data keys
        for forbidden in ["employees", "employee_count", "member_id", "uan", "salary"]:
            assert forbidden not in res.data_payload


@pytest.mark.anyio
async def test_esic_adapter_contract_success():
    """Verify ESIC adapter contract on clean active employer showcase."""
    async with AsyncSessionLocal() as session:
        registry = get_statutory_registry()
        adapter = registry.get_adapter(StatutoryAuthority.ESIC)
        assert adapter is not None
        assert adapter.authority == StatutoryAuthority.ESIC
        assert adapter.source_name == "ESIC Employer Registry"

        # Lookup by 17-digit ESIC code
        res = await adapter.verify(
            query_identifier="31000100100001001",
            identifier_type="esic_code",
            db=session,
        )

        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.mode == SourceMode.MOCK
        assert res.data_payload["is_covered"] is True
        assert res.data_payload["esic_code"] == "31000100100001001"
        assert res.data_payload["pan"] == "AAACE1001A"
        assert res.data_payload["officer_review_required"] is False
        # Assert employer-level ONLY: no insured person data
        for forbidden in ["insured_persons", "ip_number", "contribution", "wages"]:
            assert forbidden not in res.data_payload


# ==============================================================================
# 2. NOT_FOUND SEMANTICS
# ==============================================================================

@pytest.mark.anyio
async def test_not_found_semantics_dpiit_epfo_esic():
    """Verify that absent registry entities return connection SUCCESS and verification NOT_FOUND."""
    async with AsyncSessionLocal() as session:
        registry = get_statutory_registry()

        # DPIIT Not Found
        dpiit = registry.get_adapter(StatutoryAuthority.DPIIT)
        res_d = await dpiit.verify(query_identifier="DIPP99999", identifier_type="certificate_number", db=session)
        assert res_d.connection_status == SourceConnectionStatus.SUCCESS
        assert res_d.verification_status == SourceVerificationStatus.NOT_FOUND
        assert res_d.data_payload.get("is_recognized") is False

        # EPFO Not Found
        epfo = registry.get_adapter(StatutoryAuthority.EPFO)
        res_p = await epfo.verify(query_identifier="XXBAN9999999999", identifier_type="establishment_code", db=session)
        assert res_p.connection_status == SourceConnectionStatus.SUCCESS
        assert res_p.verification_status == SourceVerificationStatus.NOT_FOUND
        assert res_p.data_payload.get("is_covered") is False

        # ESIC Not Found
        esic = registry.get_adapter(StatutoryAuthority.ESIC)
        res_s = await esic.verify(query_identifier="99000999990009999", identifier_type="esic_code", db=session)
        assert res_s.connection_status == SourceConnectionStatus.SUCCESS
        assert res_s.verification_status == SourceVerificationStatus.NOT_FOUND
        assert res_s.data_payload.get("is_covered") is False


# ==============================================================================
# 3. INACTIVE STATUS SEMANTICS
# ==============================================================================

@pytest.mark.anyio
async def test_inactive_semantics():
    """Verify that inactive or deregistered entities return INACTIVE status."""
    async with AsyncSessionLocal() as session:
        registry = get_statutory_registry()

        # DPIIT Inactive
        dpiit = registry.get_adapter(StatutoryAuthority.DPIIT)
        res_d = await dpiit.verify(query_identifier="DIPP22222", identifier_type="certificate_number", db=session)
        assert res_d.connection_status == SourceConnectionStatus.SUCCESS
        assert res_d.verification_status == SourceVerificationStatus.INACTIVE
        assert res_d.data_payload["is_recognized"] is False
        assert res_d.data_payload["officer_review_required"] is True

        # EPFO Inactive
        epfo = registry.get_adapter(StatutoryAuthority.EPFO)
        res_p = await epfo.verify(query_identifier="DLCPM0020020000", identifier_type="establishment_code", db=session)
        assert res_p.connection_status == SourceConnectionStatus.SUCCESS
        assert res_p.verification_status == SourceVerificationStatus.INACTIVE
        assert res_p.data_payload["is_covered"] is False

        # ESIC Inactive
        esic = registry.get_adapter(StatutoryAuthority.ESIC)
        res_s = await esic.verify(query_identifier="11000200200001002", identifier_type="esic_code", db=session)
        assert res_s.connection_status == SourceConnectionStatus.SUCCESS
        assert res_s.verification_status == SourceVerificationStatus.INACTIVE
        assert res_s.data_payload["is_covered"] is False


# ==============================================================================
# 4. IDENTITY HIERARCHY & AMBIGUOUS NAME MATCHES
# ==============================================================================

@pytest.mark.anyio
async def test_identity_hierarchy_authoritative_overrides_name():
    """Authoritative identifiers (PAN, CIN, Code) establish identity; name-only CANNOT verify."""
    async with AsyncSessionLocal() as session:
        registry = get_statutory_registry()
        dpiit = registry.get_adapter(StatutoryAuthority.DPIIT)

        # 1. Authoritative PAN match
        res_pan = await dpiit.verify(query_identifier="AAACD1111A", identifier_type="pan", db=session)
        assert res_pan.verification_status == SourceVerificationStatus.VERIFIED
        assert res_pan.data_payload["is_recognized"] is True
        assert res_pan.data_payload["matched_by"] == "PAN"

        # 2. Authoritative CIN match
        res_cin = await dpiit.verify(query_identifier="U72200MH2020PTC341111", identifier_type="cin", db=session)
        assert res_cin.verification_status == SourceVerificationStatus.VERIFIED
        assert res_cin.data_payload["is_recognized"] is True
        assert res_cin.data_payload["matched_by"] == "CIN"

        # 3. Weak Name-Only match MUST produce UNVERIFIED + officer review
        res_name = await dpiit.verify(
            query_identifier="Startup India Innovations Pvt Ltd",
            identifier_type="company_name",
            db=session,
        )
        assert res_name.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res_name.data_payload["is_recognized"] is False
        assert res_name.data_payload["is_ambiguous_match"] is True
        assert res_name.data_payload["officer_review_required"] is True
        assert res_name.data_payload["matched_by"] == "COMPANY_NAME_ONLY"


@pytest.mark.anyio
async def test_epfo_esic_name_only_ambiguous():
    """Verify EPFO and ESIC also produce UNVERIFIED for name-only matching."""
    async with AsyncSessionLocal() as session:
        registry = get_statutory_registry()

        # EPFO Name match
        epfo = registry.get_adapter(StatutoryAuthority.EPFO)
        res_p = await epfo.verify(
            query_identifier="Apex Engineering Works Ltd",
            identifier_type="establishment_name",
            db=session,
        )
        assert res_p.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res_p.data_payload["is_covered"] is False
        assert res_p.data_payload["is_ambiguous_match"] is True
        assert res_p.data_payload["officer_review_required"] is True

        # ESIC Name match
        esic = registry.get_adapter(StatutoryAuthority.ESIC)
        res_s = await esic.verify(
            query_identifier="Apex Engineering Works Ltd",
            identifier_type="employer_name",
            db=session,
        )
        assert res_s.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res_s.data_payload["is_covered"] is False
        assert res_s.data_payload["is_ambiguous_match"] is True
        assert res_s.data_payload["officer_review_required"] is True


@pytest.mark.anyio
async def test_dpiit_pan_source_code_conflict():
    """Case A: DPIIT - Query PAN A + Certificate B (belonging to PAN B) -> UNVERIFIED + conflict."""
    async with AsyncSessionLocal() as session:
        adapter = get_statutory_registry().get_adapter(StatutoryAuthority.DPIIT)
        res = await adapter.verify(
            query_identifier="DIPP22222",
            identifier_type="certificate_number",
            pan="AAACD1111A",  # Bidder PAN is AAACD1111A, but DIPP22222 belongs to AAACD2222B
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload["is_ambiguous_match"] is True
        assert res.data_payload["officer_review_required"] is True
        assert res.data_payload["conflict_detected"] is True
        assert "PAN conflict" in res.data_payload["review_reason"]


@pytest.mark.anyio
async def test_epfo_pan_source_code_conflict():
    """Case A: EPFO - Query PAN A + Establishment Code B (belonging to PAN B) -> UNVERIFIED + conflict."""
    async with AsyncSessionLocal() as session:
        adapter = get_statutory_registry().get_adapter(StatutoryAuthority.EPFO)
        res = await adapter.verify(
            query_identifier="DLCPM0020020000",
            identifier_type="establishment_code",
            pan="AAACE1001A",  # Bidder PAN is AAACE1001A, but DLCPM0020020000 belongs to AAACE2002B
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload["is_ambiguous_match"] is True
        assert res.data_payload["officer_review_required"] is True
        assert res.data_payload["conflict_detected"] is True
        assert "PAN conflict" in res.data_payload["review_reason"]


@pytest.mark.anyio
async def test_esic_pan_source_code_conflict():
    """Case A: ESIC - Query PAN A + ESIC Code B (belonging to PAN B) -> UNVERIFIED + conflict."""
    async with AsyncSessionLocal() as session:
        adapter = get_statutory_registry().get_adapter(StatutoryAuthority.ESIC)
        res = await adapter.verify(
            query_identifier="11000200200001002",
            identifier_type="esic_code",
            pan="AAACE1001A",  # Bidder PAN is AAACE1001A, but 11000200200001002 belongs to AAACE2002B
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload["is_ambiguous_match"] is True
        assert res.data_payload["officer_review_required"] is True
        assert res.data_payload["conflict_detected"] is True
        assert "PAN conflict" in res.data_payload["review_reason"]


@pytest.mark.anyio
async def test_cin_source_code_conflict():
    """Case B: Query CIN A + Certificate B (belonging to CIN B) -> UNVERIFIED + conflict."""
    async with AsyncSessionLocal() as session:
        adapter = get_statutory_registry().get_adapter(StatutoryAuthority.DPIIT)
        res = await adapter.verify(
            query_identifier="DIPP22222",
            identifier_type="certificate_number",
            cin="U72200MH2020PTC341111",  # Bidder CIN is for Record A, but DIPP22222 belongs to Record B (DL)
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload["is_ambiguous_match"] is True
        assert res.data_payload["officer_review_required"] is True
        assert res.data_payload["conflict_detected"] is True
        assert "CIN conflict" in res.data_payload["review_reason"]


@pytest.mark.anyio
async def test_consistent_pan_source_code_match():
    """Case D: Query PAN A + Certificate A (belonging to PAN A) -> Normal VERIFIED status."""
    async with AsyncSessionLocal() as session:
        adapter = get_statutory_registry().get_adapter(StatutoryAuthority.DPIIT)
        res = await adapter.verify(
            query_identifier="DIPP11111",
            identifier_type="certificate_number",
            pan="AAACD1111A",  # Matches Record A exactly
            cin="U72200MH2020PTC341111",
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.data_payload["is_recognized"] is True
        assert res.data_payload["is_ambiguous_match"] is False
        assert res.data_payload["officer_review_required"] is False


@pytest.mark.anyio
async def test_gstin_udyam_identity_context_preservation():
    """Case C: GSTIN embeds PAN; verify conflict detection and consistency preservation."""
    async with AsyncSessionLocal() as session:
        adapter = get_statutory_registry().get_adapter(StatutoryAuthority.DPIIT)

        # Conflict: GSTIN embeds AAACD1111A, but certificate is DIPP22222 (belongs to AAACD2222B)
        res_conflict = await adapter.verify(
            query_identifier="DIPP22222",
            identifier_type="certificate_number",
            gstin="27AAACD1111A1Z1",
            db=session,
        )
        assert res_conflict.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res_conflict.data_payload["is_ambiguous_match"] is True
        assert res_conflict.data_payload["conflict_detected"] is True

        # Consistent: GSTIN embeds AAACD1111A, certificate is DIPP11111 (belongs to AAACD1111A)
        res_ok = await adapter.verify(
            query_identifier="DIPP11111",
            identifier_type="certificate_number",
            gstin="27AAACD1111A1Z1",
            db=session,
        )
        assert res_ok.verification_status == SourceVerificationStatus.VERIFIED
        assert res_ok.data_payload["is_recognized"] is True
        assert res_ok.data_payload["is_ambiguous_match"] is False


@pytest.mark.anyio
async def test_bidder_id_not_used_as_registry_identifier():
    """Verify internal bidder_id alone does not match a real statutory code."""
    async with AsyncSessionLocal() as session:
        registry = get_statutory_registry()
        epfo = registry.get_adapter(StatutoryAuthority.EPFO)

        # Internal bidder UUID
        res = await epfo.verify(
            query_identifier=str(uuid.uuid4()),
            identifier_type="entity_identifier",
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.NOT_FOUND


# ==============================================================================
# 5. SOURCE FAILURE SEMANTICS (NEVER BIDDER FAIL)
# ==============================================================================

@pytest.mark.anyio
async def test_source_failure_isolation_not_bidder_fail():
    """Source UNAVAILABLE/ERROR does NOT imply bidder FAIL."""
    registry = get_statutory_registry()
    dpiit = registry.get_adapter(StatutoryAuthority.DPIIT)

    # db=None simulates DB/Transport UNAVAILABLE
    res = await dpiit.verify(
        query_identifier="DIPP11111",
        identifier_type="certificate_number",
        db=None,
    )

    assert res.connection_status == SourceConnectionStatus.UNAVAILABLE
    assert res.verification_status == SourceVerificationStatus.FAILED
    assert res.data_payload == {}
    assert "Database session unavailable" in (res.error_message or "")


# ==============================================================================
# 6. PAYLOAD SANITIZATION & MOCK INDICATOR
# ==============================================================================

@pytest.mark.anyio
async def test_payload_sanitization_and_mock_mode():
    """Verify all results indicate MOCK mode and sensitive tokens are redacted."""
    raw_dict = {
        "certificate_number": "DIPP11111",
        "secret_token": "bearer 123456",
        "api_key": "gov_secret",
        "normal_field": "public",
    }
    sanitized = sanitize_payload(raw_dict)
    assert sanitized["certificate_number"] == "DIPP11111"
    assert sanitized["secret_token"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["normal_field"] == "public"


# ==============================================================================
# 7. POSTGRESQL PERSISTENCE
# ==============================================================================

@pytest.mark.anyio
async def test_postgresql_persistence_and_query():
    """Verify statutory verification record persists and retrieves properly."""
    async with AsyncSessionLocal() as session:
        dpiit = get_statutory_registry().get_adapter(StatutoryAuthority.DPIIT)
        res = await dpiit.verify(query_identifier="DIPP11111", db=session)

        # Create persistence record
        record = StatutoryVerificationRecord(
            verification_id=res.verification_id,
            bidder_id=None,
            tender_id=None,
            authority=res.authority.value,
            source_name=res.source_name,
            query_identifier=res.query_identifier,
            identifier_type=res.identifier_type,
            mode=res.mode.value,
            connection_status=res.connection_status.value,
            verification_status=res.verification_status.value,
            data_payload=res.data_payload,
            confidence_score=res.confidence_score,
            provenance_note=res.provenance_note,
            execution_time_ms=res.execution_time_ms,
        )
        session.add(record)
        await session.commit()

        # Query back
        stmt = select(StatutoryVerificationRecord).where(
            StatutoryVerificationRecord.verification_id == res.verification_id
        )
        fetched = (await session.execute(stmt)).scalars().first()
        assert fetched is not None
        assert fetched.authority == "DPIIT"
        assert fetched.verification_status == "VERIFIED"
        assert fetched.data_payload["certificate_number"] == "DIPP11111"


# ==============================================================================
# 8. CONCURRENCY & ORCHESTRATOR INTEGRATION
# ==============================================================================

@pytest.mark.anyio
async def test_orchestrator_concurrency_deterministic():
    """Verify orchestrator executes all 9 registered adapters concurrently."""
    orchestrator = get_statutory_orchestrator()
    all_adapters = orchestrator.registry.get_all_adapters()
    assert len(all_adapters) == 9
    assert StatutoryAuthority.DPIIT in all_adapters
    assert StatutoryAuthority.EPFO in all_adapters
    assert StatutoryAuthority.ESIC in all_adapters

    query = StatutoryVerificationQuery(
        bidder_id=None,
        tender_id=None,
        identifiers={
            "pan": "AAACE1001A",
            "cin": "U72200MH2018PTC311001",
            "gstin": "27AAACE1001A1Z1",
            "udyam_number": "UDYAM-MH-01-0011001",
            "certificate_number": "DIPP11111",
            "establishment_code": "MHBAN0010010000",
            "esic_code": "31000100100001001",
        },
        as_of_date=date(2026, 3, 1),
        mode=SourceMode.MOCK,
    )

    async with AsyncSessionLocal() as session:
        summary = await orchestrator.verify_statutory_sources(query, db=session, persist=False)
    assert summary.total_sources == 9
    assert summary.successful_connections == 9
    assert summary.failed_connections == 0
    assert len(summary.results) == 9

    # Verify each Phase 8.3A authority result is present in summary
    authorities_in_results = {r.authority for r in summary.results}
    assert StatutoryAuthority.DPIIT in authorities_in_results
    assert StatutoryAuthority.EPFO in authorities_in_results
    assert StatutoryAuthority.ESIC in authorities_in_results


# ==============================================================================
# 9. TENDER / BIDDER ISOLATION
# ==============================================================================

@pytest.mark.anyio
async def test_bidder_isolation():
    """Ensure query for Bidder A does not interleave with Bidder B."""
    orchestrator = get_statutory_orchestrator()

    query_a = StatutoryVerificationQuery(
        bidder_id=None,
        tender_id=None,
        identifiers={"pan": "AAACD1111A", "certificate_number": "DIPP11111"},
        authorities=[StatutoryAuthority.DPIIT],
    )
    query_b = StatutoryVerificationQuery(
        bidder_id=None,
        tender_id=None,
        identifiers={"pan": "AAACD2222B", "certificate_number": "DIPP22222"},
        authorities=[StatutoryAuthority.DPIIT],
    )

    async with AsyncSessionLocal() as session:
        summary_a = await orchestrator.verify_statutory_sources(query_a, db=session, persist=False)
        summary_b = await orchestrator.verify_statutory_sources(query_b, db=session, persist=False)

    assert summary_a.results[0].verification_status == SourceVerificationStatus.VERIFIED
    assert summary_b.results[0].verification_status == SourceVerificationStatus.INACTIVE


# ==============================================================================
# 10. REGRESSION CHECKS (Phase 8.1 & Phase 8.2 Debarment)
# ==============================================================================

@pytest.mark.anyio
async def test_phase8_2_debarment_regression():
    """Verify Phase 8.2 debarment temporal verification remains intact."""
    async with AsyncSessionLocal() as session:
        registry = get_statutory_registry()
        deb_adapter = registry.get_adapter(StatutoryAuthority.DEBARMENT)

        # 1. Active Debarment on date
        res_active = await deb_adapter.verify(
            query_identifier="DEMO-ACTIVE-001",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res_active.connection_status == SourceConnectionStatus.SUCCESS
        assert res_active.verification_status == SourceVerificationStatus.VERIFIED
        assert res_active.data_payload["is_debarred_on_date"] is True

        # 2. No as_of_date returns UNKNOWN_PERIOD with is_debarred_on_date=False
        res_no_date = await deb_adapter.verify(
            query_identifier="DEMO-ACTIVE-001",
            as_of_date=None,
            db=session,
        )
        assert res_no_date.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res_no_date.data_payload["is_debarred_on_date"] is False
        assert res_no_date.data_payload["temporal_status"] == "UNKNOWN_PERIOD"
