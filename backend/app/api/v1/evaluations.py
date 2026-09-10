import os
import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, Text
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.tender import Tender
from app.models.clause import TenderClause
from app.models.bidder import Bidder, BidDocument
from app.models.chunk import DocumentChunk
from app.models.evaluation import ComplianceEvaluation
from app.schemas.bidder import DocumentChunkItem
from app.schemas.evaluation import (
    ComplianceStatus,
    EvaluationCellSummary,
    ClauseSummary,
    BidderSummary,
    ComplianceMatrixResponse,
    EvaluationDetailResponse,
    OfficerOverrideRequest,
    EvaluationRunRequest,
    EvaluationRunResponse,
)
from app.schemas.scoring import (
    BidderComplianceScoreResponse,
    TenderBidderRankingResponse,
)
from app.services.evidence_fusion_service import EvidenceFusionService
from app.services.cross_source_verifier import CrossSourceVerifier
from app.services.scoring_service import ScoringAndRankingService
from app.services.embedding_service import get_embedding_service
from app.services.evidence_retrieval import retrieve_evidence_for_tender_clauses
from app.services.compliance_engine import evaluate_bidder_compliance

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Compliance Evaluations & Matrix"])


async def _get_tender_or_404(tender_id: UUID, db: AsyncSession) -> Tender:
    stmt = select(Tender).where(Tender.id == tender_id)
    tender = (await db.execute(stmt)).scalar_one_or_none()
    if not tender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender with ID {tender_id} not found",
        )
    return tender


def _to_detail_response(
    eval_rec: ComplianceEvaluation,
    tender_id: UUID,
    bidder_name: str,
    clause: TenderClause,
    doc_name: Optional[str] = None,
) -> EvaluationDetailResponse:
    effective_status = ComplianceStatus(eval_rec.override_status) if eval_rec.override_status else ComplianceStatus(eval_rec.status)
    original_status = ComplianceStatus(eval_rec.status)

    return EvaluationDetailResponse(
        id=eval_rec.id,
        tender_id=tender_id,
        bidder_id=eval_rec.bidder_id,
        bidder_name=bidder_name,
        clause_id=eval_rec.clause_id,
        clause_code=clause.clause_code,
        clause_title=clause.title,
        clause_category=clause.category,
        clause_source_text=clause.source_text,
        clause_page_number=clause.page_number,
        is_mandatory=clause.is_mandatory,
        status=effective_status,
        original_status=original_status,
        confidence_score=float(eval_rec.confidence_score) if eval_rec.confidence_score is not None else None,
        claimed_value=eval_rec.claimed_value,
        reasoning=eval_rec.reasoning,
        evidence_snippet=eval_rec.evidence_snippet,
        evidence_page_number=eval_rec.evidence_page_number,
        evidence_chunk_id=eval_rec.evidence_chunk_id,
        document_name=doc_name,
        rule_result=eval_rec.rule_result,
        contradiction_detected=eval_rec.contradiction_detected,
        contradiction_details=eval_rec.contradiction_details,
        override_status=ComplianceStatus(eval_rec.override_status) if eval_rec.override_status else None,
        override_reason=eval_rec.override_reason,
    )


