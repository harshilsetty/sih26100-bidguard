"""Scoring and Bidder Ranking Service.

Phase 6.4 — SIH26100 Compliance Score + Risk + Bidder Ranking Layer.
Calculates deterministic, explainable compliance scores (out of 100.0), safety risk levels,
and tender-scoped bidder rankings for procurement decision support.

LOCKED ARCHITECTURAL PRINCIPLES & CORRECTIONS:
1. 100-Point Scoring Model:
   - Tender Compliance = 50 points (proportional: PASS=1.0, REVIEW=0.5, FAIL=0.0)
   - Statutory Consistency = 20 points (CONSISTENT=1.0, INSUFFICIENT=0.5, INCONSISTENT=0.0, NOT_COMPARABLE=EXCLUDED)
   - Evidence Completeness = 15 points (Independent of PASS/FAIL: sufficient=1.0, partial=0.5, missing=0.0)
   - Contradictions = 15 points (Exact deductions: MINOR=-3.0, MAJOR=-7.5, floor=0.0)
2. Safety & Minimum-Risk Overrides:
   - Base: [80, 100] -> LOW, [60, 79.99] -> MEDIUM, [0, 59.99] -> HIGH
   - Any major contradiction forces risk to at least MEDIUM
   - 2+ major contradictions force risk to HIGH
   - Critical mandatory clause FAIL forces risk to HIGH
3. Fixed Ranking Order:
   - overall_score DESC -> risk_level severity ASC (LOW < MEDIUM < HIGH) -> bidder_id ASC
   - Decision support only (never winner selection or auto-qualification)
4. Deterministic:
   - Zero LLM/NIM invocations in scoring and ranking.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from uuid import UUID

from app.schemas.evaluation import ComplianceStatus, ClauseComplianceEvaluation
from app.schemas.cross_source_verification import (
    CrossSourceStatus,
    CrossSourceVerificationResult,
    BidderCrossSourceVerificationReport,
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

logger = logging.getLogger(__name__)

# Canonical fields considered MAJOR when an inconsistency/contradiction is detected
MAJOR_CONTRADICTION_FIELDS = {
    "turnover",
    "local_content_percent",
    "company_status",
    "gstin_status",
    "pan_status",
    "tax_compliance_status",
    "udyam_status",
}


class ScoringAndRankingService:
    """Service for deterministic compliance scoring, risk assessment, and bidder ranking."""

    @staticmethod
    def evaluate_clause_evidence_completeness(
        eval_item: Union[ClauseComplianceEvaluation, Any],
    ) -> float:
        """Evaluate evidence completeness independently from compliance PASS/FAIL status (Locked Correction #1).
        
        Returns:
            1.0: Sufficient evidence present (even if bidder failed threshold)
            0.5: Partial or ambiguous evidence
            0.0: Evidence required but missing/unconfirmed
        """
        snippet = (getattr(eval_item, "evidence_snippet", None) or "").strip()
        claimed = (getattr(eval_item, "claimed_value", None) or "").strip()
        reasoning = (getattr(eval_item, "reasoning", None) or "").strip().lower()

        # Check for missing evidence indicators
        missing_indicators = [
            "was not confirmed in evidence",
            "no measurable value extracted",
            "missing",
            "omitted",
            "no verifiable public procurement",
            "no evidence found",
            "0 certified",
            "uncertified",
        ]
        if any(ind in reasoning for ind in missing_indicators) or (
            not snippet and claimed in {"None", "", "None status"}
        ):
            return 0.0

        # Check for ambiguous/partial indicators
        ambiguous_indicators = [
            "ambiguous",
            "insufficient evidence",
            "clarification needed",
            "contingent",
            "conditional",
            "ongoing",
            "unclear",
        ]
        if any(ind in reasoning for ind in ambiguous_indicators) or "ambiguous" in claimed.lower():
            return 0.5

        # Sufficient evidence is present and measurable (even if compliance status is FAIL)
        return 1.0

    @classmethod
    def classify_contradictions(
        cls,
        cross_source_report: Optional[BidderCrossSourceVerificationReport],
        evaluations: List[Union[ClauseComplianceEvaluation, Any]],
    ) -> Tuple[int, int, List[str]]:
        """Deterministically classify contradictions into MAJOR and MINOR (Locked Correction #2).
        
        Returns:
            (major_count, minor_count, contradiction_summaries)
        """
        major_fields = set()
        minor_fields = set()
        summaries: List[str] = []

        # 1. From Phase 6.3 Cross-Source Verification Results
        if cross_source_report and cross_source_report.results:
            for res in cross_source_report.results:
                if res.status == CrossSourceStatus.INCONSISTENT:
                    field = res.field_name.lower()
                    if field in MAJOR_CONTRADICTION_FIELDS or "status" in field:
                        major_fields.add(field)
                        summaries.append(f"Statutory mismatch in {res.field_label}: {res.explanation}")
                    else:
                        minor_fields.add(field)
                        summaries.append(f"Discrepancy in {res.field_label}: {res.explanation}")

        # 2. From Clause-Level Evaluations (cross-chunk contradictions)
        for ev in evaluations:
            if getattr(ev, "contradiction_detected", False):
                details = getattr(ev, "contradiction_details", None) or getattr(ev, "reasoning", "")
                code = getattr(ev, "clause_code", "")

                # Detect target parameter from rule_result or details
                rule_res = getattr(ev, "rule_result", None) or {}
                if isinstance(rule_res, dict):
                    param = rule_res.get("parameter") or ""
                else:
                    param = getattr(rule_res, "parameter", "") or ""

                param_lower = param.lower() if param else ""
                if not param_lower:
                    if "turnover" in details.lower():
                        param_lower = "turnover"
                    elif "local_content" in details.lower():
                        param_lower = "local_content_percent"
                    elif "cpu" in details.lower():
                        param_lower = "cpu_cores"

                # Deduplicate by parameter: don't double count same parameter if already marked major
                if param_lower in MAJOR_CONTRADICTION_FIELDS:
                    if param_lower not in major_fields:
                        major_fields.add(param_lower)
                        summaries.append(f"Clause {code} contradiction ({param_lower}): {details[:120]}")
                else:
                    key = f"clause_{code}_{param_lower or 'spec'}"
                    if key not in minor_fields:
                        minor_fields.add(key)
                        summaries.append(f"Clause {code} contradiction: {details[:120]}")

        return len(major_fields), len(minor_fields), summaries

    @classmethod
    def calculate_bidder_score(
        cls,
        bidder_id: Union[UUID, str],
        company_name: str,
        evaluations: List[Union[ClauseComplianceEvaluation, Any]],
        cross_source_report: Optional[BidderCrossSourceVerificationReport] = None,
        tender_id: Optional[Union[UUID, str]] = None,
        clause_mandatory_map: Optional[Dict[str, bool]] = None,
        is_debarred_on_date: bool = False,
        debarment_details: Optional[Dict[str, Any]] = None,
    ) -> BidderComplianceScoreResponse:
        """Calculate the deterministic 100-point compliance score and risk determination for a bidder."""
        b_id_str = str(bidder_id)
        t_id_str = str(tender_id) if tender_id else None
        clause_map = clause_mandatory_map or {}

        # -------------------------------------------------------------------
        # 1. Tender Compliance Score (50 Points)
        # -------------------------------------------------------------------
        pass_count = 0
        fail_count = 0
        review_count = 0
        has_mandatory_fail = False
        mandatory_fails: List[str] = []

        total_clauses = len(evaluations)
        earned_clause_points = 0.0

        for ev in evaluations:
            # Effective status: officer override takes precedence if present
            override_st = getattr(ev, "override_status", None)
            st = override_st if override_st else getattr(ev, "status", None)
            st_val = st.value if hasattr(st, "value") else str(st)

            code = getattr(ev, "clause_code", "")
            is_mandatory = clause_map.get(code, getattr(ev, "is_mandatory", True))

            if st_val == "PASS":
                pass_count += 1
                earned_clause_points += 1.0
            elif st_val == "FAIL":
                fail_count += 1
                if is_mandatory:
                    has_mandatory_fail = True
                    mandatory_fails.append(code)
            else:  # REVIEW
                review_count += 1
                earned_clause_points += 0.5

        if total_clauses > 0:
            tender_score = round((earned_clause_points / total_clauses) * 50.0, 2)
        else:
            tender_score = 0.0

        # -------------------------------------------------------------------
        # 2. Statutory Cross-Source Consistency Score (20 Points)
        # Locked Correction #4: NOT_COMPARABLE is EXCLUDED from applicable checks
        # -------------------------------------------------------------------
        inconsistency_count = 0
        applicable_statutory_checks = 0
        earned_statutory_points = 0.0

        if cross_source_report and cross_source_report.results:
            for r in cross_source_report.results:
                if r.status == CrossSourceStatus.NOT_COMPARABLE:
                    # Exclude from denominator
                    continue

                applicable_statutory_checks += 1
                if r.status == CrossSourceStatus.CONSISTENT:
                    earned_statutory_points += 1.0
                elif r.status == CrossSourceStatus.INSUFFICIENT_EVIDENCE:
                    earned_statutory_points += 0.5
                elif r.status == CrossSourceStatus.INCONSISTENT:
                    inconsistency_count += 1
                    # 0.0 points

        if applicable_statutory_checks > 0:
            statutory_score = round((earned_statutory_points / applicable_statutory_checks) * 20.0, 2)
        else:
            # Neutral credit when no statutory records exist to compare
            statutory_score = 20.0 if (cross_source_report is None or len(cross_source_report.results) == 0) else 10.0

        # -------------------------------------------------------------------
        # 3. Evidence Completeness Score (15 Points)
        # Locked Correction #1: Independent from PASS/FAIL/REVIEW
        # -------------------------------------------------------------------
        earned_completeness_pts = 0.0
        for ev in evaluations:
            earned_completeness_pts += cls.evaluate_clause_evidence_completeness(ev)

        if total_clauses > 0:
            evidence_score = round((earned_completeness_pts / total_clauses) * 15.0, 2)
        else:
            evidence_score = 15.0

        # -------------------------------------------------------------------
        # 4. Contradiction Score (15 Points)
        # Locked Correction #2: MINOR = -3.0, MAJOR = -7.5, floor = 0.0
        # -------------------------------------------------------------------
        major_count, minor_count, contradiction_notes = cls.classify_contradictions(
            cross_source_report, evaluations
        )
        deduction = (major_count * 7.5) + (minor_count * 3.0)
        contradiction_score = max(0.0, round(15.0 - deduction, 2))

        # -------------------------------------------------------------------
        # 5. Overall Score & Breakdown
        # -------------------------------------------------------------------
        overall_score = round(
            tender_score + statutory_score + evidence_score + contradiction_score, 2
        )
        # Safety bound [0.0, 100.0]
        overall_score = max(0.0, min(100.0, overall_score))

        breakdown = ScoreBreakdown(
            tender_compliance=tender_score,
            statutory_consistency=statutory_score,
            evidence_completeness=evidence_score,
            contradiction_score=contradiction_score,
        )

        summary = ScoreSummary(
            pass_count=pass_count,
            fail_count=fail_count,
            review_count=review_count,
            inconsistency_count=inconsistency_count,
            major_contradiction_count=major_count,
            minor_contradiction_count=minor_count,
        )

        # -------------------------------------------------------------------
        # 6. Risk Level & Safety Overrides
        # -------------------------------------------------------------------
        risk_triggers: List[str] = []

        # Base threshold
        if overall_score >= 80.00:
            assigned_risk = RiskLevel.LOW
        elif overall_score >= 60.00:
            assigned_risk = RiskLevel.MEDIUM
        else:
            assigned_risk = RiskLevel.HIGH

        # Safety override 1: Any major unresolved contradiction -> minimum MEDIUM
        if major_count >= 1 and assigned_risk == RiskLevel.LOW:
            assigned_risk = RiskLevel.MEDIUM
            risk_triggers.append(
                f"Major contradiction detected ({major_count} major conflict(s)): risk elevated to minimum MEDIUM."
            )

        # Safety override 2: Multiple (2+) major contradictions -> HIGH
        if major_count >= 2 and assigned_risk != RiskLevel.HIGH:
            assigned_risk = RiskLevel.HIGH
            risk_triggers.append(
                f"Multiple major contradictions ({major_count} major conflicts): risk elevated to HIGH."
            )

        # Safety override 3: Critical mandatory clause FAIL -> HIGH
        if has_mandatory_fail and assigned_risk != RiskLevel.HIGH:
            assigned_risk = RiskLevel.HIGH
            fails_str = ", ".join(mandatory_fails[:3])
            risk_triggers.append(
                f"Mandatory tender criteria failed ({fails_str}): risk elevated to HIGH."
            )

        # Safety override 4: Active statutory debarment signal -> HIGH
        # Orthogonal risk signal: does NOT alter 100-pt mathematical formula.
        # HIGH RISK != FAIL != DISQUALIFIED.
        if is_debarred_on_date:
            assigned_risk = RiskLevel.HIGH
            risk_triggers.append(
                "Active statutory debarment / blacklisting verified on evaluation date: risk elevated to HIGH (officer review required)."
            )

        calculation_details = {
            "tender_compliance": {
                "earned_points": earned_clause_points,
                "total_clauses": total_clauses,
                "formula": "round((earned / total) * 50.0, 2)",
                "result": tender_score,
            },
            "statutory_consistency": {
                "earned_points": earned_statutory_points,
                "applicable_checks": applicable_statutory_checks,
                "formula": "round((earned / applicable) * 20.0, 2)",
                "result": statutory_score,
            },
            "evidence_completeness": {
                "earned_points": earned_completeness_pts,
                "total_clauses": total_clauses,
                "formula": "round((earned / total) * 15.0, 2)",
                "result": evidence_score,
            },
            "contradictions": {
                "start_points": 15.0,
                "major_count": major_count,
                "major_deduction_each": 7.5,
                "minor_count": minor_count,
                "minor_deduction_each": 3.0,
                "formula": "max(0.0, round(15.0 - (major * 7.5) - (minor * 3.0), 2))",
                "result": contradiction_score,
            },
            "contradiction_details": contradiction_notes,
        }

        if is_debarred_on_date:
            calculation_details["debarment_risk"] = {
                "is_debarred_on_date": True,
                "officer_review_required": True,
                "details": debarment_details or {},
            }

        return BidderComplianceScoreResponse(
            bidder_id=b_id_str,
            tender_id=t_id_str,
            company_name=company_name,
            overall_score=overall_score,
            risk_level=assigned_risk,
            breakdown=breakdown,
            risk_triggers=risk_triggers,
            summary=summary,
            calculation_details=calculation_details,
            disclaimer=DECISION_SUPPORT_DISCLAIMER,
        )

    @classmethod
    def rank_bidders(
        cls,
        tender_id: Union[UUID, str],
        tender_title: str,
        bidder_scores: List[BidderComplianceScoreResponse],
    ) -> TenderBidderRankingResponse:
        """Deterministically rank bidders under a tender (Locked Correction #3).
        
        Sorting hierarchy:
        1. overall_score DESC
        2. risk_level ASC: LOW (1) before MEDIUM (2) before HIGH (3)
        3. stable bidder_id ASC (alphanumeric tie-breaker)
        """
        # Risk ordering helper: LOW = 0, MEDIUM = 1, HIGH = 2
        risk_weight = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
        }

        # Sort key: (-overall_score, risk_weight, bidder_id)
        sorted_scores = sorted(
            bidder_scores,
            key=lambda item: (-item.overall_score, risk_weight.get(item.risk_level, 3), str(item.bidder_id)),
        )

        ranked_items: List[RankedBidderItem] = []
        for idx, score_item in enumerate(sorted_scores, start=1):
            # Formulate recommendation
            if score_item.risk_level == RiskLevel.LOW and score_item.summary.fail_count == 0:
                rec = "Recommended for Officer Review"
            elif score_item.risk_level == RiskLevel.MEDIUM:
                rec = "Recommended for Detailed Verification"
            else:
                rec = "Critical Flags Require Officer Adjudication"

            key_warnings: List[str] = list(score_item.risk_triggers)
            calc_details = score_item.calculation_details or {}
            notes = calc_details.get("contradiction_details", [])
            for note in notes[:2]:
                if note not in key_warnings:
                    key_warnings.append(note)

            total_warnings = (
                score_item.summary.fail_count
                + score_item.summary.review_count
                + score_item.summary.inconsistency_count
                + score_item.summary.major_contradiction_count
            )

            ranked_items.append(
                RankedBidderItem(
                    rank=idx,
                    bidder_id=score_item.bidder_id,
                    company_name=score_item.company_name,
                    overall_score=score_item.overall_score,
                    risk_level=score_item.risk_level,
                    breakdown=score_item.breakdown,
                    recommendation=rec,
                    warning_count=total_warnings,
                    key_warnings=key_warnings[:3],
                )
            )

        return TenderBidderRankingResponse(
            tender_id=str(tender_id),
            tender_title=tender_title,
            total_bidders=len(ranked_items),
            rankings=ranked_items,
            disclaimer=DECISION_SUPPORT_DISCLAIMER,
        )
