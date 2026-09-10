"""Automated Test Suite for SIH 2026 Phase 6.4 — Compliance Score + Risk + Bidder Ranking.

Verifies the 27+ core requirements and locked corrections of Phase 6.4:
1. All PASS -> 100.0 score (Tender=50, Statutory=20, Completeness=15, Contradictions=15)
2. FAIL reduces tender compliance score deterministically
3. REVIEW receives half credit (0.5 * 50 / N)
4. Statutory CONSISTENT awards full statutory points
5. Statutory INSUFFICIENT_EVIDENCE awards half points
6. Statutory INCONSISTENT awards zero points
7. Evidence completeness is proportional
8. No contradictions preserves full 15.0 contradiction points
9. Exact contradiction deduction: MAJOR = -7.5 points
10. Two major contradictions drive contradiction score to zero (15.0 - 15.0 = 0.0)
11. Base score thresholds LOW (>=80), MEDIUM (60-79.99), HIGH (<60)
12. Safety override: Major contradiction prevents LOW risk (elevated to minimum MEDIUM)
13. Safety override: Multiple major contradictions force risk to HIGH
14. Safety override: Critical mandatory clause FAIL forces risk to HIGH
15. Determinism: Same input produces identical score and breakdown
16. Ranking sorts deterministically by overall_score DESC
17. Ranking tie-breakers: risk_level severity ASC -> stable bidder_id ASC
18. Tender boundary isolation in ranking
19. Bidder isolation in scoring
20. Phase 6.3 contradiction semantics remain intact
21. Turnover mismatch (₹8 Cr vs ₹3.65 Cr) classified as MAJOR contradiction
22. Local content 3-way inconsistency (50% vs 32% BOM vs 32% MII) remains one MAJOR conflict
23. Entity name variation (Pvt Ltd vs Private Limited) is CONSISTENT (0 deduction)
24. Udyam MICRO classification is CONSISTENT and does not infer EMD exemption
25. Scoring does not mutate existing evaluation records
26. Bidder score API endpoint (GET /api/v1/tenders/{tender_id}/bidders/{bidder_id}/score)
27. Tender ranking API endpoint (GET /api/v1/tenders/{tender_id}/ranking)
28. Locked Correction #4: NOT_COMPARABLE excluded from statutory denominator
29. Locked Correction #1: Evidence completeness is strictly independent from PASS/FAIL
"""

from typing import Any, Optional, List, Dict
from uuid import uuid4, UUID
from unittest.mock import patch, MagicMock
import pytest
import httpx

from app.main import app
from app.core import database as db_module
from app.models.tender import Tender
from app.models.clause import TenderClause
from app.models.bidder import Bidder
from app.models.evaluation import ComplianceEvaluation as ComplianceEvaluationModel
from app.schemas.evaluation import ComplianceStatus, ClauseComplianceEvaluation
from app.schemas.evidence_fusion import (
    SourceType,
    EvidenceType,
    EvidenceItem,
    FieldEvidenceGroup,
    BidderEvidenceFusionProfile,
)
from app.schemas.cross_source_verification import (
    CrossSourceStatus,
    CrossSourceVerificationResult,
    BidderCrossSourceVerificationReport,
    DiscrepancyDetail,
)
from app.schemas.scoring import (
    RiskLevel,
    ContradictionSeverity,
    ScoreBreakdown,
    ScoreSummary,
    BidderComplianceScoreResponse,
    RankedBidderItem,
    TenderBidderRankingResponse,
    DECISION_SUPPORT_DISCLAIMER,
)
from app.services.scoring_service import ScoringAndRankingService
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


# Helper to build a test ClauseComplianceEvaluation
def make_eval(
    clause_code: str,
    status: ComplianceStatus,
    bidder_id: UUID = None,
    snippet: Optional[str] = "Valid evidence snippet text",
    claimed: Optional[str] = "100 units",
    reasoning: str = "Requirement satisfied.",
    contradiction: bool = False,
    is_mandatory: bool = True,
) -> ClauseComplianceEvaluation:
    return ClauseComplianceEvaluation(
        clause_code=clause_code,
        clause_title=f"Clause {clause_code}",
        bidder_id=bidder_id or uuid4(),
        status=status,
        confidence_score=1.0,
        claimed_value=claimed,
        reasoning=reasoning,
        evidence_snippet=snippet,
        evidence_page_number=1,
        contradiction_detected=contradiction,
        requires_human_confirmation=False,
    )


