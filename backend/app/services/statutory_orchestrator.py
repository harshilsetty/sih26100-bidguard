"""
app.services.statutory_orchestrator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
StatutoryVerificationOrchestrator orchestrates concurrent statutory verification queries
across registered source adapters (GSTN, Udyam, MCA, Income Tax, MII).
Ensures fault isolation, identifier resolution, temporal evaluation,
safe payload sanitization, and optional PostgreSQL persistence.
"""

import asyncio
import logging
import uuid
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
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
from app.models.bidder import Bidder
from app.models.statutory import StatutoryVerificationRecord
from app.services.statutory_adapters.base import BaseSourceAdapter
from app.services.statutory_adapters.registry import (
    StatutoryAdapterRegistry,
    get_statutory_registry,
)

logger = logging.getLogger(__name__)

# Canonical mapping of authority to default identifier key in query.identifiers
AUTHORITY_IDENTIFIER_KEYS: Dict[StatutoryAuthority, List[str]] = {
    StatutoryAuthority.GSTN: ["gstin", "gstn", "entity_identifier", "company_name"],
    StatutoryAuthority.UDYAM: ["udyam_number", "udyam", "msme_registration", "entity_identifier", "company_name"],
    StatutoryAuthority.MCA: ["cin", "corporate_id", "entity_identifier", "company_name"],
    StatutoryAuthority.INCOME_TAX: ["pan", "entity_identifier", "company_name"],
    StatutoryAuthority.MII: ["certificate_reference", "mii_cert", "entity_identifier", "product_category", "company_name"],
    StatutoryAuthority.DEBARMENT: ["pan", "cin", "gstin", "gstn", "udyam_number", "udyam", "entity_identifier", "company_name", "firm_name"],
    StatutoryAuthority.DPIIT: ["certificate_number", "dipp_number", "dpiit_number", "recognition_number", "pan", "cin", "entity_identifier", "company_name"],
    StatutoryAuthority.EPFO: ["establishment_code", "epfo_code", "epfo_establishment_code", "pan", "entity_identifier", "establishment_name", "company_name"],
    StatutoryAuthority.ESIC: ["esic_code", "employer_code", "esic_employer_code", "pan", "entity_identifier", "employer_name", "company_name"],
}


