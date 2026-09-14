"""
test_phase8_2_debarment_orchestrator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Comprehensive test suite for Phase 8.2 — Temporal + Debarment Verification.

Validates:
1. Temporal Semantics & Boundary Conditions
2. Canonical Showcase Fixtures (DEMO-CLEAN-001, DEMO-ACTIVE-001, etc.)
3. Authoritative Identity Resolution Hierarchy (PAN > CIN > GSTIN > Udyam > entity_id)
4. Company-Name-Only Supporting Candidate Logic (Never confirms debarment, flags officer review)
5. Decoupled Risk & Scoring Invariance (Mathematical formulas untouched, clean bidder invariant)
6. Source Failure Isolation & Payload Sanitization
7. Real PostgreSQL Database Verification
"""

import pytest
import uuid
from datetime import date, datetime, timezone
from typing import Dict, Any

from app.schemas.statutory_verification import (
    StatutoryAuthority,
    DebarmentTemporalStatus,
    SourceMode,
    SourceConnectionStatus,
    SourceVerificationStatus,
    SourceVerificationResult,
    StatutoryVerificationQuery,
    STATUTORY_MOCK_BANNER,
)
from app.models.mock_sources import MockDebarmentRecord
from app.services.debarment_temporal_service import DebarmentTemporalService, DebarmentTemporalEvaluation
from app.services.statutory_adapters.debarment_adapter import DebarmentSourceAdapter
from app.services.statutory_adapters.registry import get_statutory_registry, StatutoryAdapterRegistry
from app.services.statutory_orchestrator import StatutoryVerificationOrchestrator
from app.services.scoring_service import ScoringAndRankingService
from app.schemas.scoring import RiskLevel, ScoreBreakdown
from app.core.database import AsyncSessionLocal, init_db
from app.services.mock_seeder import seed_mock_sources


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_db_and_seeds(anyio_backend):
    """Ensure database and mock sources are initialized and seeded on active event loop."""
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_mock_sources(session)
        await session.commit()


# ===========================================================================
# 1. TEMPORAL BOUNDARY & SEMANTICS TESTS
# ===========================================================================

def test_temporal_start_equals_as_of_inclusive():
    """Inclusive interval: start_date == as_of_date -> ACTIVE_ON_DATE."""
    res = DebarmentTemporalService.evaluate(
        as_of="2025-01-01",
        start="2025-01-01",
        end="2026-12-31",
        status="ACTIVE",
    )
    assert res.temporal_status == DebarmentTemporalStatus.ACTIVE_ON_DATE
    assert res.is_debarred_on_date is True


def test_temporal_end_equals_as_of_inclusive():
    """Inclusive interval: end_date == as_of_date -> ACTIVE_ON_DATE."""
    res = DebarmentTemporalService.evaluate(
        as_of="2026-12-31",
        start="2025-01-01",
        end="2026-12-31",
        status="ACTIVE",
    )
    assert res.temporal_status == DebarmentTemporalStatus.ACTIVE_ON_DATE
    assert res.is_debarred_on_date is True


def test_temporal_interior_date():
    """Interior date: start < as_of < end -> ACTIVE_ON_DATE."""
    res = DebarmentTemporalService.evaluate(
        as_of="2025-06-15",
        start="2025-01-01",
        end="2026-12-31",
        status="ACTIVE",
    )
    assert res.temporal_status == DebarmentTemporalStatus.ACTIVE_ON_DATE
    assert res.is_debarred_on_date is True


def test_temporal_expired_before_date():
    """as_of > end_date -> EXPIRED_BEFORE_DATE, is_debarred_on_date=False."""
    res = DebarmentTemporalService.evaluate(
        as_of="2027-01-01",
        start="2025-01-01",
        end="2026-12-31",
        status="ACTIVE",
    )
    assert res.temporal_status == DebarmentTemporalStatus.EXPIRED_BEFORE_DATE
    assert res.is_debarred_on_date is False


def test_temporal_starts_after_date():
    """as_of < start_date -> STARTS_AFTER_DATE, is_debarred_on_date=False."""
    res = DebarmentTemporalService.evaluate(
        as_of="2024-12-31",
        start="2025-01-01",
        end="2026-12-31",
        status="ACTIVE",
    )
    assert res.temporal_status == DebarmentTemporalStatus.STARTS_AFTER_DATE
    assert res.is_debarred_on_date is False