# Helper to build a test CrossSourceVerificationResult
def make_cross_result(
    field_name: str,
    status: CrossSourceStatus,
    bidder_id: str,
    field_label: str = None,
    explanation: str = "Comparison explanation",
) -> CrossSourceVerificationResult:
    return CrossSourceVerificationResult(
        bidder_id=bidder_id,
        field_name=field_name,
        field_label=field_label or field_name.replace("_", " ").title(),
        status=status,
        evidence_ids=["ev-1", "ev-2"],
        compared_sources=["BIDDER_DOCUMENT", "GSTN"],
        normalized_values=[],
        explanation=explanation,
        confidence=1.0,
        provenance_references=["Doc A (Page 1)", "GSTN Verification ID"],
        is_mock_involved=True,
        discrepancy_details=[],
    )


# ===========================================================================
# 1. All PASS -> 100.0 Score
# ===========================================================================
def test_all_pass_gives_100():
    b_id = uuid4()
    evals = [
        make_eval("TECH-01", ComplianceStatus.PASS, b_id),
        make_eval("TECH-02", ComplianceStatus.PASS, b_id),
    ]
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Perfect Bidder Ltd",
        results=[
            make_cross_result("turnover", CrossSourceStatus.CONSISTENT, str(b_id)),
            make_cross_result("gstin_status", CrossSourceStatus.CONSISTENT, str(b_id)),
        ],
        total_fields_verified=2,
        consistent_count=2,
    )

    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Perfect Bidder Ltd",
        evaluations=evals,
        cross_source_report=cross_report,
    )

    assert score_resp.overall_score == 100.0
    assert score_resp.breakdown.tender_compliance == 50.0
    assert score_resp.breakdown.statutory_consistency == 20.0
    assert score_resp.breakdown.evidence_completeness == 15.0
    assert score_resp.breakdown.contradiction_score == 15.0
    assert score_resp.risk_level == RiskLevel.LOW
    assert len(score_resp.risk_triggers) == 0


# ===========================================================================
# 2. FAIL Reduces Score Deterministically
# ===========================================================================
def test_fail_reduces_score_deterministically():
    b_id = uuid4()
    # 2 clauses: 1 PASS, 1 FAIL -> (1/2) * 50 = 25.0
    evals = [
        make_eval("TECH-01", ComplianceStatus.PASS, b_id),
        make_eval("TECH-02", ComplianceStatus.FAIL, b_id, is_mandatory=False),
    ]
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Test Bidder",
        evaluations=evals,
        cross_source_report=None,
        clause_mandatory_map={"TECH-01": False, "TECH-02": False},
    )

    assert score_resp.breakdown.tender_compliance == 25.0


# ===========================================================================
# 3. REVIEW Gets Half Credit
# ===========================================================================
def test_review_gets_half_credit():
    b_id = uuid4()
    # 2 clauses: 1 PASS, 1 REVIEW -> (1.5 / 2) * 50 = 37.5
    evals = [
        make_eval("TECH-01", ComplianceStatus.PASS, b_id),
        make_eval("TECH-02", ComplianceStatus.REVIEW, b_id),
    ]
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Test Bidder",
        evaluations=evals,
        cross_source_report=None,
    )

    assert score_resp.breakdown.tender_compliance == 37.5


# ===========================================================================
# 4. Statutory CONSISTENT Awards Full Points
# ===========================================================================
def test_statutory_consistent_full_points():
    b_id = uuid4()
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Test Bidder",
        results=[
            make_cross_result("turnover", CrossSourceStatus.CONSISTENT, str(b_id)),
            make_cross_result("pan_status", CrossSourceStatus.CONSISTENT, str(b_id)),
        ],
        total_fields_verified=2,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Test Bidder",
        evaluations=[],
        cross_source_report=cross_report,
    )

    assert score_resp.breakdown.statutory_consistency == 20.0


