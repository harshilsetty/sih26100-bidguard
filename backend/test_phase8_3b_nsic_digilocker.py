"""
backend/test_phase8_3b_nsic_digilocker.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Comprehensive test suite for Phase 8.3B:
1. NSIC / Single Point Registration Scheme (SPRS)
2. DigiLocker document verification/provenance

Tests:
1. NSIC adapter contract
2. DigiLocker adapter contract
3. NSIC active/verified
4. NSIC expired
5. NSIC inactive
6. NSIC future/not-yet-valid
7. NSIC not-found
8. NSIC name-only ambiguity
9. NSIC source-code/PAN conflict
10. NSIC consistent identity
11. DigiLocker verified document
12. DigiLocker not found
13. DigiLocker unverified
14. DigiLocker signature invalid/not verified
15. DigiLocker authentication failure
16. DigiLocker timeout
17. source failure != bidder FAIL
18. bidder_id never used as statutory identity
19. identity cross-validation
20. payload sanitization
21. MOCK mode explicit
22. PostgreSQL persistence
23. repeated seed idempotency
24. deterministic concurrency
25. bidder isolation
26. temporal semantics / as_of_date=None
27. Phase 8.3A regression (DPIIT/EPFO/ESIC)
28. Phase 8.2 debarment regression
29. Phase 6.4 scoring regression
30. recommendation compatibility
"""

import asyncio
import pytest
from datetime import date, datetime
from sqlalchemy import select, func

from app.core.database import AsyncSessionLocal, init_db
from app.services.mock_seeder import seed_mock_sources
from app.schemas.statutory_verification import (
    StatutoryAuthority,
    SourceMode,
    SourceConnectionStatus,
    SourceVerificationStatus,
    SourceVerificationResult,
    StatutoryVerificationQuery,
    STATUTORY_MOCK_BANNER,
)
from app.models.mock_sources import (
    MockNSICRecord,
    MockDigiLockerRecord,
    MockDPIITRecord,
    MockEPFORecord,
    MockESICRecord,
    MockDebarmentRecord,
)
from app.services.statutory_adapters.nsic_adapter import NSICSourceAdapter
from app.services.statutory_adapters.digilocker_adapter import DigiLockerSourceAdapter
from app.services.statutory_adapters.base import (
    sanitize_payload,
    validate_bidder_identity_consistency,
)
from app.services.statutory_adapters.registry import get_statutory_registry
from app.services.statutory_orchestrator import StatutoryVerificationOrchestrator
from app.services.scoring_service import ScoringAndRankingService
from app.schemas.scoring import RiskLevel


from app.core.database import engine


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def cleanup_db_connections(anyio_backend):
    """Ensure database connection pool is disposed cleanly between tests."""
    yield
    await engine.dispose()


@pytest.mark.anyio
async def test_01_nsic_adapter_contract():
    """Verify NSIC adapter authority, naming, and supported identifier types."""
    adapter = NSICSourceAdapter()
    assert adapter.authority == StatutoryAuthority.NSIC
    assert "NSIC" in adapter.source_name
    supported = adapter.get_supported_identifier_types()
    assert "registration_number" in supported
    assert "pan" in supported
    assert "udyam_number" in supported
    assert "company_name" in supported


@pytest.mark.anyio
async def test_02_digilocker_adapter_contract():
    """Verify DigiLocker adapter authority, naming, and supported identifier types."""
    adapter = DigiLockerSourceAdapter()
    assert adapter.authority == StatutoryAuthority.DIGILOCKER
    assert "DigiLocker" in adapter.source_name
    supported = adapter.get_supported_identifier_types()
    assert "document_reference" in supported
    assert "pan" in supported
    assert "cin" in supported


@pytest.mark.anyio
async def test_03_nsic_active_verified():
    """Case A: NSIC Active + Valid within dates -> VERIFIED + ACTIVE_ON_DATE."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="NSIC-SPRS-11111",
            identifier_type="registration_number",
            as_of_date=date(2024, 6, 1),
            db=db,
            pan="AAACD1111A",
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.data_payload.get("is_registered") is True
        assert res.data_payload.get("temporal_status") == "ACTIVE_ON_DATE"
        assert res.data_payload.get("monetary_limit") == 50.0


@pytest.mark.anyio
async def test_04_nsic_expired():
    """Case B: NSIC Expired before as_of_date -> EXPIRED."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="NSIC-SPRS-22222",
            identifier_type="registration_number",
            as_of_date=date(2024, 6, 1),
            db=db,
            pan="AAACD2222B",
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.EXPIRED
        assert res.data_payload.get("is_registered") is False
        assert res.data_payload.get("temporal_status") == "EXPIRED_BEFORE_DATE"