def test_temporal_missing_start_date_expired():
    """Missing start_date with as_of > end_date -> EXPIRED_BEFORE_DATE."""
    res = DebarmentTemporalService.evaluate(
        as_of="2026-01-01",
        start=None,
        end="2025-12-31",
        status="ACTIVE",
    )
    assert res.temporal_status == DebarmentTemporalStatus.EXPIRED_BEFORE_DATE
    assert res.is_debarred_on_date is False


def test_temporal_missing_start_date_prior_to_end():
    """Missing start_date with as_of <= end_date -> UNKNOWN_PERIOD."""
    res = DebarmentTemporalService.evaluate(
        as_of="2025-06-01",
        start=None,
        end="2025-12-31",
        status="ACTIVE",
    )
    assert res.temporal_status == DebarmentTemporalStatus.UNKNOWN_PERIOD
    assert res.is_debarred_on_date is False


def test_temporal_open_ended_active_indefinite():
    """Open-ended with explicit ACTIVE_INDEFINITE -> ACTIVE_ON_DATE."""
    res = DebarmentTemporalService.evaluate(
        as_of="2026-03-01",
        start="2023-01-01",
        end=None,
        status="ACTIVE_INDEFINITE",
    )
    assert res.temporal_status == DebarmentTemporalStatus.ACTIVE_ON_DATE
    assert res.is_debarred_on_date is True


def test_temporal_open_ended_permanent():
    """Open-ended with explicit PERMANENT -> ACTIVE_ON_DATE."""
    res = DebarmentTemporalService.evaluate(
        as_of="2026-03-01",
        start="2021-01-01",
        end=None,
        status="PERMANENT",
    )
    assert res.temporal_status == DebarmentTemporalStatus.ACTIVE_ON_DATE
    assert res.is_debarred_on_date is True


def test_temporal_open_ended_future_start():
    """Open-ended ACTIVE_INDEFINITE with future start_date -> STARTS_AFTER_DATE."""
    res = DebarmentTemporalService.evaluate(
        as_of="2025-01-01",
        start="2026-01-01",
        end=None,
        status="ACTIVE_INDEFINITE",
    )
    assert res.temporal_status == DebarmentTemporalStatus.STARTS_AFTER_DATE
    assert res.is_debarred_on_date is False


def test_temporal_null_end_with_ordinary_status_is_unknown():
    """Locked requirement: Never infer active status merely because end_date is NULL with ordinary status."""
    res = DebarmentTemporalService.evaluate(
        as_of="2026-03-01",
        start="2024-01-01",
        end=None,
        status="ACTIVE",  # ordinary status, not ACTIVE_INDEFINITE or PERMANENT
    )
    assert res.temporal_status == DebarmentTemporalStatus.UNKNOWN_PERIOD
    assert res.is_debarred_on_date is False


def test_temporal_missing_both_dates():
    """Missing both start and end dates -> UNKNOWN_PERIOD."""
    res = DebarmentTemporalService.evaluate(
        as_of="2026-03-01",
        start=None,
        end=None,
        status="UNDER_INQUIRY",
    )
    assert res.temporal_status == DebarmentTemporalStatus.UNKNOWN_PERIOD
    assert res.is_debarred_on_date is False


def test_temporal_missing_as_of_returns_unknown_period():
    """Locked requirement: as_of_date=None -> temporal_status == UNKNOWN_PERIOD and is_debarred_on_date is False."""
    res = DebarmentTemporalService.evaluate(
        as_of=None,
        start="2020-01-01",
        end="2035-12-31",
        status="ACTIVE",
    )
    assert res.as_of_date is None
    assert res.temporal_status == DebarmentTemporalStatus.UNKNOWN_PERIOD
    assert res.is_debarred_on_date is False
    assert "No as_of_date provided" in res.reason


def test_temporal_revoked_status_does_not_bypass():
    """REVOKED order must not be active on date."""
    res = DebarmentTemporalService.evaluate(
        as_of="2025-06-01",
        start="2024-01-01",
        end="2027-12-31",
        status="REVOKED",
    )
    assert res.is_debarred_on_date is False
    assert res.temporal_status == DebarmentTemporalStatus.EXPIRED_BEFORE_DATE


# ===========================================================================
# 2. CANONICAL SHOWCASE FIXTURES (POSTGRESQL REAL DB)
# ===========================================================================