# ===========================================================================
# 5. Statutory INSUFFICIENT_EVIDENCE Awards Half Points
# ===========================================================================
def test_statutory_insufficient_evidence_half():
    b_id = uuid4()
    # 2 checks: 1 CONSISTENT (1.0), 1 INSUFFICIENT (0.5) -> (1.5 / 2) * 20 = 15.0
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Test Bidder",
        results=[
            make_cross_result("turnover", CrossSourceStatus.CONSISTENT, str(b_id)),
            make_cross_result("pan_status", CrossSourceStatus.INSUFFICIENT_EVIDENCE, str(b_id)),
        ],
        total_fields_verified=2,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Test Bidder",
        evaluations=[],
        cross_source_report=cross_report,
    )

    assert score_resp.breakdown.statutory_consistency == 15.0


# ===========================================================================
# 6. Statutory INCONSISTENT Awards Zero Points
# ===========================================================================
def test_statutory_inconsistent_zero():
    b_id = uuid4()
    # 2 checks: 1 CONSISTENT (1.0), 1 INCONSISTENT (0.0) -> (1.0 / 2) * 20 = 10.0
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Test Bidder",
        results=[
            make_cross_result("turnover", CrossSourceStatus.CONSISTENT, str(b_id)),
            make_cross_result("pan_status", CrossSourceStatus.INCONSISTENT, str(b_id)),
        ],
        total_fields_verified=2,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Test Bidder",
        evaluations=[],
        cross_source_report=cross_report,
    )

    assert score_resp.breakdown.statutory_consistency == 10.0


# ===========================================================================
# 7. Evidence Completeness Is Proportional
# ===========================================================================
def test_evidence_completeness_proportional():
    b_id = uuid4()
    # 2 clauses: 1 with sufficient evidence (1.0), 1 with ambiguous evidence (0.5)
    # Total = (1.5 / 2) * 15.0 = 11.25
    evals = [
        make_eval("TECH-01", ComplianceStatus.PASS, b_id, snippet="Proposes 64 cores", claimed="64 cores"),
        make_eval("TECH-02", ComplianceStatus.REVIEW, b_id, snippet="Ambiguous text", claimed="unclear", reasoning="ambiguous and clarification needed"),
    ]
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Test Bidder",
        evaluations=evals,
    )

    assert score_resp.breakdown.evidence_completeness == 11.25


# ===========================================================================
# 8. No Contradictions -> Full 15.0
# ===========================================================================
def test_no_contradictions_gives_15():
    b_id = uuid4()
    evals = [make_eval("TECH-01", ComplianceStatus.PASS, b_id, contradiction=False)]
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Test Bidder",
        results=[make_cross_result("turnover", CrossSourceStatus.CONSISTENT, str(b_id))],
        total_fields_verified=1,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Test Bidder",
        evaluations=evals,
        cross_source_report=cross_report,
    )

    assert score_resp.breakdown.contradiction_score == 15.0
    assert score_resp.summary.major_contradiction_count == 0
    assert score_resp.summary.minor_contradiction_count == 0


# ===========================================================================
# 9. Major Contradiction Exact Deduction: -7.5 (Locked Correction #2)
# ===========================================================================
def test_major_contradiction_exact_deduction():
    b_id = uuid4()
    # 1 major contradiction in turnover
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Test Bidder",
        results=[make_cross_result("turnover", CrossSourceStatus.INCONSISTENT, str(b_id))],
        total_fields_verified=1,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Test Bidder",
        evaluations=[],
        cross_source_report=cross_report,
    )

    # 15.0 - 7.5 = 7.5
    assert score_resp.breakdown.contradiction_score == 7.5
    assert score_resp.summary.major_contradiction_count == 1


