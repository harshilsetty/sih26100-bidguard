"""
app.services.statutory_adapters.income_tax_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Adapter for Income Tax Department (CBDT) PAN & tax compliance verification.
Queries mock Income Tax database, extracts PAN status, last filed ITR FY,
compliance status, and enforces status separation and payload sanitization.
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
from app.models.mock_sources import MockIncomeTaxRecord
from app.services.statutory_adapters.base import BaseSourceAdapter, sanitize_payload


class IncomeTaxSourceAdapter(BaseSourceAdapter):
    """Statutory adapter for Income Tax PAN & tax compliance verification."""

    @property
    def authority(self) -> StatutoryAuthority:
        return StatutoryAuthority.INCOME_TAX

    @property
    def source_name(self) -> str:
        return "Income Tax Department (CBDT)"

    def get_supported_identifier_types(self) -> List[str]:
        return ["pan", "entity_identifier", "entity_name"]

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
                error_message="Database session unavailable for Income Tax query",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        try:
            stmt = select(MockIncomeTaxRecord).where(
                or_(
                    MockIncomeTaxRecord.pan == clean_id,
                    MockIncomeTaxRecord.entity_identifier == clean_id,
                    MockIncomeTaxRecord.entity_name.ilike(f"%{clean_id}%"),
                )
            )
            result = await db.execute(stmt)
            record: Optional[MockIncomeTaxRecord] = result.scalars().first()

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
                    error_message=f"Entity not found in Income Tax registry: {clean_id}",
                    execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                )

            status_str = (record.pan_status or "").upper()
            compliance_str = (record.tax_compliance_status or "").upper()
            if status_str == "ACTIVE" and compliance_str in ["COMPLIANT", "REGULAR"]:
                ver_status = SourceVerificationStatus.VERIFIED
            elif status_str in ["INOPERATIVE", "CANCELLED", "INVALID", "DEACTIVATED"]:
                ver_status = SourceVerificationStatus.INACTIVE
            elif compliance_str in ["NON_COMPLIANT", "DEFAULT"]:
                ver_status = SourceVerificationStatus.DISCREPANCY
            else:
                ver_status = SourceVerificationStatus.UNVERIFIED

            raw_dict = {
                "pan": record.pan,
                "entity_name": record.entity_name,
                "pan_status": record.pan_status,
                "taxpayer_type": record.taxpayer_type,
                "last_itr_filed_fy": record.last_itr_filed_fy,
                "tax_compliance_status": record.tax_compliance_status,
                "verification_id": record.verification_id,
            }

            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=record.pan,
                identifier_type="pan" if record.pan == clean_id else identifier_type,
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
                error_message=f"Income Tax verification query exception: {str(e)}",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
