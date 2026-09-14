"""
app.services.statutory_adapters.dpiit_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Statutory Source Adapter for DPIIT / Startup India Recognition.
Authoritative Identity Hierarchy:
PAN > CIN > GSTIN > Udyam > entity_identifier > company_name (weak)

Rules:
- Authoritative match confirms verification status (VERIFIED, INACTIVE, EXPIRED).
- Company name alone MUST NEVER establish authoritative identity.
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
from app.models.mock_sources import MockDPIITRecord
from app.services.statutory_adapters.base import (
    BaseSourceAdapter,
    sanitize_payload,
    validate_bidder_identity_consistency,
)

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$", re.IGNORECASE)
CIN_REGEX = re.compile(r"^[UL][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$", re.IGNORECASE)
DPIIT_CERT_REGEX = re.compile(r"^(DIPP|DPIIT)[0-9]{4,8}$", re.IGNORECASE)


class DPIITSourceAdapter(BaseSourceAdapter):
    """Statutory adapter for DPIIT / Startup India verification."""

    @property
    def authority(self) -> StatutoryAuthority:
        return StatutoryAuthority.DPIIT

    @property
    def source_name(self) -> str:
        return "DPIIT / Startup India"

    def get_supported_identifier_types(self) -> List[str]:
        return [
            "dipp_number",
            "dpiit_number",
            "certificate_number",
            "recognition_number",
            "pan",
            "cin",
            "entity_identifier",
            "company_name",
            "firm_name",
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
        extra_cin = kwargs.get("cin") or kwargs.get("CIN")
        extra_cert = (
            kwargs.get("certificate_number")
            or kwargs.get("dipp_number")
            or kwargs.get("dpiit_number")
            or kwargs.get("recognition_number")
        )
        extra_entity_id = kwargs.get("entity_identifier")
        extra_name = kwargs.get("company_name") or kwargs.get("firm_name") or kwargs.get("entity_name")

        if not clean_id and not any([extra_pan, extra_cin, extra_cert, extra_entity_id, extra_name]):
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
                    "is_recognized": False,
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
                error_message="Database session unavailable for DPIIT query",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        try:
            # 1. Authoritative Identity Resolution
            # Hierarchy: Certificate Number > PAN > CIN > entity_identifier
            matched_record: Optional[MockDPIITRecord] = None
            matched_by: Optional[str] = None

            # Resolve query_identifier if 'auto'
            cert_val = extra_cert or (
                clean_id if (identifier_type in ("certificate_number", "dipp_number", "dpiit_number", "recognition_number") or DPIIT_CERT_REGEX.match(clean_id)) else None
            )
            pan_val = extra_pan or (clean_id if (identifier_type == "pan" or PAN_REGEX.match(clean_id.upper())) else None)
            cin_val = extra_cin or (clean_id if (identifier_type == "cin" or CIN_REGEX.match(clean_id.upper())) else None)
            entity_val = extra_entity_id or (clean_id if identifier_type == "entity_identifier" else None)

            # In auto mode, recognize DEMO- or BIDDER- IDs as entity_identifier
            if identifier_type == "auto" and not any([cert_val, pan_val, cin_val]):
                if clean_id.upper().startswith("DEMO-") or clean_id.upper().startswith("BIDDER-") or clean_id.upper().startswith("ENT-"):
                    entity_val = clean_id

            # Priority 1: Certificate / Recognition Number
            if cert_val and not matched_record:
                res = await db.execute(select(MockDPIITRecord).where(MockDPIITRecord.certificate_number == cert_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "CERTIFICATE_NUMBER"

            # Priority 2: PAN
            if pan_val and not matched_record:
                res = await db.execute(select(MockDPIITRecord).where(MockDPIITRecord.pan == pan_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "PAN"

            # Priority 3: CIN
            if cin_val and not matched_record:
                res = await db.execute(select(MockDPIITRecord).where(MockDPIITRecord.cin == cin_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "CIN"

            # Priority 4: Entity Identifier
            if entity_val and not matched_record:
                res = await db.execute(select(MockDPIITRecord).where(MockDPIITRecord.entity_identifier == entity_val.strip()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "ENTITY_IDENTIFIER"

            # Authoritative Match Found
            if matched_record:
                # Cross-validate located record against authoritative bidder identity (PAN > CIN > GSTIN > Udyam)
                extra_gstin = kwargs.get("gstin") or kwargs.get("GSTIN") or kwargs.get("gstn")
                extra_udyam = kwargs.get("udyam") or kwargs.get("udyam_number") or kwargs.get("udyam_registration_number")

                is_consistent, conflict_reason = validate_bidder_identity_consistency(
                    record_pan=matched_record.pan,
                    record_cin=matched_record.cin,
                    query_pan=pan_val,
                    query_cin=cin_val,
                    query_gstin=extra_gstin,
                    query_udyam=extra_udyam,
                )

                if not is_consistent:
                    # Identity Conflict detected! Never silently accept a record for a different entity.
                    payload = {
                        "is_recognized": False,
                        "recognition_status": "IDENTITY_CONFLICT",
                        "certificate_number": matched_record.certificate_number,
                        "entity_name": matched_record.entity_name,
                        "record_pan": matched_record.pan,
                        "record_cin": matched_record.cin,
                        "query_pan": pan_val,
                        "query_cin": cin_val,
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
                        query_identifier=clean_id or (matched_record.certificate_number or ""),
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
                elif raw_status in ("INACTIVE", "DERECOGNIZED"):
                    ver_status = SourceVerificationStatus.INACTIVE
                elif raw_status == "EXPIRED":
                    ver_status = SourceVerificationStatus.EXPIRED
                else:
                    ver_status = SourceVerificationStatus.UNVERIFIED

                payload = {
                    "is_recognized": (ver_status == SourceVerificationStatus.VERIFIED),
                    "recognition_status": raw_status,
                    "certificate_number": matched_record.certificate_number,
                    "entity_name": matched_record.entity_name,
                    "pan": matched_record.pan,
                    "cin": matched_record.cin,
                    "recognition_date": matched_record.recognition_date,
                    "valid_until": matched_record.valid_until,
                    "industry_sector": matched_record.industry_sector,
                    "matched_by": matched_by,
                    "is_ambiguous_match": False,
                    "officer_review_required": (ver_status != SourceVerificationStatus.VERIFIED),
                }

                return SourceVerificationResult(
                    verification_id=v_id,
                    authority=self.authority,
                    source_name=self.source_name,
                    query_identifier=clean_id or (matched_record.certificate_number or ""),
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

            # 2. Supporting Candidate Signal: Company-name matching ONLY (Weak identifier)
            name_candidate = extra_name or clean_id
            if name_candidate and len(name_candidate.strip()) >= 3:
                clean_name = name_candidate.strip()
                res = await db.execute(
                    select(MockDPIITRecord).where(
                        MockDPIITRecord.entity_name.ilike(f"%{clean_name}%")
                    )
                )
                name_rec = res.scalars().first()
                if name_rec:
                    # STRICT RULE: Name-only match MUST NEVER establish authoritative identity
                    # -> UNVERIFIED
                    # -> is_ambiguous_match = True
                    # -> officer_review_required = True
                    payload = {
                        "is_recognized": False,
                        "candidate_certificate_number": name_rec.certificate_number,
                        "candidate_entity_name": name_rec.entity_name,
                        "candidate_status": name_rec.status,
                        "recognition_date": name_rec.recognition_date,
                        "matched_by": "COMPANY_NAME_ONLY",
                        "is_ambiguous_match": True,
                        "officer_review_required": True,
                        "review_reason": "Weak/ambiguous company-name-only match. Authoritative identifier required.",
                    }

                    return SourceVerificationResult(
                        verification_id=v_id,
                        authority=self.authority,
                        source_name=self.source_name,
                        query_identifier=clean_id,
                        identifier_type="company_name",
                        mode=mode,
                        connection_status=SourceConnectionStatus.SUCCESS,
                        verification_status=SourceVerificationStatus.UNVERIFIED,
                        retrieved_at=retrieved_at,
                        as_of_date=as_of_date,
                        data_payload=sanitize_payload(payload),
                        confidence_score=0.4,
                        provenance_note=STATUTORY_MOCK_BANNER,
                        error_message="Ambiguous name match; unverified identity",
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
                    "is_recognized": False,
                    "is_ambiguous_match": False,
                    "officer_review_required": False,
                },
                confidence_score=1.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message="No recognition record found in DPIIT registry",
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
                error_message=f"DPIIT adapter error: {str(e)}",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