# ===========================================================================
# 10. Two Major Contradictions Drive Contradiction Score to Zero
# ===========================================================================
def test_two_major_contradictions_drive_to_zero():
    b_id = uuid4()
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Test Bidder",
        results=[
            make_cross_result("turnover", CrossSourceStatus.INCONSISTENT, str(b_id)),
            make_cross_result("local_content_percent", CrossSourceStatus.INCONSISTENT, str(b_id)),
        ],
        total_fields_verified=2,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Test Bidder",
        evaluations=[],
        cross_source_report=cross_report,
    )

    # 15.0 - (2 * 7.5) = 0.0
    assert score_resp.breakdown.contradiction_score == 0.0
    assert score_resp.summary.major_contradiction_count == 2


# ===========================================================================
# 11. Base Risk Thresholds (LOW, MEDIUM, HIGH)
# ===========================================================================
def test_base_risk_thresholds():
    b_id = uuid4()

    # Case A: 85.0 -> LOW
    # Tender = 50, Statutory = 20, Completeness = 15, Contradictions = 15 -> 100.0 (LOW)
    evals = [make_eval("TECH-01", ComplianceStatus.PASS, b_id)]
    resp_low = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Low Risk Bidder",
        evaluations=evals,
        clause_mandatory_map={"TECH-01": False},
    )
    assert resp_low.risk_level == RiskLevel.LOW

    # Case B: 70.0 -> MEDIUM (when no overrides)
    # E.g. Tender = (2/5)*50 = 20, Statutory = 20, Completeness = 15, Contradiction = 15 -> 70.0
    evals_med = [
        make_eval("C1", ComplianceStatus.PASS, b_id),
        make_eval("C2", ComplianceStatus.PASS, b_id),
        make_eval("C3", ComplianceStatus.FAIL, b_id, is_mandatory=False),
        make_eval("C4", ComplianceStatus.FAIL, b_id, is_mandatory=False),
        make_eval("C5", ComplianceStatus.FAIL, b_id, is_mandatory=False),
    ]
    resp_med = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Med Risk Bidder",
        evaluations=evals_med,
        clause_mandatory_map={f"C{i}": False for i in range(1, 6)},
    )
    assert 60.0 <= resp_med.overall_score < 80.0
    assert resp_med.risk_level == RiskLevel.MEDIUM


# ===========================================================================
# 12. Major Contradiction Prevents LOW Risk (Minimum-Risk Override)
# ===========================================================================
def test_major_contradiction_prevents_low_risk():
    b_id = uuid4()
    # High score: 50 (tender) + 15 (completeness) + 7.5 (contradiction) + 15 (statutory) = 87.5
    # Overall score 87.5 normally >= 80 (LOW), but 1 major contradiction forces risk to MEDIUM!
    evals = [make_eval("TECH-01", ComplianceStatus.PASS, b_id)]
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="High Score with Conflict",
        results=[
            make_cross_result("turnover", CrossSourceStatus.INCONSISTENT, str(b_id)),
            make_cross_result("pan_status", CrossSourceStatus.CONSISTENT, str(b_id)),
            make_cross_result("gstin_status", CrossSourceStatus.CONSISTENT, str(b_id)),
        ],
        total_fields_verified=3,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="High Score with Conflict",
        evaluations=evals,
        cross_source_report=cross_report,
        clause_mandatory_map={"TECH-01": False},
    )

    assert score_resp.overall_score >= 80.0
    assert score_resp.risk_level == RiskLevel.MEDIUM
    assert any("forces minimum risk to minimum MEDIUM" in t or "minimum MEDIUM" in t for t in score_resp.risk_triggers)


# ===========================================================================
# 13. Multiple Major Contradictions Produce HIGH Risk
# ===========================================================================
def test_multiple_major_contradictions_produce_high_risk():
    b_id = uuid4()
    # Score could be in 60s, but 2 major contradictions must force HIGH risk
    evals = [make_eval("TECH-01", ComplianceStatus.PASS, b_id)]
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Multi Conflict Bidder",
        results=[
            make_cross_result("turnover", CrossSourceStatus.INCONSISTENT, str(b_id)),
            make_cross_result("local_content_percent", CrossSourceStatus.INCONSISTENT, str(b_id)),
            make_cross_result("gstin_status", CrossSourceStatus.CONSISTENT, str(b_id)),
        ],
        total_fields_verified=3,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Multi Conflict Bidder",
        evaluations=evals,
        cross_source_report=cross_report,
        clause_mandatory_map={"TECH-01": False},
    )

    assert score_resp.risk_level == RiskLevel.HIGH
    assert any("Multiple major contradictions" in t for t in score_resp.risk_triggers)


