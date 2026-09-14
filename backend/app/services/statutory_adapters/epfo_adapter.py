"""
app.services.statutory_adapters.epfo_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Statutory Source Adapter for EPFO (Employees' Provident Fund Organisation).
Establishment-level verification ONLY. No employee-level information.

Authoritative Identity Hierarchy:
Establishment Code > PAN > entity_identifier > establishment_name (weak)

Rules:
- Authoritative match confirms establishment registration status.
- Company/establishment name alone MUST NEVER establish authoritative identity.
- Name-only matches return UNVERIFIED with officer review required.
- All mock data is sanitized and labeled with SourceMode.MOCK.
"""

import re
import time
import uuid
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.schemas.statutory_verification import (
    StatutoryAuthority,
    SourceMode,
    SourceConnectionStatus,
    SourceVerificationStatus,
    SourceVerificationResult,
    STATUTORY_MOCK_BANNER,
)
from app.models.mock_sources import MockEPFORecord
from app.services.statutory_adapters.base import (
    BaseSourceAdapter,
    sanitize_payload,
    validate_bidder_identity_consistency,
)

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$", re.IGNORECASE)
EPFO_CODE_REGEX = re.compile(r"^[A-Z]{2}[A-Z]{3}[0-9]{7}[0-9]{3}$", re.IGNORECASE)