class StatutoryVerificationOrchestrator:
    """
    Orchestrates statutory verification queries against authoritative registries.
    Executes multiple source adapters concurrently with complete fault isolation.
    """

    def __init__(self, registry: Optional[StatutoryAdapterRegistry] = None) -> None:
        self.registry = registry or get_statutory_registry()

    def resolve_query_identifier(
        self,
        authority: StatutoryAuthority,
        identifiers: Dict[str, str],
        fallback_name: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Resolves query identifier and its type for a specific statutory authority.
        Returns tuple: (query_identifier, identifier_type).
        """
        keys = AUTHORITY_IDENTIFIER_KEYS.get(authority, ["entity_identifier", "company_name"])
        for k in keys:
            val = identifiers.get(k)
            if val and str(val).strip():
                return str(val).strip(), k

        # Fallback to general company name if available
        if fallback_name and str(fallback_name).strip():
            return str(fallback_name).strip(), "company_name"

        # Fallback to first available value in identifiers
        for k, v in identifiers.items():
            if v and str(v).strip():
                return str(v).strip(), k

        return "", "unknown"

    async def execute_adapter(
        self,
        adapter: BaseSourceAdapter,
        query_identifier: str,
        identifier_type: str,
        as_of_date: Optional[date] = None,
        mode: SourceMode = SourceMode.MOCK,
        db: Optional[AsyncSession] = None,
        timeout_seconds: float = 10.0,
        **kwargs: Any,
    ) -> SourceVerificationResult:
        """
        Executes a single adapter with strict timeout and exception isolation.
        Guarantees that no individual adapter crash can disrupt the orchestrator.
        """
        retrieved_at = datetime.now(timezone.utc)
        v_id = str(uuid.uuid4())

        try:
            result = await asyncio.wait_for(
                adapter.verify(
                    query_identifier=query_identifier,
                    identifier_type=identifier_type,
                    as_of_date=as_of_date,
                    mode=mode,
                    db=db,
                    **kwargs,
                ),
                timeout=timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Statutory adapter {adapter.source_name} timed out after {timeout_seconds}s")
            return SourceVerificationResult(
                verification_id=v_id,
                authority=adapter.authority,
                source_name=adapter.source_name,
                query_identifier=query_identifier,
                identifier_type=identifier_type,
                mode=mode,
                connection_status=SourceConnectionStatus.TIMEOUT,
                verification_status=SourceVerificationStatus.FAILED,
                retrieved_at=retrieved_at,
                as_of_date=as_of_date,
                data_payload={},
                confidence_score=0.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message=f"Request to {adapter.source_name} timed out after {timeout_seconds} seconds",
                execution_time_ms=timeout_seconds * 1000,
            )
        except Exception as exc:
            logger.error(f"Statutory adapter {adapter.source_name} execution error: {exc}", exc_info=True)
            return SourceVerificationResult(
                verification_id=v_id,
                authority=adapter.authority,
                source_name=adapter.source_name,
                query_identifier=query_identifier,
                identifier_type=identifier_type,
                mode=mode,
                connection_status=SourceConnectionStatus.ERROR,
                verification_status=SourceVerificationStatus.FAILED,
                retrieved_at=retrieved_at,
                as_of_date=as_of_date,
                data_payload={},
                confidence_score=0.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message=f"Source adapter failure: {str(exc)}",
                execution_time_ms=0.0,
            )

    async def verify_statutory_sources(
        self,
        query: StatutoryVerificationQuery,
        db: Optional[AsyncSession] = None,
        persist: bool = True,
        timeout_seconds: float = 10.0,
    ) -> BidderStatutoryVerificationSummary:
        """
        Orchestrates multi-source statutory verification for given query.
        Concurrently queries requested authorities, aggregates results,
        and optionally persists records to PostgreSQL.
        """
        fallback_name: Optional[str] = None
        bidder_uuid: Optional[UUID] = None
        tender_uuid: Optional[UUID] = None

        if query.bidder_id:
            try:
                bidder_uuid = UUID(str(query.bidder_id))
            except (ValueError, TypeError):
                bidder_uuid = None

        if query.tender_id:
            try:
                tender_uuid = UUID(str(query.tender_id))
            except (ValueError, TypeError):
                tender_uuid = None

        # Fetch bidder entity information if bidder_id provided and db available
        if bidder_uuid and db:
            try:
                stmt = select(Bidder).where(Bidder.id == bidder_uuid)
                res = await db.execute(stmt)
                bidder_row = res.scalars().first()
                if bidder_row:
                    fallback_name = bidder_row.company_name
                    if not tender_uuid and bidder_row.tender_id:
                        tender_uuid = bidder_row.tender_id
                else:
                    # Target bidder not present in DB; do not violate FK constraint on persistence
                    bidder_uuid = None
            except Exception as e:
                logger.warning(f"Could not load bidder context for {bidder_uuid}: {e}")
                bidder_uuid = None

        if tender_uuid and db:
            try:
                from app.models.tender import Tender
                stmt_t = select(Tender.id).where(Tender.id == tender_uuid)
                res_t = await db.execute(stmt_t)
                if not res_t.scalars().first():
                    tender_uuid = None
            except Exception as e:
                logger.warning(f"Could not verify tender foreign key for {tender_uuid}: {e}")
                tender_uuid = None


        # Select authorities to query
        authorities_to_run = query.authorities or self.registry.list_supported_authorities()

        async def _run_adapter(adp: BaseSourceAdapter, q_id: str, id_type: str) -> SourceVerificationResult:
            if db is not None:
                async with AsyncSessionLocal() as task_session:
                    return await self.execute_adapter(
                        adapter=adp,
                        query_identifier=q_id,
                        identifier_type=id_type,
                        as_of_date=query.as_of_date,
                        mode=query.mode,
                        db=task_session,
                        timeout_seconds=timeout_seconds,
                        **query.identifiers,
                    )
            else:
                return await self.execute_adapter(
                    adapter=adp,
                    query_identifier=q_id,
                    identifier_type=id_type,
                    as_of_date=query.as_of_date,
                    mode=query.mode,
                    db=None,
                    timeout_seconds=timeout_seconds,
                    **query.identifiers,
                )

        tasks = []
        for auth in authorities_to_run:
            adapter = self.registry.get_adapter(auth)
            if not adapter:
                logger.warning(f"No adapter registered for authority: {auth}")
                continue

            q_id, id_type = self.resolve_query_identifier(
                authority=auth,
                identifiers=query.identifiers,
                fallback_name=fallback_name,
            )

            tasks.append(_run_adapter(adapter, q_id, id_type))

        # Run concurrently with gather
        results: List[SourceVerificationResult] = []
        if tasks:
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in raw_results:
                if isinstance(r, SourceVerificationResult):
                    results.append(r)
                elif isinstance(r, Exception):
                    results.append(
                        SourceVerificationResult(
                            verification_id=str(uuid.uuid4()),
                            authority=StatutoryAuthority.GSTN,  # Generic fallback
                            source_name="Unknown Source",
                            query_identifier="",
                            identifier_type="unknown",
                            mode=query.mode,
                            connection_status=SourceConnectionStatus.ERROR,
                            verification_status=SourceVerificationStatus.FAILED,
                            error_message=f"Async task failure: {str(r)}",
                        )
                    )

        # Optional PostgreSQL persistence
        if persist and db and results:
            try:
                for r in results:
                    v_uuid = UUID(r.verification_id) if isinstance(r.verification_id, str) else r.verification_id
                    rec = StatutoryVerificationRecord(
                        tender_id=tender_uuid,
                        bidder_id=bidder_uuid,
                        verification_id=v_uuid,
                        authority=r.authority.value,
                        source_name=r.source_name,
                        query_identifier=r.query_identifier,
                        identifier_type=r.identifier_type,
                        mode=r.mode.value,
                        connection_status=r.connection_status.value,
                        verification_status=r.verification_status.value,
                        retrieved_at=r.retrieved_at,
                        as_of_date=r.as_of_date,
                        data_payload=r.data_payload,
                        confidence_score=r.confidence_score,
                        provenance_note=r.provenance_note,
                        error_message=r.error_message,
                        execution_time_ms=r.execution_time_ms,
                    )
                    db.add(rec)
                await db.flush()
            except Exception as e:
                logger.error(f"Failed to persist statutory verification records: {e}", exc_info=True)

        successful_conn = sum(1 for r in results if r.connection_status == SourceConnectionStatus.SUCCESS)
        failed_conn = len(results) - successful_conn

        return BidderStatutoryVerificationSummary(
            bidder_id=str(bidder_uuid) if bidder_uuid else query.bidder_id,
            tender_id=str(tender_uuid) if tender_uuid else query.tender_id,
            results=results,
            total_sources=len(results),
            successful_connections=successful_conn,
            failed_connections=failed_conn,
            as_of_date=query.as_of_date,
            verified_at=datetime.now(timezone.utc),
            disclaimer=STATUTORY_MOCK_BANNER,
        )


# Global singleton orchestrator
_default_orchestrator = StatutoryVerificationOrchestrator()


def get_statutory_orchestrator() -> StatutoryVerificationOrchestrator:
    """Dependency / accessor for global statutory orchestrator."""
    return _default_orchestrator