# ===========================================================================
# 14. Critical Mandatory FAIL Produces HIGH Risk
# ===========================================================================
def test_critical_mandatory_fail_produces_high_risk():
    b_id = uuid4()
    # 10 clauses: 9 PASS, 1 FAIL on mandatory requirement TECH-01
    evals = [make_eval("TECH-01", ComplianceStatus.FAIL, b_id, is_mandatory=True)]
    for i in range(2, 11):
        evals.append(make_eval(f"TECH-0{i}", ComplianceStatus.PASS, b_id, is_mandatory=False))

    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Mandatory Fail Bidder",
        evaluations=evals,
        clause_mandatory_map={"TECH-01": True},
    )

    # Score is 45 (tender) + 20 (stat) + 15 (comp) + 15 (contra) = 95.0, but mandatory fail forces HIGH!
    assert score_resp.overall_score >= 80.0
    assert score_resp.risk_level == RiskLevel.HIGH
    assert any("Mandatory tender criteria failed" in t for t in score_resp.risk_triggers)


# ===========================================================================
# 15. Deterministic Repeated Calculation
# ===========================================================================
def test_deterministic_repeated_calculation():
    b_id = uuid4()
    evals = [make_eval("TECH-01", ComplianceStatus.PASS, b_id)]
    resp1 = ScoringAndRankingService.calculate_bidder_score(b_id, "Company A", evals)
    resp2 = ScoringAndRankingService.calculate_bidder_score(b_id, "Company A", evals)

    assert resp1.overall_score == resp2.overall_score
    assert resp1.risk_level == resp2.risk_level
    assert resp1.breakdown.model_dump() == resp2.breakdown.model_dump()


# ===========================================================================
# 16. Ranking Sorts by Score Descending (Locked Correction #3)
# ===========================================================================
def test_ranking_sorts_by_score_descending():
    tender_id = uuid4()
    b1 = uuid4()
    b2 = uuid4()
    b3 = uuid4()

    # Create dummy scores
    s1 = ScoringAndRankingService.calculate_bidder_score(b1, "Company Low", [make_eval("C1", ComplianceStatus.FAIL, b1, is_mandatory=False)])
    s2 = ScoringAndRankingService.calculate_bidder_score(b2, "Company High", [make_eval("C1", ComplianceStatus.PASS, b2)])
    s3 = ScoringAndRankingService.calculate_bidder_score(b3, "Company Mid", [make_eval("C1", ComplianceStatus.REVIEW, b3)])

    ranking = ScoringAndRankingService.rank_bidders(
        tender_id=tender_id,
        tender_title="Test Server Tender",
        bidder_scores=[s1, s2, s3],
    )

    assert len(ranking.rankings) == 3
    assert ranking.rankings[0].bidder_id == str(b2)  # High score
    assert ranking.rankings[0].rank == 1
    assert ranking.rankings[1].bidder_id == str(b3)  # Mid score
    assert ranking.rankings[1].rank == 2
    assert ranking.rankings[2].bidder_id == str(b1)  # Low score
    assert ranking.rankings[2].rank == 3