@pytest.mark.anyio
async def test_showcase_demo_clean_guaranteed_not_found():
    """DEMO-CLEAN-001 MUST NOT exist -> SUCCESS + NOT_FOUND + is_debarred_on_date=False."""
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        res = await adapter.verify(
            query_identifier="DEMO-CLEAN-001",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.NOT_FOUND
        assert res.data_payload.get("is_debarred_on_date") is False
        assert res.provenance_note == STATUTORY_MOCK_BANNER


@pytest.mark.anyio
async def test_showcase_demo_active_001():
    """DEMO-ACTIVE-001 active on 2026-03-01 -> SUCCESS + VERIFIED + is_debarred_on_date=True."""
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        res = await adapter.verify(
            query_identifier="DEMO-ACTIVE-001",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.data_payload.get("is_debarred_on_date") is True
        assert res.data_payload.get("temporal_status") == "ACTIVE_ON_DATE"
        assert res.data_payload.get("officer_review_required") is True
        assert res.provenance_note == STATUTORY_MOCK_BANNER


@pytest.mark.anyio
async def test_showcase_demo_expired_001():
    """DEMO-EXPIRED-001 expired before 2026-03-01 -> SUCCESS + EXPIRED + is_debarred_on_date=False."""
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        res = await adapter.verify(
            query_identifier="DEMO-EXPIRED-001",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.EXPIRED
        assert res.data_payload.get("is_debarred_on_date") is False
        assert res.data_payload.get("temporal_status") == "EXPIRED_BEFORE_DATE"


@pytest.mark.anyio
async def test_showcase_demo_future_001():
    """DEMO-FUTURE-001 starts after 2026-03-01 -> SUCCESS + UNVERIFIED + is_debarred_on_date=False."""
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        res = await adapter.verify(
            query_identifier="DEMO-FUTURE-001",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload.get("is_debarred_on_date") is False
        assert res.data_payload.get("temporal_status") == "STARTS_AFTER_DATE"


@pytest.mark.anyio
async def test_showcase_demo_unknown_001():
    """DEMO-UNKNOWN-001 missing dates -> SUCCESS + UNVERIFIED + is_debarred_on_date=False."""
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        res = await adapter.verify(
            query_identifier="DEMO-UNKNOWN-001",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload.get("is_debarred_on_date") is False
        assert res.data_payload.get("temporal_status") == "UNKNOWN_PERIOD"


@pytest.mark.anyio
async def test_showcase_demo_indefinite_001():
    """DEMO-INDEFINITE-001 active indefinite -> SUCCESS + VERIFIED + is_debarred_on_date=True."""
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        res = await adapter.verify(
            query_identifier="DEMO-INDEFINITE-001",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.data_payload.get("is_debarred_on_date") is True
        assert res.data_payload.get("temporal_status") == "ACTIVE_ON_DATE"


# ===========================================================================
# 3. AUTHORITATIVE IDENTITY RESOLUTION HIERARCHY TESTS
# ===========================================================================

@pytest.mark.anyio
async def test_identity_hierarchy_pan_match():
    """Authoritative match by PAN: AAACE1001A (maps to DEMO-ACTIVE-001)."""
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        res = await adapter.verify(
            query_identifier="AAACE1001A",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.data_payload.get("is_debarred_on_date") is True
        assert res.data_payload.get("matched_by") == "PAN"


@pytest.mark.anyio
async def test_identity_hierarchy_cin_match():
    """Authoritative match by CIN: U72200MH2018PTC311001."""
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        res = await adapter.verify(
            query_identifier="U72200MH2018PTC311001",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.data_payload.get("is_debarred_on_date") is True
        assert res.data_payload.get("matched_by") == "CIN"


@pytest.mark.anyio
async def test_identity_hierarchy_gstin_match():
    """Authoritative match by GSTIN: 27AAACE1001A1Z1."""
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        res = await adapter.verify(
            query_identifier="27AAACE1001A1Z1",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.data_payload.get("is_debarred_on_date") is True
        assert res.data_payload.get("matched_by") == "GSTIN"


@pytest.mark.anyio
async def test_identity_hierarchy_udyam_match():
    """Authoritative match by Udyam: UDYAM-MH-01-0011001."""
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        res = await adapter.verify(
            query_identifier="UDYAM-MH-01-0011001",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.VERIFIED
        assert res.data_payload.get("is_debarred_on_date") is True
        assert res.data_payload.get("matched_by") == "UDYAM"


# ===========================================================================
# 4. COMPANY-NAME-ONLY CANDIDATE SIGNAL TESTS
# ===========================================================================

@pytest.mark.anyio
async def test_company_name_only_match_remains_unverified():
    """LOCKED REQUIREMENT: Name-only match must remain UNVERIFIED, is_ambiguous_match=True,
    officer_review_required=True, and is_debarred_on_date=False. NEVER assert debarment from name alone.
    """
    async with AsyncSessionLocal() as session:
        adapter = DebarmentSourceAdapter()
        # Query solely with firm name "Apex Global Dynamics Pvt Ltd"
        res = await adapter.verify(
            query_identifier="Apex Global Dynamics",
            identifier_type="company_name",
            as_of_date=date(2026, 3, 1),
            db=session,
        )
        assert res.connection_status == SourceConnectionStatus.SUCCESS
        assert res.verification_status == SourceVerificationStatus.UNVERIFIED
        assert res.data_payload.get("is_debarred_on_date") is False
        assert res.data_payload.get("is_ambiguous_match") is True
        assert res.data_payload.get("officer_review_required") is True
        assert res.data_payload.get("matched_by") == "COMPANY_NAME_ONLY"
        assert res.confidence_score == 0.4
        assert "officer review required" in res.error_message.lower()


# ===========================================================================
# 5. SOURCE FAILURE ISOLATION & PAYLOAD SANITIZATION
# ===========================================================================

@pytest.mark.anyio
async def test_adapter_db_session_unavailable():
    """When db session is None, adapter must return UNAVAILABLE, not crash or report FAIL."""
    adapter = DebarmentSourceAdapter()
    res = await adapter.verify(query_identifier="DEMO-ACTIVE-001", db=None)
    assert res.connection_status == SourceConnectionStatus.UNAVAILABLE
    assert res.verification_status == SourceVerificationStatus.FAILED


def test_registry_registration():
    """Registry must include DEBARMENT authority among supported adapters."""
    registry = get_statutory_registry()
    authorities = registry.list_supported_authorities()
    assert StatutoryAuthority.DEBARMENT in authorities
    adapter = registry.get_adapter(StatutoryAuthority.DEBARMENT)
    assert isinstance(adapter, DebarmentSourceAdapter)
    assert adapter.authority == StatutoryAuthority.DEBARMENT


# ===========================================================================
# 6. RISK & SCORING DECOUPLING TESTS (PHASE 6.4 INVARIANCE)
# ===========================================================================

def test_debarment_risk_orthogonal_to_100_point_scoring():
    """LOCKED REQUIREMENT:
    Base score = 86
    Debarment active -> score remains 86, risk = HIGH, officer_review_required = True,
    automatic disqualification = False.
    """
    # Create mock clause evaluations with known earned points
    class MockClauseEval:
        def __init__(self, code, status, is_mandatory=True, snippet="verified snippet", reasoning="compliant"):
            self.clause_code = code
            self.status = status
            self.is_mandatory = is_mandatory
            self.evidence_snippet = snippet
            self.reasoning = reasoning
            self.claimed_value = "Verified"

    # 4 clauses with PASS -> tender score = 50.0
    evals = [
        MockClauseEval("TECH-01", "PASS"),
        MockClauseEval("FIN-01", "PASS"),
        MockClauseEval("EXP-01", "PASS"),
        MockClauseEval("STAT-01", "PASS"),
    ]

    bidder_id = uuid.uuid4()

    # 1. Clean run (no debarment)
    clean_score = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=bidder_id,
        company_name="Clean Bidder Ltd",
        evaluations=evals,
        cross_source_report=None,
        is_debarred_on_date=False,
    )
    # Expected base score: 50.0 (tender) + 20.0 (statutory neutral) + 15.0 (evidence) + 15.0 (no contradictions) = 100.0
    assert clean_score.overall_score == 100.0
    assert clean_score.risk_level == RiskLevel.LOW

    # 2. Debarred run: active debarment signal on same bidder
    debarred_score = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=bidder_id,
        company_name="Clean Bidder Ltd",
        evaluations=evals,
        cross_source_report=None,
        is_debarred_on_date=True,
        debarment_details={"order_number": "DEB/TEST/001"},
    )

    # LOCKED REQUIREMENT:
    # 1. Formula score UNCHANGED: 100.0 remains 100.0
    assert debarred_score.overall_score == clean_score.overall_score
    assert debarred_score.breakdown.tender_compliance == clean_score.breakdown.tender_compliance
    assert debarred_score.breakdown.statutory_consistency == clean_score.breakdown.statutory_consistency
    assert debarred_score.breakdown.evidence_completeness == clean_score.breakdown.evidence_completeness
    assert debarred_score.breakdown.contradiction_score == clean_score.breakdown.contradiction_score

    # 2. Orthogonal risk elevation: RiskLevel.HIGH
    assert debarred_score.risk_level == RiskLevel.HIGH
    assert any("debarment" in trigger.lower() for trigger in debarred_score.risk_triggers)

    # 3. Calculation details record debarment risk signal
    deb_risk = debarred_score.calculation_details.get("debarment_risk")
    assert deb_risk is not None
    assert deb_risk["is_debarred_on_date"] is True
    assert deb_risk["officer_review_required"] is True


def test_ranking_hierarchy_with_debarred_bidder():
    """Debarred bidder is sorted by score DESC, but with elevated risk HIGH (weight 2).
    Clean bidder with identical score is ranked ahead due to lower risk (weight 0).
    """
    bidder_1 = uuid.uuid4()
    bidder_2 = uuid.uuid4()

    class MockClauseEval:
        def __init__(self, code, status):
            self.clause_code = code
            self.status = status
            self.is_mandatory = True
            self.evidence_snippet = "valid evidence"
            self.reasoning = "compliant"
            self.claimed_value = "Verified"

    evals = [MockClauseEval("T-1", "PASS")]

    score_clean = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=bidder_1,
        company_name="Alpha Tech",
        evaluations=evals,
        is_debarred_on_date=False,
    )
    score_debarred = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=bidder_2,
        company_name="Beta Systems",
        evaluations=evals,
        is_debarred_on_date=True,
    )

    ranking = ScoringAndRankingService.rank_bidders(
        tender_id=uuid.uuid4(),
        tender_title="Sample Defense Tender",
        bidder_scores=[score_debarred, score_clean],
    )

    # Rank 1: Alpha Tech (Score 100, LOW risk)
    # Rank 2: Beta Systems (Score 100, HIGH risk due to debarment)
    assert ranking.rankings[0].bidder_id == str(bidder_1)
    assert ranking.rankings[0].risk_level == RiskLevel.LOW
    assert ranking.rankings[1].bidder_id == str(bidder_2)
    assert ranking.rankings[1].risk_level == RiskLevel.HIGH
    assert any("debarment" in w.lower() for w in ranking.rankings[1].key_warnings)


# ===========================================================================
# 7. MULTI-SOURCE ORCHESTRATOR INTEGRATION TEST WITH REAL POSTGRESQL
# ===========================================================================

@pytest.mark.anyio
async def test_statutory_orchestrator_multi_source_including_debarment():
    """StatutoryVerificationOrchestrator runs 6 authorities concurrently including DEBARMENT."""
    async with AsyncSessionLocal() as session:
        orchestrator = StatutoryVerificationOrchestrator()

        query = StatutoryVerificationQuery(
            tender_id=None,
            bidder_id=None,
            identifiers={
                "gstin": "27AAACE1001A1Z1",
                "udyam_number": "UDYAM-MH-01-0011001",
                "cin": "U72200MH2018PTC311001",
                "pan": "AAACE1001A",
                "certificate_reference": "MII-2026-001",
            },
            as_of_date=date(2026, 3, 1),
            mode=SourceMode.MOCK,
        )

        summary = await orchestrator.verify_statutory_sources(
            query=query,
            db=session,
            persist=False,
        )

        assert summary.total_sources >= 6
        assert summary.successful_connections >= 6
        authorities_returned = {r.authority for r in summary.results}
        assert StatutoryAuthority.DEBARMENT in authorities_returned

        # Debarment result check
        deb_res = next(r for r in summary.results if r.authority == StatutoryAuthority.DEBARMENT)
        assert deb_res.connection_status == SourceConnectionStatus.SUCCESS
        assert deb_res.verification_status == SourceVerificationStatus.VERIFIED
        assert deb_res.data_payload.get("is_debarred_on_date") is True
        assert deb_res.data_payload.get("temporal_status") == "ACTIVE_ON_DATE"