@router.post("/tenders/{tender_id}/evaluations/run", response_model=EvaluationRunResponse, status_code=status.HTTP_200_OK)
async def run_tender_compliance_evaluation(
    tender_id: UUID,
    req: EvaluationRunRequest = EvaluationRunRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Execute the Hybrid Compliance Engine across all bidders and clauses for a tender.

    Guarantees:
    - Reuses existing verified services/engine (no invented fake AI pipeline).
    - Strict bidder chunk isolation during retrieval.
    - Deterministic Python rules evaluate numeric and strict constraints.
    - Preserves existing officer overrides: evaluate -> override -> evaluate leaves overrides intact.
    """
    tender = await _get_tender_or_404(tender_id, db)

    # 1. Load Clauses for Tender
    c_stmt = (
        select(TenderClause)
        .where(TenderClause.tender_id == tender_id)
        .order_by(TenderClause.clause_code)
    )
    clauses = (await db.execute(c_stmt)).scalars().all()
    if not clauses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tender has 0 clauses. Please extract or confirm clauses before running evaluation.",
        )

    # 2. Load Bidders for Tender
    b_stmt = select(Bidder).where(Bidder.tender_id == tender_id)
    if req.bidder_ids:
        b_stmt = b_stmt.where(Bidder.id.in_(req.bidder_ids))
    b_stmt = b_stmt.order_by(Bidder.created_at)
    bidders = (await db.execute(b_stmt)).scalars().all()
    if not bidders:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No bidders found for this tender. Add bidders or load demo bidders first.",
        )

    embedder = get_embedding_service()
    clause_dicts = [
        {
            "clause_code": c.clause_code,
            "category": c.category,
            "title": c.title,
            "description": c.description,
            "source_text": c.source_text,
            "page_number": c.page_number,
            "is_mandatory": c.is_mandatory,
            "rule_config": c.rule_config,
        }
        for c in clauses
    ]
    clause_by_code = {c.clause_code: c for c in clauses}

    all_reports = []
    total_evals_count = 0

    # 3. Evaluate Each Bidder Independently with Strict Chunk Isolation
    for bidder in bidders:
        # Load chunks strictly for this bidder from database
        chunk_query = (
            select(DocumentChunk, BidDocument.file_name)
            .join(BidDocument, DocumentChunk.bid_document_id == BidDocument.id)
            .where(DocumentChunk.bidder_id == bidder.id)
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        chunk_rows = (await db.execute(chunk_query)).all()

        bidder_chunk_items: List[DocumentChunkItem] = [
            DocumentChunkItem(
                chunk_id=str(row[0].id),
                bidder_id=row[0].bidder_id,
                document_id=row[0].bid_document_id,
                filename=row[1] or "document.pdf",
                page_number=row[0].page_number,
                chunk_index=row[0].chunk_index,
                chunk_text=row[0].content,
                start_char=row[0].start_char,
                end_char=row[0].end_char,
                embedding=list(row[0].embedding) if row[0].embedding is not None else None,
            )
            for row in chunk_rows
        ]

        # Retrieve evidence chunks for all tender clauses
        ev_list = await retrieve_evidence_for_tender_clauses(
            clauses=clause_dicts,
            bidder_id=bidder.id,
            chunks=bidder_chunk_items,
            embedding_service=embedder,
        )
        ev_map = {item.clause_code: item.top_evidence for item in ev_list}

        # Run compliance engine
        report = await evaluate_bidder_compliance(
            clauses=clause_dicts,
            bidder_id=bidder.id,
            retrieved_evidence_map=ev_map,
            tender_id=tender_id,
            use_live_llm=req.use_live_llm,
        )
        all_reports.append(report)

        # 4. Upsert ComplianceEvaluation records, PRESERVING existing officer overrides
        for clause_eval in report.evaluations:
            total_evals_count += 1
            clause_model = clause_by_code[clause_eval.clause_code]

            eval_check_stmt = select(ComplianceEvaluation).where(
                ComplianceEvaluation.bidder_id == bidder.id,
                ComplianceEvaluation.clause_id == clause_model.id,
            )
            eval_record = (await db.execute(eval_check_stmt)).scalar_one_or_none()

            rule_res_dict = (
                clause_eval.rule_result.model_dump()
                if clause_eval.rule_result
                else None
            )

            if eval_record:
                # Update automated audit fields
                eval_record.status = clause_eval.status.value
                eval_record.confidence_score = clause_eval.confidence_score
                eval_record.claimed_value = clause_eval.claimed_value
                eval_record.reasoning = clause_eval.reasoning
                eval_record.evidence_snippet = clause_eval.evidence_snippet
                eval_record.evidence_page_number = clause_eval.evidence_page_number
                eval_record.evidence_chunk_id = clause_eval.evidence_chunk_id
                eval_record.rule_result = rule_res_dict
                eval_record.contradiction_detected = clause_eval.contradiction_detected
                eval_record.contradiction_details = clause_eval.contradiction_details
                # CRITICAL: Preserve existing officer override
                # eval_record.override_status and eval_record.override_reason are LEFT UNCHANGED!
            else:
                eval_record = ComplianceEvaluation(
                    bidder_id=bidder.id,
                    clause_id=clause_model.id,
                    status=clause_eval.status.value,
                    confidence_score=clause_eval.confidence_score,
                    claimed_value=clause_eval.claimed_value,
                    reasoning=clause_eval.reasoning,
                    evidence_snippet=clause_eval.evidence_snippet,
                    evidence_page_number=clause_eval.evidence_page_number,
                    evidence_chunk_id=clause_eval.evidence_chunk_id,
                    rule_result=rule_res_dict,
                    contradiction_detected=clause_eval.contradiction_detected,
                    contradiction_details=clause_eval.contradiction_details,
                    risk_level="MEDIUM",
                    override_status=None,
                    override_reason=None,
                )
                db.add(eval_record)

        # Update bidder status
        if report.fail_count == 0 and report.review_count == 0:
            bidder.final_status = "QUALIFIED"
        elif report.fail_count > 0:
            bidder.final_status = "DISQUALIFIED"
        else:
            bidder.final_status = "UNDER_REVIEW"

    await db.commit()

    return EvaluationRunResponse(
        tender_id=tender_id,
        bidders_evaluated=len(bidders),
        total_evaluations=total_evals_count,
        reports=all_reports,
    )


@router.get("/tenders/{tender_id}/evaluations/matrix", response_model=ComplianceMatrixResponse)
async def get_compliance_matrix(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Fetch comparative compliance matrix for tender, with clause, bidder, and override details."""
    tender = await _get_tender_or_404(tender_id, db)

    # 1. Fetch clauses
    c_stmt = (
        select(TenderClause)
        .where(TenderClause.tender_id == tender_id)
        .order_by(TenderClause.clause_code)
    )
    clauses = (await db.execute(c_stmt)).scalars().all()

    # 2. Fetch bidders
    b_stmt = select(Bidder).where(Bidder.tender_id == tender_id).order_by(Bidder.created_at)
    bidders = (await db.execute(b_stmt)).scalars().all()

    # 3. Fetch all evaluations for this tender
    eval_stmt = (
        select(ComplianceEvaluation)
        .join(TenderClause, ComplianceEvaluation.clause_id == TenderClause.id)
        .where(TenderClause.tender_id == tender_id)
        .options(
            selectinload(ComplianceEvaluation.clause),
            selectinload(ComplianceEvaluation.bidder),
        )
    )
    eval_records = (await db.execute(eval_stmt)).scalars().all()

    # Organize evaluations: matrix[str(bidder_id)][clause_code]
    eval_map: Dict[str, Dict[str, ComplianceEvaluation]] = {}
    for er in eval_records:
        bidder_key = str(er.bidder_id)
        if bidder_key not in eval_map:
            eval_map[bidder_key] = {}
        eval_map[bidder_key][er.clause.clause_code] = er

    # Build matrix response
    matrix_data: Dict[str, Dict[str, EvaluationCellSummary]] = {}
    bidder_summaries: List[BidderSummary] = []

    total_pass = 0
    total_fail = 0
    total_review = 0
    total_overrides = 0

    for b in bidders:
        b_key = str(b.id)
        matrix_data[b_key] = {}
        b_pass = 0
        b_fail = 0
        b_review = 0

        for c in clauses:
            er = eval_map.get(b_key, {}).get(c.clause_code)
            if er:
                effective_st = er.override_status or er.status
                if effective_st == "PASS":
                    b_pass += 1
                elif effective_st == "FAIL":
                    b_fail += 1
                else:
                    b_review += 1

                if er.override_status:
                    total_overrides += 1

                cell = EvaluationCellSummary(
                    evaluation_id=er.id,
                    bidder_id=b.id,
                    clause_id=c.id,
                    clause_code=c.clause_code,
                    status=ComplianceStatus(effective_st),
                    original_status=ComplianceStatus(er.status),
                    confidence_score=float(er.confidence_score) if er.confidence_score is not None else None,
                    claimed_value=er.claimed_value,
                    reasoning=er.reasoning,
                    contradiction_detected=er.contradiction_detected,
                    evidence_page_number=er.evidence_page_number,
                    evidence_chunk_id=er.evidence_chunk_id,
                    document_name=None,
                    override_status=ComplianceStatus(er.override_status) if er.override_status else None,
                    override_reason=er.override_reason,
                )
                matrix_data[b_key][c.clause_code] = cell

        total_pass += b_pass
        total_fail += b_fail
        total_review += b_review

        # Final status considering officer overrides
        effective_final_status = b.final_status
        if b_fail == 0 and b_review == 0 and b_pass > 0:
            effective_final_status = "QUALIFIED"
        elif b_fail > 0:
            effective_final_status = "DISQUALIFIED"
        elif b_pass + b_fail + b_review > 0:
            effective_final_status = "UNDER_REVIEW"

        bidder_summaries.append(
            BidderSummary(
                id=b.id,
                company_name=b.company_name,
                pass_count=b_pass,
                fail_count=b_fail,
                review_count=b_review,
                final_status=effective_final_status,
                officer_recommendation=(
                    "Qualified" if effective_final_status == "QUALIFIED"
                    else "Disqualified" if effective_final_status == "DISQUALIFIED"
                    else "Officer Review Required"
                ),
            )
        )

    clause_summaries = [
        ClauseSummary(
            id=c.id,
            clause_code=c.clause_code,
            category=c.category,
            title=c.title,
            is_mandatory=c.is_mandatory,
            rule_type=(c.rule_config or {}).get("type") if isinstance(c.rule_config, dict) else None,
        )
        for c in clauses
    ]

    return ComplianceMatrixResponse(
        tender_id=tender.id,
        tender_title=tender.title,
        bidders=bidder_summaries,
        clauses=clause_summaries,
        matrix=matrix_data,
        summary={
            "total_bidders": len(bidders),
            "total_clauses": len(clauses),
            "total_pass": total_pass,
            "total_fail": total_fail,
            "total_review": total_review,
            "total_officer_overrides": total_overrides,
        },
    )


@router.get("/tenders/{tender_id}/evaluations/{evaluation_id}", response_model=EvaluationDetailResponse)
@router.get("/evaluations/{evaluation_id}/detail", response_model=EvaluationDetailResponse)
async def get_evaluation_detail(
    evaluation_id: UUID,
    tender_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full audit detail for a specific evaluation cell with tender boundary verification."""
    stmt = (
        select(ComplianceEvaluation)
        .where(ComplianceEvaluation.id == evaluation_id)
        .options(
            selectinload(ComplianceEvaluation.clause),
            selectinload(ComplianceEvaluation.bidder),
        )
    )
    eval_rec = (await db.execute(stmt)).scalar_one_or_none()

    if not eval_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compliance evaluation {evaluation_id} not found",
        )

    # Tender ownership verification
    if tender_id and eval_rec.clause.tender_id != tender_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {evaluation_id} does not belong to tender {tender_id}",
        )

    return _to_detail_response(
        eval_rec=eval_rec,
        tender_id=eval_rec.clause.tender_id,
        bidder_name=eval_rec.bidder.company_name,
        clause=eval_rec.clause,
    )


@router.post("/tenders/{tender_id}/evaluations/{evaluation_id}/override", response_model=EvaluationDetailResponse)
@router.post("/evaluations/{evaluation_id}/override", response_model=EvaluationDetailResponse)
async def override_evaluation_decision(
    evaluation_id: UUID,
    req: OfficerOverrideRequest,
    tender_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    """Apply a procurement officer override with mandatory non-empty justification.

    Validates:
    - Non-empty officer justification (minimum length 3).
    - Tender boundary isolation.
    - Preserves audit trail and marks override.
    """
    clean_reason = req.override_reason.strip()
    if not clean_reason or len(clean_reason) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Officer override requires a non-empty justification with at least 3 characters.",
        )

    stmt = (
        select(ComplianceEvaluation)
        .where(ComplianceEvaluation.id == evaluation_id)
        .options(
            selectinload(ComplianceEvaluation.clause),
            selectinload(ComplianceEvaluation.bidder),
        )
    )
    eval_rec = (await db.execute(stmt)).scalar_one_or_none()

    if not eval_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compliance evaluation {evaluation_id} not found",
        )

    # Tender ownership verification
    if tender_id and eval_rec.clause.tender_id != tender_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {evaluation_id} does not belong to tender {tender_id}",
        )

    # Apply override
    eval_rec.override_status = req.override_status.value
    eval_rec.override_reason = clean_reason
    await db.commit()
    await db.refresh(eval_rec)

    logger.info(
        f"Officer override applied to evaluation {evaluation_id}: "
        f"status -> {eval_rec.override_status}, reason: '{clean_reason}'"
    )

    return _to_detail_response(
        eval_rec=eval_rec,
        tender_id=eval_rec.clause.tender_id,
        bidder_name=eval_rec.bidder.company_name,
        clause=eval_rec.clause,
    )


async def _compute_bidder_score(
    bidder: Bidder,
    tender_id: UUID,
    db: AsyncSession,
) -> BidderComplianceScoreResponse:
    # 1. Load clauses for tender to map mandatory flags
    c_stmt = select(TenderClause).where(TenderClause.tender_id == tender_id)
    clauses = (await db.execute(c_stmt)).scalars().all()
    clause_map = {c.clause_code: c.is_mandatory for c in clauses}

    # 2. Load compliance evaluations for this bidder
    eval_stmt = (
        select(ComplianceEvaluation)
        .where(ComplianceEvaluation.bidder_id == bidder.id)
        .options(selectinload(ComplianceEvaluation.clause))
    )
    eval_records = (await db.execute(eval_stmt)).scalars().all()
    evals_for_tender = [e for e in eval_records if e.clause and e.clause.tender_id == tender_id]

    # 3. Fuse evidence and verify cross-source
    profile = await EvidenceFusionService.fuse_bidder_evidence(
        bidder_id=bidder.id,
        db=db,
        tender_id=tender_id,
        company_name_override=bidder.company_name,
    )
    cross_report = CrossSourceVerifier.verify_profile(profile)

    # 4. Calculate score
    return ScoringAndRankingService.calculate_bidder_score(
        bidder_id=bidder.id,
        company_name=bidder.company_name,
        evaluations=evals_for_tender,
        cross_source_report=cross_report,
        tender_id=tender_id,
        clause_mandatory_map=clause_map,
    )


@router.get(
    "/tenders/{tender_id}/bidders/{bidder_id}/score",
    response_model=BidderComplianceScoreResponse,
    status_code=status.HTTP_200_OK,
)
async def get_bidder_compliance_score(
    tender_id: UUID,
    bidder_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve 100-point compliance score, risk assessment, and component breakdown for a bidder."""
    await _get_tender_or_404(tender_id, db)

    b_stmt = select(Bidder).where(
        Bidder.id == bidder_id,
        Bidder.tender_id == tender_id,
    )
    bidder = (await db.execute(b_stmt)).scalar_one_or_none()
    if not bidder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bidder with ID {bidder_id} not found for tender {tender_id}",
        )

    return await _compute_bidder_score(bidder, tender_id, db)


@router.get(
    "/tenders/{tender_id}/evaluations/{evaluation_id}/score",
    response_model=BidderComplianceScoreResponse,
    status_code=status.HTTP_200_OK,
)
async def get_evaluation_bidder_compliance_score(
    tender_id: UUID,
    evaluation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve compliance score for the bidder associated with a specific evaluation cell."""
    await _get_tender_or_404(tender_id, db)

    eval_stmt = (
        select(ComplianceEvaluation)
        .where(ComplianceEvaluation.id == evaluation_id)
        .options(
            selectinload(ComplianceEvaluation.clause),
            selectinload(ComplianceEvaluation.bidder),
        )
    )
    eval_rec = (await db.execute(eval_stmt)).scalar_one_or_none()
    if not eval_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compliance evaluation {evaluation_id} not found",
        )

    if eval_rec.clause.tender_id != tender_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {evaluation_id} does not belong to tender {tender_id}",
        )

    return await _compute_bidder_score(eval_rec.bidder, tender_id, db)


@router.get(
    "/tenders/{tender_id}/ranking",
    response_model=TenderBidderRankingResponse,
    status_code=status.HTTP_200_OK,
)
async def get_tender_bidder_ranking(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve deterministic, comparative bidder ranking and safety risk assessment under a tender."""
    tender = await _get_tender_or_404(tender_id, db)

    b_stmt = select(Bidder).where(Bidder.tender_id == tender_id).order_by(Bidder.created_at)
    bidders = (await db.execute(b_stmt)).scalars().all()

    bidder_scores = []
    for bidder in bidders:
        score_item = await _compute_bidder_score(bidder, tender_id, db)
        bidder_scores.append(score_item)

    return ScoringAndRankingService.rank_bidders(
        tender_id=tender.id,
        tender_title=tender.title,
        bidder_scores=bidder_scores,
    )