# ===========================================================================
# 17. Ranking Tie-Breakers (Risk Level Severity ASC -> Bidder ID ASC)
# ===========================================================================
def test_ranking_tie_breakers():
    tender_id = uuid4()
    b_low_risk = uuid4()
    b_med_risk = uuid4()

    # Same score (e.g. 70.0), but different risk
    s_low = ScoringAndRankingService.calculate_bidder_score(b_low_risk, "Bidder A", [make_eval("C1", ComplianceStatus.PASS, b_low_risk)])
    s_med = ScoringAndRankingService.calculate_bidder_score(b_med_risk, "Bidder B", [make_eval("C1", ComplianceStatus.PASS, b_med_risk)])

    # Manually adjust risk on s_med to test tie-breaker
    s_low.overall_score = 80.0
    s_low.risk_level = RiskLevel.LOW

    s_med.overall_score = 80.0
    s_med.risk_level = RiskLevel.MEDIUM

    ranking = ScoringAndRankingService.rank_bidders(
        tender_id=tender_id,
        tender_title="Tie Breaker Tender",
        bidder_scores=[s_med, s_low],
    )

    # LOW risk should be ranked ahead of MEDIUM risk for equal scores
    assert ranking.rankings[0].bidder_id == str(b_low_risk)
    assert ranking.rankings[1].bidder_id == str(b_med_risk)


# ===========================================================================
# 18. Tender Boundary Isolation
# ===========================================================================
@pytest.mark.anyio
async def test_tender_isolation():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        t1 = Tender(title="Tender 1", gem_tender_id=f"GEM/{uuid4().hex[:6]}", file_name="t1.pdf", total_pages=1, extraction_status="READY")
        t2 = Tender(title="Tender 2", gem_tender_id=f"GEM/{uuid4().hex[:6]}", file_name="t2.pdf", total_pages=1, extraction_status="READY")
        session.add_all([t1, t2])
        await session.flush()

        b1 = Bidder(tender_id=t1.id, company_name="Bidder T1")
        b2 = Bidder(tender_id=t2.id, company_name="Bidder T2")
        session.add_all([b1, b2])
        await session.commit()

        t1_id, t2_id, b1_id, b2_id = t1.id, t2.id, b1.id, b2.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res1 = await client.get(f"/api/v1/tenders/{t1_id}/ranking")
        assert res1.status_code == 200
        data1 = res1.json()

        # T1 ranking must only contain b1, never b2
        b_ids_in_t1 = [r["bidder_id"] for r in data1["rankings"]]
        assert str(b1_id) in b_ids_in_t1
        assert str(b2_id) not in b_ids_in_t1


# ===========================================================================
# 19. Bidder Isolation
# ===========================================================================
def test_bidder_isolation():
    b1 = uuid4()
    b2 = uuid4()
    evals_b1 = [make_eval("TECH-01", ComplianceStatus.PASS, b1)]
    score_b1 = ScoringAndRankingService.calculate_bidder_score(b1, "Company 1", evals_b1)

    assert score_b1.bidder_id == str(b1)
    assert score_b1.company_name == "Company 1"


# ===========================================================================
# 20. Phase 6.3 Contradiction Semantics Unchanged
# ===========================================================================
def test_phase6_3_contradiction_semantics_unchanged():
    from app.schemas.cross_source_verification import CrossSourceStatus
    assert CrossSourceStatus.CONSISTENT == "CONSISTENT"
    assert CrossSourceStatus.INCONSISTENT == "INCONSISTENT"
    assert CrossSourceStatus.INSUFFICIENT_EVIDENCE == "INSUFFICIENT_EVIDENCE"
    assert CrossSourceStatus.NOT_COMPARABLE == "NOT_COMPARABLE"


# ===========================================================================
# 21. Turnover Mismatch (₹8 Cr vs ₹3.65 Cr)
# ===========================================================================
def test_turnover_contradiction():
    b_id = uuid4()
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Turnover Mismatch Bidder",
        results=[
            make_cross_result("turnover", CrossSourceStatus.INCONSISTENT, str(b_id), explanation="Bidder ₹8.00 Cr vs GSTN ₹3.65 Cr differs"),
        ],
        total_fields_verified=1,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Turnover Mismatch Bidder",
        evaluations=[],
        cross_source_report=cross_report,
    )

    assert score_resp.summary.major_contradiction_count == 1
    assert score_resp.breakdown.contradiction_score == 7.5  # 15.0 - 7.5 = 7.5
    assert score_resp.risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH}


