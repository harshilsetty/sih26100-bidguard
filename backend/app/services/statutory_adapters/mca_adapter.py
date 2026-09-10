"""
app.services.statutory_adapters.mca_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Adapter for Ministry of Corporate Affairs (MCA) corporate registry verification.
Queries mock MCA database, extracts CIN, company status, incorporation date,
authorized capital, and enforces status separation and payload sanitization.
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
from app.models.mock_sources import MockMCARecord
from app.services.statutory_adapters.base import BaseSourceAdapter, sanitize_payload


class MCASourceAdapter(BaseSourceAdapter):
    """Statutory adapter for MCA corporate registry verification."""

    @property
    def authority(self) -> StatutoryAuthority:
        return StatutoryAuthority.MCA

    @property
    def source_name(self) -> str:
        return "Ministry of Corporate Affairs (MCA)"

    def get_supported_identifier_types(self) -> List[str]:
        return ["cin", "entity_identifier", "legal_name"]

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
                error_message="Database session unavailable for MCA query",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        try:
            stmt = select(MockMCARecord).where(
                or_(
                    MockMCARecord.cin == clean_id,
                    MockMCARecord.entity_identifier == clean_id,
                    MockMCARecord.legal_name.ilike(f"%{clean_id}%"),
                )
            )
            result = await db.execute(stmt)
            record: Optional[MockMCARecord] = result.scalars().first()

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
                    error_message=f"Entity not found in MCA registry: {clean_id}",
                    execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                )

            status_str = (record.company_status or "").upper()
            if status_str in ["ACTIVE"]:
                ver_status = SourceVerificationStatus.VERIFIED
            elif status_str in ["STRUCK_OFF", "DORMANT", "DISSOLVED", "UNDER_LIQUIDATION"]:
                ver_status = SourceVerificationStatus.INACTIVE
            else:
                ver_status = SourceVerificationStatus.UNVERIFIED

            temporal_valid = True
            if as_of_date and record.incorporation_date:
                try:
                    inc_date = datetime.strptime(record.incorporation_date, "%Y-%m-%d").date()
                    if inc_date > as_of_date:
                        temporal_valid = False
                except (ValueError, TypeError):
                    pass

            raw_dict = {
                "cin": record.cin,
                "legal_name": record.legal_name,
                "company_status": record.company_status,
                "incorporation_date": record.incorporation_date,
                "registered_state": record.registered_state,
                "company_type": record.company_type,
                "authorized_capital_cr": float(record.authorized_capital_cr) if record.authorized_capital_cr is not None else 0.0,
                "verification_id": record.verification_id,
                "temporal_valid": temporal_valid,
            }

            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=record.cin,
                identifier_type="cin" if record.cin == clean_id else identifier_type,
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
                error_message=f"MCA verification query exception: {str(e)}",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
