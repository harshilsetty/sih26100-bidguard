"""
app.services.statutory_adapters.mii_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Adapter for Make in India (MII) / DPIIT Local Content verification.
Queries mock MII database, extracts verified local content percentage,
certifying authority, certificate reference, and enforces status separation and payload sanitization.
"""

import time
import uuid
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.schemas.statutory_verification import (
    StatutoryAuthority,
    SourceMode,
    SourceConnectionStatus,
    SourceVerificationStatus,
    SourceVerificationResult,
    STATUTORY_MOCK_BANNER,
)
from app.models.mock_sources import MockMIIRecord
from app.services.statutory_adapters.base import BaseSourceAdapter, sanitize_payload


class MIISourceAdapter(BaseSourceAdapter):
    """Statutory adapter for Make in India (MII) verification."""

    @property
    def authority(self) -> StatutoryAuthority:
        return StatutoryAuthority.MII

    @property
    def source_name(self) -> str:
        return "Make in India (MII) / Local Content Registry"

    def get_supported_identifier_types(self) -> List[str]:
        return ["certificate_reference", "entity_identifier", "product_category"]

    async def verify(
        self,
        query_identifier: str,
        identifier_type: str = "auto",
        as_of_date: Optional[date] = None,
        mode: SourceMode = SourceMode.MOCK,
        db: Optional[AsyncSession] = None,
        **kwargs: Any,
    ) -> SourceVerificationResult:
        start_time = time.perf_counter()
        v_id = str(uuid.uuid4())
        retrieved_at = datetime.now(timezone.utc)

        if not query_identifier or not str(query_identifier).strip():
            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=query_identifier or "",
                identifier_type=identifier_type,
                mode=mode,
                connection_status=SourceConnectionStatus.SUCCESS,
                verification_status=SourceVerificationStatus.NOT_FOUND,
                retrieved_at=retrieved_at,
                as_of_date=as_of_date,
                data_payload={},
                confidence_score=1.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message="Empty query identifier provided",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        clean_id = str(query_identifier).strip()

        if db is None:
            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=clean_id,
                identifier_type=identifier_type,
                mode=mode,
                connection_status=SourceConnectionStatus.UNAVAILABLE,
                verification_status=SourceVerificationStatus.FAILED,
                retrieved_at=retrieved_at,
                as_of_date=as_of_date,
                data_payload={},
                confidence_score=0.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message="Database session unavailable for MII query",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        try:
            stmt = select(MockMIIRecord).where(
                or_(
                    MockMIIRecord.certificate_reference == clean_id,
                    MockMIIRecord.entity_identifier == clean_id,
                    MockMIIRecord.product_category.ilike(f"%{clean_id}%"),
                )
            )
            result = await db.execute(stmt)
            record: Optional[MockMIIRecord] = result.scalars().first()

            if not record:
                return SourceVerificationResult(
                    verification_id=v_id,
                    authority=self.authority,
                    source_name=self.source_name,
                    query_identifier=clean_id,
                    identifier_type=identifier_type,
                    mode=mode,
                    connection_status=SourceConnectionStatus.SUCCESS,
                    verification_status=SourceVerificationStatus.NOT_FOUND,
                    retrieved_at=retrieved_at,
                    as_of_date=as_of_date,
                    data_payload={},
                    confidence_score=1.0,
                    provenance_note=STATUTORY_MOCK_BANNER,
                    error_message=f"Entity not found in MII registry: {clean_id}",
                    execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                )

            status_str = (record.verification_status or "").upper()
            if "VERIFIED" in status_str:
                ver_status = SourceVerificationStatus.VERIFIED
            elif "NON_LOCAL" in status_str:
                ver_status = SourceVerificationStatus.VERIFIED
            elif "CONTRADICTION" in status_str:
                ver_status = SourceVerificationStatus.DISCREPANCY
            else:
                ver_status = SourceVerificationStatus.UNVERIFIED

            raw_dict = {
                "product_category": record.product_category,
                "verified_local_content": float(record.verified_local_content) if record.verified_local_content is not None else 0.0,
                "verification_status": record.verification_status,
                "certifying_authority": record.certifying_authority,
                "certificate_reference": record.certificate_reference,
                "verification_id": record.verification_id,
            }

            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=record.certificate_reference or clean_id,
                identifier_type="certificate_reference" if record.certificate_reference == clean_id else identifier_type,
                mode=mode,
                connection_status=SourceConnectionStatus.SUCCESS,
                verification_status=ver_status,
                retrieved_at=retrieved_at,
                as_of_date=as_of_date,
                data_payload=sanitize_payload(raw_dict),
                confidence_score=1.0,
                provenance_note=f"{STATUTORY_MOCK_BANNER} (ID: {record.verification_id})",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        except Exception as e:
            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=clean_id,
                identifier_type=identifier_type,
                mode=mode,
                connection_status=SourceConnectionStatus.ERROR,
                verification_status=SourceVerificationStatus.FAILED,
                retrieved_at=retrieved_at,
                as_of_date=as_of_date,
                data_payload={},
                confidence_score=0.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message=f"MII verification query exception: {str(e)}",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