@pytest.mark.anyio
async def test_05_nsic_inactive():
    """Case D: NSIC Inactive -> INACTIVE."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="NSIC-SPRS-33333",
            identifier_type="registration_number",
            as_of_date=date(2024, 6, 1),
            db=db,
            pan="AAACD3333C",
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.INACTIVE
        assert res.data_payload.get("is_registered") is False


@pytest.mark.anyio
async def test_06_nsic_future_not_yet_valid():
    """Case E: NSIC starts after as_of_date -> UNVERIFIED / STARTS_AFTER_DATE."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="NSIC-SPRS-44444",
            identifier_type="registration_number",
            as_of_date=date(2024, 6, 1),  # Starts 2027-01-01
            db=db,
            pan="AAACD4444D",
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload.get("temporal_status") == "STARTS_AFTER_DATE"
        assert res.data_payload.get("is_registered") is False


@pytest.mark.anyio
async def test_07_nsic_not_found():
    """Case C: NSIC Not Found in register -> SUCCESS + NOT_FOUND."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="NSIC-NONEXISTENT-99999",
            identifier_type="registration_number",
            as_of_date=date(2024, 6, 1),
            db=db,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.NOT_FOUND


@pytest.mark.anyio
async def test_08_nsic_name_only_ambiguity():
    """Case F: NSIC Name-only match -> UNVERIFIED + is_ambiguous_match + officer review."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="National Industries Pvt Ltd",
            identifier_type="company_name",
            as_of_date=date(2024, 6, 1),
            db=db,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload.get("is_ambiguous_match") is True
        assert res.data_payload.get("officer_review_required") is True


@pytest.mark.anyio
async def test_09_nsic_source_code_pan_conflict():
    """Case G: NSIC Registration Number points to record with PAN-G, but query PAN is PAN-A."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="NSIC-SPRS-66666",
            identifier_type="registration_number",
            as_of_date=date(2024, 6, 1),
            db=db,
            pan="AAACD1111A",  # Conflicting query PAN (record has AAACD6666G)
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload.get("is_ambiguous_match") is True
        assert res.data_payload.get("officer_review_required") is True
        assert res.data_payload.get("conflict_detected") is True


@pytest.mark.anyio
async def test_10_nsic_consistent_identity():
    """Case H: Consistent PAN + NSIC Registration Number -> Normal verified outcome."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="NSIC-SPRS-77777",
            identifier_type="registration_number",
            as_of_date=date(2024, 6, 1),
            db=db,
            pan="AAACD7777H",  # Matches record PAN
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.data_payload.get("conflict_detected") is False


@pytest.mark.anyio
async def test_11_digilocker_verified_document():
    """DigiLocker verified document with valid cryptographic signature."""
    adapter = DigiLockerSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="in.gov.pan-VER-001",
            identifier_type="document_reference",
            db=db,
            pan="AAACD1111A",
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.data_payload.get("signature_status") == "VALID"
        assert res.data_payload.get("verification_result") == "VERIFIED"
        assert res.data_payload.get("document_status") == "ACTIVE"


@pytest.mark.anyio
async def test_12_digilocker_not_found():
    """DigiLocker document reference not found -> SUCCESS + NOT_FOUND."""
    adapter = DigiLockerSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="in.gov.unknown-doc-99999",
            identifier_type="document_reference",
            db=db,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.NOT_FOUND


@pytest.mark.anyio
async def test_13_digilocker_unverified_signature():
    """DigiLocker document with unverified signature -> UNVERIFIED."""
    adapter = DigiLockerSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="in.gov.cert-UNVERIFIED-001",
            identifier_type="document_reference",
            db=db,
            pan="AAACD5555E",
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload.get("officer_review_required") is True


@pytest.mark.anyio
async def test_14_digilocker_signature_invalid_fails():
    """DigiLocker document with invalid / tampered signature -> FAILED."""
    adapter = DigiLockerSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="in.gov.mca-SIG-INVALID-001",
            identifier_type="document_reference",
            db=db,
            pan="AAACD2222B",
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.FAILED
        assert res.data_payload.get("signature_status") == "INVALID"


@pytest.mark.anyio
async def test_15_digilocker_authentication_failure():
    """DigiLocker gateway authentication failure -> AUTH_FAILURE connection status."""
    adapter = DigiLockerSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="DL-SIM-AUTH-FAILURE",
            identifier_type="document_reference",
            db=db,
        )
        assert res.connection_status == SourceConnectionStatus.AUTH_FAILURE
        assert res.verification_status == SourceVerificationStatus.FAILED