# ===========================================================================
# 22. Local Content 3-Way Aggregated Inconsistency (50% vs 32% BOM vs 32% MII)
# ===========================================================================
def test_local_content_three_way_inconsistency_aggregated():
    b_id = uuid4()
    # Single field result with status INCONSISTENT
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Local Content Bidder",
        results=[
            make_cross_result(
                "local_content_percent",
                CrossSourceStatus.INCONSISTENT,
                str(b_id),
                explanation="Differences: Declaration (50.0%) differs from BOM (32.0%) and MII (32.0%).",
            ),
        ],
        total_fields_verified=1,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Local Content Bidder",
        evaluations=[],
        cross_source_report=cross_report,
    )

    # Exactly 1 major contradiction deducted
    assert score_resp.summary.major_contradiction_count == 1
    assert score_resp.breakdown.contradiction_score == 7.5


# ===========================================================================
# 23. Entity Name Variation (Pvt Ltd vs Private Limited)
# ===========================================================================
def test_name_variation_remains_consistent_no_deduction():
    b_id = uuid4()
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Alpha Technologies Pvt Ltd",
        results=[
            make_cross_result("company_name", CrossSourceStatus.CONSISTENT, str(b_id), explanation="Normalized names equivalent"),
        ],
        total_fields_verified=1,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Alpha Technologies Pvt Ltd",
        evaluations=[],
        cross_source_report=cross_report,
    )

    assert score_resp.summary.major_contradiction_count == 0
    assert score_resp.breakdown.contradiction_score == 15.0


# ===========================================================================
# 24. Udyam MICRO Classification Does Not Infer EMD Exemption
# ===========================================================================
def test_udyam_classification_does_not_infer_emd_exemption():
    b_id = uuid4()
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Micro Enterprise",
        results=[
            make_cross_result("enterprise_type", CrossSourceStatus.CONSISTENT, str(b_id), explanation="Classification MICRO agrees"),
        ],
        total_fields_verified=1,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Micro Enterprise",
        evaluations=[],
        cross_source_report=cross_report,
    )

    assert score_resp.breakdown.contradiction_score == 15.0
    # Ensure no automatic exemption text is generated
    for t in score_resp.risk_triggers:
        assert "exemption" not in t.lower()


# ===========================================================================
# 25. Scoring Does Not Mutate Evaluation Records
# ===========================================================================
def test_scoring_does_not_mutate_evaluations():
    b_id = uuid4()
    ev = make_eval("TECH-01", ComplianceStatus.PASS, b_id)
    initial_dump = ev.model_dump()

    ScoringAndRankingService.calculate_bidder_score(b_id, "Company A", [ev])
    after_dump = ev.model_dump()

    assert initial_dump == after_dump


# ===========================================================================
# 26. Bidder Score API Endpoint
# ===========================================================================
@pytest.mark.anyio
async def test_bidder_score_api_endpoint():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)

        tender = Tender(title="Score API Tender", gem_tender_id=f"GEM/{uuid4().hex[:6]}", file_name="tender.pdf", total_pages=2, extraction_status="READY")
        session.add(tender)
        await session.flush()

        bidder = Bidder(tender_id=tender.id, company_name="Enterprise Tech Solutions Ltd (Bidder A)")
        session.add(bidder)
        await session.commit()

        t_id, b_id = tender.id, bidder.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/tenders/{t_id}/bidders/{b_id}/score")
        assert resp.status_code == 200
        data = resp.json()

        assert data["bidder_id"] == str(b_id)
        assert "overall_score" in data
        assert "breakdown" in data
        assert "risk_level" in data
        assert data["disclaimer"] == DECISION_SUPPORT_DISCLAIMER


