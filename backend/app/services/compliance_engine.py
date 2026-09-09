import logging
from typing import List, Dict, Any, Optional, Union
from uuid import UUID

from app.schemas.bidder import RetrievedEvidenceChunk
from app.schemas.evaluation import (
    ComplianceStatus,
    DeterministicRuleResult,
    AIEvidenceInterpretation,
    ClauseComplianceEvaluation,
    BidderComplianceReport,
)
from app.services.ai_evidence_interpreter import interpret_evidence_for_clause
from app.services.deterministic_rules import evaluate_deterministic_rule

logger = logging.getLogger(__name__)


async def evaluate_clause_compliance(
    clause: Union[Dict[str, Any], Any],
    bidder_id: UUID,
    evidence_chunks: List[RetrievedEvidenceChunk],
    use_live_llm: bool = False,
) -> ClauseComplianceEvaluation:
    """Evaluate a single tender clause against bidder evidence using the Hybrid Compliance Engine.

    Decision Hierarchy:
    1. AI interprets evidence chunks, extracts claimed values, and checks for contradictions/ambiguities.
    2. Contradictions between evidence chunks immediately divert to REVIEW.
    3. Missing or ambiguous evidence diverts to REVIEW.
    4. Deterministic Python rule verifies numeric and strict constraints:
       - Fails constraint -> FAIL
       - Meets constraint -> PASS
    5. Final decision records remain transparent for human procurement-officer confirmation.
    """
    code = clause.get("clause_code") if isinstance(clause, dict) else getattr(clause, "clause_code", "GEN-01")
    title = clause.get("title") if isinstance(clause, dict) else getattr(clause, "title", "Requirement")
    is_mandatory = clause.get("is_mandatory", True) if isinstance(clause, dict) else getattr(clause, "is_mandatory", True)
    rule_cfg = clause.get("rule_config") if isinstance(clause, dict) else getattr(clause, "rule_config", None) or {}

    # 1. AI Evidence Interpretation
    interpretation = await interpret_evidence_for_clause(
        clause=clause,
        evidence_chunks=evidence_chunks,
        use_live_llm=use_live_llm,
    )

    combined_evidence_text = " ".join(c.chunk_text for c in evidence_chunks)
    claimed_val_str = f"{interpretation.extracted_value} {interpretation.extracted_unit or ''}".strip() if interpretation.extracted_value is not None else None

    # 2. Priority Rule: Contradictions divert to REVIEW
    if interpretation.contradiction_detected:
        reason = (
            f"CONTRADICTION DETECTED: {interpretation.contradiction_details}. "
            f"Internal document conflict prevents automated evaluation; requires procurement-officer review."
        )
        return ClauseComplianceEvaluation(
            clause_code=code,
            clause_title=title,
            bidder_id=bidder_id,
            status=ComplianceStatus.REVIEW,
            confidence_score=0.45,
            claimed_value=claimed_val_str,
            reasoning=reason,
            evidence_snippet=interpretation.supporting_quote,
            evidence_page_number=interpretation.evidence_page,
            evidence_chunk_id=interpretation.evidence_chunk_id,
            rule_result=None,
            contradiction_detected=True,
            contradiction_details=interpretation.contradiction_details,
            requires_human_confirmation=True,
        )

    # 3. Priority Rule: Missing or ambiguous evidence diverts to REVIEW
    if interpretation.is_ambiguous_or_missing or not evidence_chunks:
        reason = (
            f"AMBIGUOUS / INSUFFICIENT EVIDENCE: {interpretation.finding}. "
            f"Bidder submission lacks unambiguous proof or references pending/expired credentials; requires officer confirmation."
        )
        return ClauseComplianceEvaluation(
            clause_code=code,
            clause_title=title,
            bidder_id=bidder_id,
            status=ComplianceStatus.REVIEW,
            confidence_score=0.40,
            claimed_value=claimed_val_str,
            reasoning=reason,
            evidence_snippet=interpretation.supporting_quote,
            evidence_page_number=interpretation.evidence_page,
            evidence_chunk_id=interpretation.evidence_chunk_id,
            rule_result=None,
            contradiction_detected=False,
            contradiction_details=None,
            requires_human_confirmation=True,
        )

    # 4. Deterministic Python Rule Execution
    rule_res = evaluate_deterministic_rule(
        rule_config=rule_cfg,
        extracted_value=interpretation.extracted_value,
        evidence_text=combined_evidence_text,
    )

    # 5. Hybrid Decision Synthesis
    if rule_res.passed is True:
        status = ComplianceStatus.PASS
        confidence = 0.95
        reason = f"COMPLIANT: {rule_res.message} {interpretation.finding}"
        req_human = not is_mandatory  # Optional items noted for human confirmation

    elif rule_res.passed is False:
        status = ComplianceStatus.FAIL
        confidence = 0.95
        reason = f"NON-COMPLIANT: {rule_res.message} {interpretation.finding}"
        req_human = True  # Procurement officer should review disqualifying failure

    else:
        # Rule passed is None (CUSTOM or qualitative rule)
        # Check if affirmative qualitative compliance is evidenced
        if interpretation.extracted_value is not None or any(
            w in combined_evidence_text.lower() for w in ["certified", "complies", "confirms", "provided", "guaranteed"]
        ):
            status = ComplianceStatus.PASS
            confidence = 0.88
            reason = f"QUALITATIVELY COMPLIANT: {interpretation.finding}"
            req_human = False
        else:
            status = ComplianceStatus.REVIEW
            confidence = 0.50
            reason = f"OFFICER REVIEW REQUIRED: Qualitative requirement lacks conclusive proof. {interpretation.finding}"
            req_human = True

    return ClauseComplianceEvaluation(
        clause_code=code,
        clause_title=title,
        bidder_id=bidder_id,
        status=status,
        confidence_score=confidence,
        claimed_value=claimed_val_str,
        reasoning=reason,
        evidence_snippet=interpretation.supporting_quote,
        evidence_page_number=interpretation.evidence_page,
        evidence_chunk_id=interpretation.evidence_chunk_id,
        rule_result=rule_res,
        contradiction_detected=False,
        contradiction_details=None,
        requires_human_confirmation=req_human,
    )