@pytest.mark.anyio
async def test_16_digilocker_timeout():
    """DigiLocker gateway timeout -> TIMEOUT connection status."""
    adapter = DigiLockerSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="DL-SIM-TIMEOUT",
            identifier_type="document_reference",
            db=db,
        )
        assert res.connection_status == SourceConnectionStatus.TIMEOUT
        assert res.verification_status == SourceVerificationStatus.FAILED


@pytest.mark.anyio
async def test_17_source_failure_not_bidder_fail():
    """Source unavailable or timeout must NEVER produce bidder FAIL."""
    adapter = NSICSourceAdapter()
    # Pass db=None to simulate database / network transport unavailability
    res = await adapter.verify(
        query_identifier="NSIC-SPRS-11111",
        db=None,
    )
    assert res.connection_status == SourceConnectionStatus.UNAVAILABLE
    assert res.verification_status == SourceVerificationStatus.FAILED
    # Connection error must not falsely conclude bidder is non-compliant or debarred


@pytest.mark.anyio
async def test_18_bidder_id_never_used_as_statutory_identity():
    """Internal database UUID must NEVER establish statutory identity."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="550e8400-e29b-41d4-a716-446655440000",
            identifier_type="bidder_id",
            as_of_date=date(2024, 6, 1),
            db=db,
        )
        # Without canonical statutory identifiers, must return NOT_FOUND or UNVERIFIED
        assert res.verification_status in (SourceVerificationStatus.NOT_FOUND, SourceVerificationStatus.UNVERIFIED)


@pytest.mark.anyio
async def test_19_identity_cross_validation_helper():
    """Test identity consistency helper with PAN, CIN, GSTIN, and Udyam."""
    # Consistent
    consistent, err = validate_bidder_identity_consistency(
        record_pan="ABCDE1234F",
        query_pan="ABCDE1234F",
    )
    assert consistent is True
    assert err is None

    # Mismatched PAN
    conflict, err = validate_bidder_identity_consistency(
        record_pan="ABCDE1234F",
        query_pan="XYZPA9999K",
    )
    assert conflict is False
    assert "PAN conflict" in err

    # Mismatched Udyam
    conflict, err = validate_bidder_identity_consistency(
        record_udyam="UDYAM-MH-01-0011111",
        query_udyam="UDYAM-DL-02-0022222",
    )
    assert conflict is False
    assert "Udyam conflict" in err


@pytest.mark.anyio
async def test_20_payload_sanitization():
    """Payload sanitization must redact sensitive token / secret patterns."""
    raw = {
        "access_token": "secret_bearer_12345",
        "api_key": "private_key_xyz",
        "public_data": {"registration_number": "NSIC-12345"},
    }
    sanitized = sanitize_payload(raw)
    assert sanitized["access_token"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["public_data"]["registration_number"] == "NSIC-12345"


@pytest.mark.anyio
async def test_21_mock_mode_explicit():
    """All results must explicitly declare MOCK mode and provenance note."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(query_identifier="NSIC-SPRS-11111", db=db)
        assert res.mode == SourceMode.MOCK
        assert res.provenance_note == STATUTORY_MOCK_BANNER


@pytest.mark.anyio
async def test_22_postgresql_persistence():
    """Verify PostgreSQL tables exist and have exactly 1,000 records each."""
    async with AsyncSessionLocal() as db:
        nsic_count = (await db.execute(select(func.count()).select_from(MockNSICRecord))).scalar_one()
        dl_count = (await db.execute(select(func.count()).select_from(MockDigiLockerRecord))).scalar_one()
        assert nsic_count == 1000
        assert dl_count == 1000


@pytest.mark.anyio
async def test_23_repeated_seed_idempotency():
    """Repeated seeding must not create duplicate records."""
    from app.services.mock_seeder import seed_mock_sources
    async with AsyncSessionLocal() as db:
        results = await seed_mock_sources(db)
        assert results["NSIC"]["inserted"] == 0
        assert results["NSIC"]["total_source"] == 1000
        assert results["DIGILOCKER"]["inserted"] == 0
        assert results["DIGILOCKER"]["total_source"] == 1000