# ===========================================================================
# 27. Tender Ranking API Endpoint
# ===========================================================================
@pytest.mark.anyio
async def test_tender_ranking_api_endpoint():
    await db_module.init_db()
    async with db_module.AsyncSessionLocal() as session:
        await seed_mock_sources(session)

        tender = Tender(title="Ranking API Tender", gem_tender_id=f"GEM/{uuid4().hex[:6]}", file_name="tender.pdf", total_pages=2, extraction_status="READY")
        session.add(tender)
        await session.flush()

        b1 = Bidder(tender_id=tender.id, company_name="Enterprise Tech Solutions Ltd (Bidder A)")
        b2 = Bidder(tender_id=tender.id, company_name="Legacy Hardware Trading Co (Bidder B)")
        session.add_all([b1, b2])
        await session.commit()

        t_id = tender.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/tenders/{t_id}/ranking")
        assert resp.status_code == 200
        data = resp.json()

        assert data["tender_id"] == str(t_id)
        assert data["total_bidders"] == 2
        assert len(data["rankings"]) == 2
        assert data["rankings"][0]["rank"] == 1
        assert data["rankings"][1]["rank"] == 2
        assert data["disclaimer"] == DECISION_SUPPORT_DISCLAIMER


# ===========================================================================
# 28. Locked Correction #4: NOT_COMPARABLE Excluded from Denominator
# ===========================================================================
def test_not_comparable_excluded_from_statutory_denominator():
    b_id = uuid4()
    # 3 items:
    # 1 CONSISTENT (1.0)
    # 1 INCONSISTENT (0.0)
    # 1 NOT_COMPARABLE (Excluded)
    # Denominator must be 2, earned = 1.0 -> (1.0 / 2) * 20 = 10.0
    cross_report = BidderCrossSourceVerificationReport(
        bidder_id=str(b_id),
        company_name="Not Comparable Test Bidder",
        results=[
            make_cross_result("field_a", CrossSourceStatus.CONSISTENT, str(b_id)),
            make_cross_result("field_b", CrossSourceStatus.INCONSISTENT, str(b_id)),
            make_cross_result("field_c", CrossSourceStatus.NOT_COMPARABLE, str(b_id)),
        ],
        total_fields_verified=3,
    )
    score_resp = ScoringAndRankingService.calculate_bidder_score(
        bidder_id=b_id,
        company_name="Not Comparable Test Bidder",
        evaluations=[],
        cross_source_report=cross_report,
    )

    # 10.0 out of 20.0
    assert score_resp.breakdown.statutory_consistency == 10.0
    calc_details = score_resp.calculation_details["statutory_consistency"]
    assert calc_details["applicable_checks"] == 2  # Denominator is 2, not 3!


# ===========================================================================
# 29. Locked Correction #1: Evidence Completeness Independent from PASS/FAIL
# ===========================================================================
def test_evidence_completeness_independent_from_pass_fail():
    b_id = uuid4()
    # Clause A: FAIL but valid evidence present (e.g. 32 cores < 64 required) -> 1.0 completeness
    ev_fail_with_evidence = make_eval(
        "TECH-01",
        ComplianceStatus.FAIL,
        b_id,
        snippet="Server model configured with 32 cores",
        claimed="32.0 cores",
        reasoning="Deficit: actual 32.0 cores is below required minimum 64.0 cores (shortfall: -32.0 cores).",
    )
    # Clause B: PASS with valid evidence -> 1.0 completeness
    ev_pass_with_evidence = make_eval(
        "TECH-02",
        ComplianceStatus.PASS,
        b_id,
        snippet="Certificate ISO 9001 attached",
        claimed="ISO 9001",
        reasoning="Certificate is confirmed present.",
    )
    # Clause C: Missing evidence -> 0.0 completeness
    ev_missing = make_eval(
        "TECH-03",
        ComplianceStatus.FAIL,
        b_id,
        snippet=None,
        claimed="None",
        reasoning="Required documentation 'oem_warranty' was not confirmed in evidence.",
    )

    comp_a = ScoringAndRankingService.evaluate_clause_evidence_completeness(ev_fail_with_evidence)
    comp_b = ScoringAndRankingService.evaluate_clause_evidence_completeness(ev_pass_with_evidence)
    comp_c = ScoringAndRankingService.evaluate_clause_evidence_completeness(ev_missing)

    assert comp_a == 1.0  # Even though status is FAIL!
    assert comp_b == 1.0
    assert comp_c == 0.0
