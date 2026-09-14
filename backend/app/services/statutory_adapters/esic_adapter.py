"""
app.services.statutory_adapters.esic_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Statutory Source Adapter for ESIC (Employees' State Insurance Corporation).
Establishment/employer-level verification ONLY. No employee-level information.

Authoritative Identity Hierarchy:
ESIC Code > PAN > entity_identifier > employer_name (weak)

Rules:
- Authoritative match confirms employer registration status.
- Company/employer name alone MUST NEVER establish authoritative identity.
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
from app.models.mock_sources import MockESICRecord
from app.services.statutory_adapters.base import (
    BaseSourceAdapter,
    sanitize_payload,
    validate_bidder_identity_consistency,
)

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$", re.IGNORECASE)
ESIC_CODE_REGEX = re.compile(r"^[0-9]{17}$")


class ESICSourceAdapter(BaseSourceAdapter):
    """Statutory adapter for ESIC employer verification."""

    @property
    def authority(self) -> StatutoryAuthority:
        return StatutoryAuthority.ESIC

    @property
    def source_name(self) -> str:
        return "ESIC Employer Registry"

    def get_supported_identifier_types(self) -> List[str]:
        return [
            "esic_code",
            "employer_code",
            "pan",
            "entity_identifier",
            "employer_name",
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
        extra_esic_code = (
            kwargs.get("esic_code")
            or kwargs.get("employer_code")
            or kwargs.get("esic_employer_code")
        )
        extra_entity_id = kwargs.get("entity_identifier")
        extra_name = (
            kwargs.get("employer_name")
            or kwargs.get("company_name")
            or kwargs.get("firm_name")
            or kwargs.get("entity_name")
        )

        if not clean_id and not any([extra_pan, extra_esic_code, extra_entity_id, extra_name]):
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
                error_message="Database session unavailable for ESIC query",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        try:
            # 1. Authoritative Identity Resolution
            # Hierarchy: ESIC Code > PAN > entity_identifier
            matched_record: Optional[MockESICRecord] = None
            matched_by: Optional[str] = None

            # Resolve query_identifier if 'auto'
            code_val = extra_esic_code or (
                clean_id if (identifier_type in ("esic_code", "employer_code") or ESIC_CODE_REGEX.match(clean_id)) else None
            )
            pan_val = extra_pan or (clean_id if (identifier_type == "pan" or PAN_REGEX.match(clean_id.upper())) else None)
            entity_val = extra_entity_id or (clean_id if identifier_type == "entity_identifier" else None)

            if identifier_type == "auto" and not any([code_val, pan_val]):
                if clean_id.upper().startswith("DEMO-") or clean_id.upper().startswith("BIDDER-") or clean_id.upper().startswith("ENT-"):
                    entity_val = clean_id

            # Priority 1: ESIC Code
            if code_val and not matched_record:
                res = await db.execute(select(MockESICRecord).where(MockESICRecord.esic_code == code_val.strip()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "ESIC_CODE"

            # Priority 2: PAN
            if pan_val and not matched_record:
                res = await db.execute(select(MockESICRecord).where(MockESICRecord.pan == pan_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "PAN"

            # Priority 3: Entity Identifier
            if entity_val and not matched_record:
                res = await db.execute(select(MockESICRecord).where(MockESICRecord.entity_identifier == entity_val.strip()))
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
                        "esic_code": matched_record.esic_code,
                        "employer_name": matched_record.employer_name,
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
                        query_identifier=clean_id or (matched_record.esic_code or ""),
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
                elif raw_status in ("INACTIVE", "SUSPENDED", "DEREGISTERED", "CLOSED"):
                    ver_status = SourceVerificationStatus.INACTIVE
                else:
                    ver_status = SourceVerificationStatus.UNVERIFIED

                payload = {
                    "is_covered": (ver_status == SourceVerificationStatus.VERIFIED),
                    "esic_code": matched_record.esic_code,
                    "employer_name": matched_record.employer_name,
                    "pan": matched_record.pan,
                    "status": raw_status,
                    "registration_date": matched_record.registration_date,
                    "region": matched_record.region,
                    "matched_by": matched_by,
                    "is_ambiguous_match": False,
                    "officer_review_required": (ver_status != SourceVerificationStatus.VERIFIED),
                }

                return SourceVerificationResult(
                    verification_id=v_id,
                    authority=self.authority,
                    source_name=self.source_name,
                    query_identifier=clean_id or (matched_record.esic_code or ""),
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
                    select(MockESICRecord).where(
                        MockESICRecord.employer_name.ilike(f"%{clean_name}%")
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
                        "candidate_esic_code": name_rec.esic_code,
                        "candidate_employer_name": name_rec.employer_name,
                        "candidate_status": name_rec.status,
                        "matched_by": "EMPLOYER_NAME_ONLY",
                        "is_ambiguous_match": True,
                        "officer_review_required": True,
                        "review_reason": "Weak/ambiguous employer-name-only match. Authoritative ESIC code or PAN required.",
                    }

                    return SourceVerificationResult(
                        verification_id=v_id,
                        authority=self.authority,
                        source_name=self.source_name,
                        query_identifier=clean_id,
                        identifier_type="employer_name",
                        mode=mode,
                        connection_status=SourceConnectionStatus.SUCCESS,
                        verification_status=SourceVerificationStatus.UNVERIFIED,
                        retrieved_at=retrieved_at,
                        as_of_date=as_of_date,
                        data_payload=sanitize_payload(payload),
                        confidence_score=0.4,
                        provenance_note=STATUTORY_MOCK_BANNER,
                        error_message="Ambiguous employer name match; unverified identity",
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
                error_message="No employer record found in ESIC registry",
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
                error_message=f"ESIC adapter error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