@pytest.mark.anyio
async def test_24_deterministic_concurrency():
    """StatutoryVerificationOrchestrator queries all 11 adapters concurrently."""
    registry = get_statutory_registry()
    assert len(registry.list_supported_authorities()) == 11

    orchestrator = StatutoryVerificationOrchestrator(registry=registry)
    query = StatutoryVerificationQuery(
        identifiers={
            "pan": "AAACD1111A",
            "registration_number": "NSIC-SPRS-11111",
            "document_reference": "in.gov.pan-VER-001",
        },
        as_of_date=date(2024, 6, 1),
    )

    async with AsyncSessionLocal() as db:
        summary = await orchestrator.verify_statutory_sources(query=query, db=db, persist=False)
        assert summary.total_sources == 11
        assert summary.successful_connections == 11
        authorities = {r.authority for r in summary.results}
        assert StatutoryAuthority.NSIC in authorities
        assert StatutoryAuthority.DIGILOCKER in authorities


@pytest.mark.anyio
async def test_25_bidder_isolation():
    """Queries for Bidder A do not cross-pollinate with Bidder B."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res_a = await adapter.verify(query_identifier="NSIC-SPRS-11111", db=db, pan="AAACD1111A", as_of_date=date(2024, 6, 1))
        res_b = await adapter.verify(query_identifier="NSIC-SPRS-22222", db=db, pan="AAACD2222B", as_of_date=date(2024, 6, 1))
        assert res_a.verification_status == SourceVerificationStatus.VERIFIED
        assert res_b.verification_status == SourceVerificationStatus.EXPIRED


@pytest.mark.anyio
async def test_26_temporal_semantics_as_of_date_none():
    """as_of_date=None must NEVER use date.today() fallback."""
    adapter = NSICSourceAdapter()
    async with AsyncSessionLocal() as db:
        res = await adapter.verify(
            query_identifier="NSIC-SPRS-11111",
            as_of_date=None,  # No evaluation date
            db=db,
            pan="AAACD1111A",
        )
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload.get("temporal_status") == "UNKNOWN_PERIOD"
        assert res.data_payload.get("is_registered") is False


@pytest.mark.anyio
async def test_27_phase8_3a_regression():
    """Confirm Phase 8.3A adapters (DPIIT, EPFO, ESIC) remain intact."""
    async with AsyncSessionLocal() as db:
        dpiit_count = (await db.execute(select(func.count()).select_from(MockDPIITRecord))).scalar_one()
        epfo_count = (await db.execute(select(func.count()).select_from(MockEPFORecord))).scalar_one()
        esic_count = (await db.execute(select(func.count()).select_from(MockESICRecord))).scalar_one()
        assert dpiit_count == 1000
        assert epfo_count == 1000
        assert esic_count == 1000


@pytest.mark.anyio
async def test_28_phase8_2_debarment_regression():
    """Confirm Phase 8.2 temporal debarment records and logic remain identical."""
    async with AsyncSessionLocal() as db:
        deb_count = (await db.execute(select(func.count()).select_from(MockDebarmentRecord))).scalar_one()
        assert deb_count == 1000


@pytest.mark.anyio
async def test_29_phase6_4_scoring_regression():
    """Scoring service 100-point formula remains mathematically unchanged."""
    b_id = "550e8400-e29b-41d4-a716-446655440000"
    from app.schemas.evaluation import ComplianceStatus, ClauseComplianceEvaluation
    evals = [
        ClauseComplianceEvaluation(
            clause_code="TECH-01",
            clause_title="Technical Specifications",
            bidder_id=b_id,
            status=ComplianceStatus.PASS,
            confidence_score=1.0,
            claimed_value="Meets requirement",
            reasoning="Valid certificate verified in bid documents.",
            evidence_snippet="Audited ISO certificate verified.",
            evidence_page_number=1,
            contradiction_detected=False,
            requires_human_confirmation=False,
        )
    ]
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Clean Co",
        evaluations=evals,
    )
    assert score_resp.overall_score == 100.0
    assert score_resp.risk_level == RiskLevel.LOW
    assert score_resp.breakdown.tender_compliance == 50.0
    assert score_resp.breakdown.statutory_consistency == 20.0
    assert score_resp.breakdown.evidence_completeness == 15.0
    assert score_resp.breakdown.contradiction_score == 15.0


@pytest.mark.anyio
async def test_30_recommendation_compatibility():
    """Orchestrator summary cleanly integrates with downstream recommendation formats."""
    registry = get_statutory_registry()
    orchestrator = StatutoryVerificationOrchestrator(registry=registry)
    query = StatutoryVerificationQuery(
        identifiers={"pan": "AAACD1111A"},
        as_of_date=date(2024, 6, 1),
    )
    async with AsyncSessionLocal() as db:
        summary = await orchestrator.verify_statutory_sources(query=query, db=db, persist=False)
        assert summary.total_sources == 11
        dict_rep = summary.model_dump()
        assert "results" in dict_rep
        assert len(dict_rep["results"]) == 11