async def evaluate_bidder_compliance(
    clauses: List[Union[Dict[str, Any], Any]],
    bidder_id: UUID,
    retrieved_evidence_map: Dict[str, List[RetrievedEvidenceChunk]],
    tender_id: Optional[UUID] = None,
    use_live_llm: bool = False,
) -> BidderComplianceReport:
    """Evaluate all tender clauses for a bidder and generate an officer audit report.

    Strict boundary: Does NOT make final bidder qualification or award decisions.
    Provides structured evaluations and recommendations for the human procurement officer.
    """
    evaluations: List[ClauseComplianceEvaluation] = []

    for clause in clauses:
        code = clause.get("clause_code") if isinstance(clause, dict) else getattr(clause, "clause_code", "")
        chunks = retrieved_evidence_map.get(code, [])

        evaluation = await evaluate_clause_compliance(
            clause=clause,
            bidder_id=bidder_id,
            evidence_chunks=chunks,
            use_live_llm=use_live_llm,
        )
        evaluations.append(evaluation)

    total = len(evaluations)
    pass_cnt = sum(1 for e in evaluations if e.status == ComplianceStatus.PASS)
    fail_cnt = sum(1 for e in evaluations if e.status == ComplianceStatus.FAIL)
    review_cnt = sum(1 for e in evaluations if e.status == ComplianceStatus.REVIEW)

    # Advisory recommendation for human officer
    if fail_cnt > 0:
        recommendation = (
            f"Advisory: Bidder failed {fail_cnt} out of {total} evaluation criteria. "
            f"Procurement officer review recommended for non-compliant clauses."
        )
    elif review_cnt > 0:
        recommendation = (
            f"Advisory: Bidder satisfied {pass_cnt} criteria, but {review_cnt} items require manual verification "
            f"(internal document contradictions or ambiguous proof). Human confirmation required."
        )
    else:
        recommendation = (
            f"Advisory: Bidder successfully satisfied all {pass_cnt} evaluated compliance criteria. "
            f"Final qualification decision submitted for procurement officer sign-off."
        )

    logger.info(
        f"Completed compliance evaluation for bidder {bidder_id}: "
        f"{pass_cnt} PASS, {fail_cnt} FAIL, {review_cnt} REVIEW."
    )

    return BidderComplianceReport(
        bidder_id=bidder_id,
        tender_id=tender_id,
        total_clauses=total,
        pass_count=pass_cnt,
        fail_count=fail_cnt,
        review_count=review_cnt,
        evaluations=evaluations,
        officer_recommendation=recommendation,
    )
