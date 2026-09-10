"""
app.api.v1.statutory
~~~~~~~~~~~~~~~~~~~~
REST API router for Phase 8.1 Unified Statutory Verification Orchestrator.
Exposes endpoints for triggering statutory verification queries, retrieving persisted status,
and listing available statutory source adapters.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
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
from app.models.statutory import StatutoryVerificationRecord
from app.services.statutory_orchestrator import (
    StatutoryVerificationOrchestrator,
    get_statutory_orchestrator,
)
from app.services.statutory_adapters.registry import get_statutory_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/statutory", tags=["Statutory Verification"])


@router.post(
    "/verify",
    response_model=BidderStatutoryVerificationSummary,
    summary="Execute statutory verification across authorities",
    description=(
        "Concurrently queries statutory registers (GSTN, Udyam, MCA, Income Tax, MII) "
        "with complete fault isolation, status separation, temporal evaluation, "
        "and persistence to PostgreSQL."
    ),
)
async def verify_statutory_sources(
    query: StatutoryVerificationQuery,
    db: AsyncSession = Depends(get_db),
    orchestrator: StatutoryVerificationOrchestrator = Depends(get_statutory_orchestrator),
) -> BidderStatutoryVerificationSummary:
    """Trigger statutory verification for a bidder or ad-hoc statutory identifiers."""
    try:
        summary = await orchestrator.verify_statutory_sources(
            query=query,
            db=db,
            persist=True,
        )
        return summary
    except Exception as e:
        logger.error(f"Error during statutory verification execution: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Statutory verification execution failed: {str(e)}",
        )


@router.get(
    "/status",
    response_model=List[SourceVerificationResult],
    summary="Retrieve persisted statutory verification history",
    description="Fetches historical statutory verification records filtered by bidder, tender, or authority.",
)
async def get_statutory_status(
    bidder_id: Optional[UUID] = Query(None, description="Bidder UUID filter"),
    tender_id: Optional[UUID] = Query(None, description="Tender UUID filter"),
    authority: Optional[str] = Query(None, description="Authority filter (e.g. GSTN, UDYAM)"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    db: AsyncSession = Depends(get_db),
) -> List[SourceVerificationResult]:
    """Retrieve historical statutory verification records."""
    stmt = select(StatutoryVerificationRecord)

    if bidder_id:
        stmt = stmt.where(StatutoryVerificationRecord.bidder_id == bidder_id)
    if tender_id:
        stmt = stmt.where(StatutoryVerificationRecord.tender_id == tender_id)
    if authority:
        stmt = stmt.where(StatutoryVerificationRecord.authority == authority.upper())

    stmt = stmt.order_by(desc(StatutoryVerificationRecord.retrieved_at)).limit(limit)

    result = await db.execute(stmt)
    records = result.scalars().all()

    return [
        SourceVerificationResult(
            verification_id=str(r.verification_id),
            authority=StatutoryAuthority(r.authority),
            source_name=r.source_name,
            query_identifier=r.query_identifier,
            identifier_type=r.identifier_type,
            mode=SourceMode(r.mode),
            connection_status=SourceConnectionStatus(r.connection_status),
            verification_status=SourceVerificationStatus(r.verification_status),
            retrieved_at=r.retrieved_at,
            as_of_date=r.as_of_date,
            data_payload=r.data_payload or {},
            confidence_score=float(r.confidence_score) if r.confidence_score is not None else 1.0,
            provenance_note=r.provenance_note or STATUTORY_MOCK_BANNER,
            error_message=r.error_message,
            execution_time_ms=float(r.execution_time_ms) if r.execution_time_ms is not None else 0.0,
        )
        for r in records
    ]


@router.get(
    "/adapters",
    response_model=List[Dict[str, Any]],
    summary="List available statutory adapters",
    description="Returns metadata of all registered statutory source adapters.",
)
async def list_statutory_adapters() -> List[Dict[str, Any]]:
    """List all registered statutory adapters and their supported identifier types."""
    registry = get_statutory_registry()
    adapters = registry.get_all_adapters()
    return [
        {
            "authority": adapter.authority.value,
            "source_name": adapter.source_name,
            "supported_identifier_types": adapter.get_supported_identifier_types(),
            "mode": SourceMode.MOCK.value,
            "disclaimer": STATUTORY_MOCK_BANNER,
        }
        for adapter in adapters.values()
    ]
