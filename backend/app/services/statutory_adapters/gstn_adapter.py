"""
app.services.statutory_adapters.gstn_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Adapter for Goods & Services Tax Network (GSTN) verification.
Queries mock GSTN database, maps factual attributes, verifies active registration,
and adheres to strict status separation and payload sanitization.
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
from app.models.mock_sources import MockGSTNRecord
from app.services.statutory_adapters.base import BaseSourceAdapter, sanitize_payload


class GSTNSourceAdapter(BaseSourceAdapter):
    """Statutory adapter for GSTN verification."""

    @property
    def authority(self) -> StatutoryAuthority:
        return StatutoryAuthority.GSTN

    @property
    def source_name(self) -> str:
        return "Goods & Services Tax Network (GSTN)"

    def get_supported_identifier_types(self) -> List[str]:
        return ["gstin", "entity_identifier", "legal_name"]

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
                error_message="Database session unavailable for GSTN query",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        try:
            # Query resolution: Match gstin, entity_identifier, or legal_name
            stmt = select(MockGSTNRecord).where(
                or_(
                    MockGSTNRecord.gstin == clean_id,
                    MockGSTNRecord.entity_identifier == clean_id,
                    MockGSTNRecord.legal_name.ilike(f"%{clean_id}%"),
                )
            )
            result = await db.execute(stmt)
            record: Optional[MockGSTNRecord] = result.scalars().first()

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
                    error_message=f"Entity not found in GSTN registry: {clean_id}",
                    execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                )

            # Determine verification status
            status_str = (record.registration_status or "").upper()
            if status_str in ["ACTIVE", "REGULAR"]:
                ver_status = SourceVerificationStatus.VERIFIED
            elif status_str in ["INACTIVE", "CANCELLED", "SUSPENDED"]:
                ver_status = SourceVerificationStatus.INACTIVE
            else:
                ver_status = SourceVerificationStatus.UNVERIFIED

            # Temporal check: Evaluate historical validity if as_of_date provided
            temporal_valid = True
            if as_of_date and record.registration_date:
                try:
                    reg_date = datetime.strptime(record.registration_date, "%Y-%m-%d").date()
                    if reg_date > as_of_date:
                        temporal_valid = False
                except (ValueError, TypeError):
                    pass

            raw_dict = {
                "gstin": record.gstin,
                "legal_name": record.legal_name,
                "registration_status": record.registration_status,
                "registration_date": record.registration_date,
                "state": record.state,
                "verified_turnover": float(record.verified_turnover) if record.verified_turnover is not None else 0.0,
                "taxpayer_type": record.taxpayer_type,
                "filing_status": record.filing_status,
                "verification_id": record.verification_id,
                "temporal_valid": temporal_valid,
            }

            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=record.gstin,
                identifier_type="gstin" if record.gstin == clean_id else identifier_type,
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
                error_message=f"GSTN verification query exception: {str(e)}",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