class EPFOSourceAdapter(BaseSourceAdapter):
    """Statutory adapter for EPFO establishment verification."""

    @property
    def authority(self) -> StatutoryAuthority:
        return StatutoryAuthority.EPFO

    @property
    def source_name(self) -> str:
        return "EPFO Establishment Registry"

    def get_supported_identifier_types(self) -> List[str]:
        return [
            "establishment_code",
            "epfo_code",
            "pan",
            "entity_identifier",
            "establishment_name",
            "company_name",
            "auto",
        ]

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

        clean_id = str(query_identifier).strip() if query_identifier else ""

        # Extract extra identifier candidates from kwargs
        extra_pan = kwargs.get("pan") or kwargs.get("PAN")
        extra_est_code = (
            kwargs.get("establishment_code")
            or kwargs.get("epfo_code")
            or kwargs.get("epfo_establishment_code")
        )
        extra_entity_id = kwargs.get("entity_identifier")
        extra_name = (
            kwargs.get("establishment_name")
            or kwargs.get("company_name")
            or kwargs.get("firm_name")
            or kwargs.get("entity_name")
        )

        if not clean_id and not any([extra_pan, extra_est_code, extra_entity_id, extra_name]):
            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier="",
                identifier_type=identifier_type,
                mode=mode,
                connection_status=SourceConnectionStatus.SUCCESS,
                verification_status=SourceVerificationStatus.NOT_FOUND,
                retrieved_at=retrieved_at,
                as_of_date=as_of_date,
                data_payload={
                    "is_covered": False,
                    "is_ambiguous_match": False,
                    "officer_review_required": False,
                },
                confidence_score=1.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message="Empty query identifier provided",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

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
                error_message="Database session unavailable for EPFO query",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        try:
            # 1. Authoritative Identity Resolution
            # Hierarchy: Establishment Code > PAN > entity_identifier
            matched_record: Optional[MockEPFORecord] = None
            matched_by: Optional[str] = None

            # Resolve query_identifier if 'auto'
            code_val = extra_est_code or (
                clean_id if (identifier_type in ("establishment_code", "epfo_code") or EPFO_CODE_REGEX.match(clean_id)) else None
            )
            pan_val = extra_pan or (clean_id if (identifier_type == "pan" or PAN_REGEX.match(clean_id.upper())) else None)
            entity_val = extra_entity_id or (clean_id if identifier_type == "entity_identifier" else None)

            if identifier_type == "auto" and not any([code_val, pan_val]):
                if clean_id.upper().startswith("DEMO-") or clean_id.upper().startswith("BIDDER-") or clean_id.upper().startswith("ENT-"):
                    entity_val = clean_id

            # Priority 1: Establishment Code
            if code_val and not matched_record:
                res = await db.execute(select(MockEPFORecord).where(MockEPFORecord.establishment_code == code_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "ESTABLISHMENT_CODE"

            # Priority 2: PAN
            if pan_val and not matched_record:
                res = await db.execute(select(MockEPFORecord).where(MockEPFORecord.pan == pan_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "PAN"

            # Priority 3: Entity Identifier
            if entity_val and not matched_record:
                res = await db.execute(select(MockEPFORecord).where(MockEPFORecord.entity_identifier == entity_val.strip()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "ENTITY_IDENTIFIER"

            # Authoritative Match Found
            if matched_record:
                # Cross-validate located record against authoritative bidder identity (PAN > GSTIN > Udyam)
                extra_gstin = kwargs.get("gstin") or kwargs.get("GSTIN") or kwargs.get("gstn")
                extra_udyam = kwargs.get("udyam") or kwargs.get("udyam_number") or kwargs.get("udyam_registration_number")

                is_consistent, conflict_reason = validate_bidder_identity_consistency(
                    record_pan=matched_record.pan,
                    record_cin=None,
                    query_pan=pan_val,
                    query_cin=None,
                    query_gstin=extra_gstin,
                    query_udyam=extra_udyam,
                )

                if not is_consistent:
                    # Identity Conflict detected! Never silently accept a record for a different entity.
                    payload = {
                        "is_covered": False,
                        "status": "IDENTITY_CONFLICT",
                        "establishment_code": matched_record.establishment_code,
                        "establishment_name": matched_record.establishment_name,
                        "record_pan": matched_record.pan,
                        "query_pan": pan_val,
                        "matched_by": matched_by,
                        "is_ambiguous_match": True,
                        "officer_review_required": True,
                        "conflict_detected": True,
                        "review_reason": conflict_reason,
                    }
                    return SourceVerificationResult(
                        verification_id=v_id,
                        authority=self.authority,
                        source_name=self.source_name,
                        query_identifier=clean_id or (matched_record.establishment_code or ""),
                        identifier_type=matched_by.lower() if matched_by else identifier_type,
                        mode=mode,
                        connection_status=SourceConnectionStatus.SUCCESS,
                        verification_status=SourceVerificationStatus.UNVERIFIED,
                        retrieved_at=retrieved_at,
                        as_of_date=as_of_date,
                        data_payload=sanitize_payload(payload),
                        confidence_score=0.4,
                        provenance_note=STATUTORY_MOCK_BANNER,
                        error_message=f"Identity conflict: {conflict_reason}",
                        execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                    )

                raw_status = (matched_record.status or "").upper()
                if raw_status == "ACTIVE":
                    ver_status = SourceVerificationStatus.VERIFIED
                elif raw_status in ("INACTIVE", "CLOSED", "SUSPENDED"):
                    ver_status = SourceVerificationStatus.INACTIVE
                else:
                    ver_status = SourceVerificationStatus.UNVERIFIED

                payload = {
                    "is_covered": (ver_status == SourceVerificationStatus.VERIFIED),
                    "establishment_code": matched_record.establishment_code,
                    "establishment_name": matched_record.establishment_name,
                    "pan": matched_record.pan,
                    "status": raw_status,
                    "registration_date": matched_record.registration_date,
                    "office_name": matched_record.office_name,
                    "exemption_status": matched_record.exemption_status,
                    "matched_by": matched_by,
                    "is_ambiguous_match": False,
                    "officer_review_required": (ver_status != SourceVerificationStatus.VERIFIED),
                }

                return SourceVerificationResult(
                    verification_id=v_id,
                    authority=self.authority,
                    source_name=self.source_name,
                    query_identifier=clean_id or (matched_record.establishment_code or ""),
                    identifier_type=matched_by.lower() if matched_by else identifier_type,
                    mode=mode,
                    connection_status=SourceConnectionStatus.SUCCESS,
                    verification_status=ver_status,
                    retrieved_at=retrieved_at,
                    as_of_date=as_of_date,
                    data_payload=sanitize_payload(payload),
                    confidence_score=1.0,
                    provenance_note=STATUTORY_MOCK_BANNER,
                    error_message=None,
                    execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                )

            # 2. Supporting Candidate Signal: Name matching ONLY (Weak identifier)
            name_candidate = extra_name or clean_id
            if name_candidate and len(name_candidate.strip()) >= 3:
                clean_name = name_candidate.strip()
                res = await db.execute(
                    select(MockEPFORecord).where(
                        MockEPFORecord.establishment_name.ilike(f"%{clean_name}%")
                    )
                )
                name_rec = res.scalars().first()
                if name_rec:
                    # STRICT RULE: Name-only match MUST NEVER establish authoritative identity
                    # -> UNVERIFIED
                    # -> is_ambiguous_match = True
                    # -> officer_review_required = True
                    payload = {
                        "is_covered": False,
                        "candidate_establishment_code": name_rec.establishment_code,
                        "candidate_establishment_name": name_rec.establishment_name,
                        "candidate_status": name_rec.status,
                        "matched_by": "ESTABLISHMENT_NAME_ONLY",
                        "is_ambiguous_match": True,
                        "officer_review_required": True,
                        "review_reason": "Weak/ambiguous establishment-name-only match. Authoritative code or PAN required.",
                    }

                    return SourceVerificationResult(
                        verification_id=v_id,
                        authority=self.authority,
                        source_name=self.source_name,
                        query_identifier=clean_id,
                        identifier_type="establishment_name",
                        mode=mode,
                        connection_status=SourceConnectionStatus.SUCCESS,
                        verification_status=SourceVerificationStatus.UNVERIFIED,
                        retrieved_at=retrieved_at,
                        as_of_date=as_of_date,
                        data_payload=sanitize_payload(payload),
                        confidence_score=0.4,
                        provenance_note=STATUTORY_MOCK_BANNER,
                        error_message="Ambiguous establishment name match; unverified identity",
                        execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                    )

            # 3. Not Found in Registry
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
                data_payload={
                    "is_covered": False,
                    "is_ambiguous_match": False,
                    "officer_review_required": False,
                },
                confidence_score=1.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message="No establishment record found in EPFO registry",
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
                error_message=f"EPFO adapter error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
