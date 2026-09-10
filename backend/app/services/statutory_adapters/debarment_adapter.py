"""
app.services.statutory_adapters.debarment_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Statutory adapter for Debarment / Blacklisting Central Registry verification.
Performs time-aware debarment evaluation against an as_of_date with strict
adherence to authoritative identity hierarchy and temporal status semantics.

LOCKED REQUIREMENTS:
1. Temporal semantics:
   - ACTIVE_ON_DATE      -> SUCCESS + VERIFIED   + is_debarred_on_date=True
   - EXPIRED_BEFORE_DATE -> SUCCESS + EXPIRED    + is_debarred_on_date=False
   - STARTS_AFTER_DATE   -> SUCCESS + UNVERIFIED + is_debarred_on_date=False
   - UNKNOWN_PERIOD      -> SUCCESS + UNVERIFIED + is_debarred_on_date=False
   - No matching entity  -> SUCCESS + NOT_FOUND  + is_debarred_on_date=False

2. Identity hierarchy:
   PAN > CIN > GSTIN > Udyam > entity_identifier
   Company-name matching is ONLY a supporting candidate signal.
   Name-only match:
   - SUCCESS + UNVERIFIED
   - is_ambiguous_match = True
   - officer_review_required = True
   - is_debarred_on_date = False
   NEVER establish confirmed debarment from company name alone.
"""

import re
import time
import uuid
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.schemas.statutory_verification import (
    StatutoryAuthority,
    DebarmentTemporalStatus,
    SourceMode,
    SourceConnectionStatus,
    SourceVerificationStatus,
    SourceVerificationResult,
    STATUTORY_MOCK_BANNER,
)
from app.models.mock_sources import MockDebarmentRecord
from app.services.statutory_adapters.base import BaseSourceAdapter, sanitize_payload
from app.services.debarment_temporal_service import DebarmentTemporalService

# Regex patterns for canonical Indian identification tokens
PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
CIN_REGEX = re.compile(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$")
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")


class DebarmentSourceAdapter(BaseSourceAdapter):
    """Statutory adapter for time-aware debarment verification."""

    @property
    def authority(self) -> StatutoryAuthority:
        return StatutoryAuthority.DEBARMENT

    @property
    def source_name(self) -> str:
        return "Debarment / Blacklisting Central Registry"

    def get_supported_identifier_types(self) -> List[str]:
        return [
            "pan",
            "cin",
            "gstin",
            "udyam_number",
            "udyam_registration_number",
            "entity_identifier",
            "firm_name",
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

        clean_id = (str(query_identifier).strip() if query_identifier else "")

        # Extract extra identifier candidates from kwargs
        extra_pan = kwargs.get("pan") or kwargs.get("PAN")
        extra_cin = kwargs.get("cin") or kwargs.get("CIN")
        extra_gstin = kwargs.get("gstin") or kwargs.get("GSTIN") or kwargs.get("gstn")
        extra_udyam = kwargs.get("udyam") or kwargs.get("udyam_number") or kwargs.get("udyam_registration_number")
        extra_entity_id = kwargs.get("entity_identifier") or kwargs.get("bidder_id")
        extra_name = kwargs.get("company_name") or kwargs.get("firm_name") or kwargs.get("legal_name")

        if not clean_id and not any([extra_pan, extra_cin, extra_gstin, extra_udyam, extra_entity_id, extra_name]):
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
                    "is_debarred_on_date": False,
                    "temporal_status": None,
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
                error_message="Database session unavailable for Debarment query",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        try:
            # 1. Authoritative Identity Resolution
            # Hierarchy: PAN > CIN > GSTIN > Udyam > entity_identifier
            matched_record: Optional[MockDebarmentRecord] = None
            matched_by: Optional[str] = None

            # Resolve query_identifier type if 'auto'
            pan_val = extra_pan or (clean_id if (identifier_type == "pan" or PAN_REGEX.match(clean_id.upper())) else None)
            cin_val = extra_cin or (clean_id if (identifier_type == "cin" or CIN_REGEX.match(clean_id.upper())) else None)
            gstin_val = extra_gstin or (clean_id if (identifier_type == "gstin" or GSTIN_REGEX.match(clean_id.upper())) else None)
            udyam_val = extra_udyam or (clean_id if (identifier_type in ("udyam", "udyam_number", "udyam_registration_number") or clean_id.upper().startswith("UDYAM-")) else None)
            entity_val = extra_entity_id or (clean_id if identifier_type == "entity_identifier" else None)

            # If auto and none matched above regex, treat clean_id as candidate entity_identifier or name
            if identifier_type == "auto" and not any([pan_val, cin_val, gstin_val, udyam_val]):
                if clean_id.upper().startswith("DEMO-") or clean_id.upper().startswith("ENT-DEB-") or clean_id.upper().startswith("BIDDER-"):
                    entity_val = clean_id

            # Priority 1: PAN match
            if pan_val and not matched_record:
                res = await db.execute(select(MockDebarmentRecord).where(MockDebarmentRecord.pan == pan_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "PAN"

            # Priority 2: CIN match
            if cin_val and not matched_record:
                res = await db.execute(select(MockDebarmentRecord).where(MockDebarmentRecord.cin == cin_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "CIN"

            # Priority 3: GSTIN match
            if gstin_val and not matched_record:
                res = await db.execute(select(MockDebarmentRecord).where(MockDebarmentRecord.gstin == gstin_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "GSTIN"

            # Priority 4: Udyam match
            if udyam_val and not matched_record:
                res = await db.execute(select(MockDebarmentRecord).where(MockDebarmentRecord.udyam_registration_number == udyam_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "UDYAM"

            # Priority 5: Entity Identifier match
            if entity_val and not matched_record:
                res = await db.execute(select(MockDebarmentRecord).where(MockDebarmentRecord.entity_identifier == entity_val.strip()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "ENTITY_IDENTIFIER"

            # Authoritative Match Found: evaluate temporal status
            if matched_record:
                temp_eval = DebarmentTemporalService.evaluate(
                    as_of=as_of_date,
                    start=matched_record.start_date,
                    end=matched_record.end_date,
                    status=matched_record.status,
                )

                # Locked temporal semantics:
                # ACTIVE_ON_DATE      -> SUCCESS + VERIFIED   + is_debarred_on_date=True
                # EXPIRED_BEFORE_DATE -> SUCCESS + EXPIRED    + is_debarred_on_date=False
                # STARTS_AFTER_DATE   -> SUCCESS + UNVERIFIED + is_debarred_on_date=False
                # UNKNOWN_PERIOD      -> SUCCESS + UNVERIFIED + is_debarred_on_date=False
                if temp_eval.temporal_status == DebarmentTemporalStatus.ACTIVE_ON_DATE:
                    ver_status = SourceVerificationStatus.VERIFIED
                elif temp_eval.temporal_status == DebarmentTemporalStatus.EXPIRED_BEFORE_DATE:
                    ver_status = SourceVerificationStatus.EXPIRED
                else:
                    ver_status = SourceVerificationStatus.UNVERIFIED

                payload = {
                    "is_debarred_on_date": temp_eval.is_debarred_on_date,
                    "temporal_status": temp_eval.temporal_status.value,
                    "is_ambiguous_match": False,
                    "officer_review_required": temp_eval.is_debarred_on_date,
                    "order_number": matched_record.order_number,
                    "authority_name": matched_record.authority_name,
                    "reason": matched_record.reason,
                    "start_date": matched_record.start_date,
                    "end_date": matched_record.end_date,
                    "status": matched_record.status,
                    "matched_by": matched_by,
                    "firm_name": matched_record.firm_name,
                    "temporal_reason": temp_eval.reason,
                }

                return SourceVerificationResult(
                    verification_id=v_id,
                    authority=self.authority,
                    source_name=self.source_name,
                    query_identifier=clean_id or (matched_record.entity_identifier or ""),
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

            # 2. Supporting Candidate Signal: Company-name matching ONLY
            name_candidate = extra_name or clean_id
            if name_candidate and len(name_candidate.strip()) >= 3:
                clean_name = name_candidate.strip()
                res = await db.execute(
                    select(MockDebarmentRecord).where(
                        MockDebarmentRecord.firm_name.ilike(f"%{clean_name}%")
                    )
                )
                name_rec = res.scalars().first()
                if name_rec:
                    # LOCKED REQUIREMENT:
                    # Name-only match:
                    # -> UNVERIFIED
                    # -> is_ambiguous_match=True
                    # -> officer_review_required=True
                    # -> is_debarred_on_date=False
                    # NEVER establish confirmed debarment from company name alone.
                    payload = {
                        "is_debarred_on_date": False,
                        "temporal_status": None,
                        "is_ambiguous_match": True,
                        "officer_review_required": True,
                        "candidate_order_number": name_rec.order_number,
                        "candidate_authority": name_rec.authority_name,
                        "candidate_firm_name": name_rec.firm_name,
                        "candidate_reason": name_rec.reason,
                        "start_date": name_rec.start_date,
                        "end_date": name_rec.end_date,
                        "matched_by": "COMPANY_NAME_ONLY",
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
                        error_message=(
                            f"Company name similarity detected with '{name_rec.firm_name}'. "
                            "Authoritative identifier (PAN/CIN/GSTIN/Udyam) was not verified. "
                            "Procurement officer review required. Debarment NOT confirmed."
                        ),
                        execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                    )

            # 3. No matching entity found
            # Locked semantics:
            # -> SUCCESS + NOT_FOUND + is_debarred_on_date=False
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
                    "is_debarred_on_date": False,
                    "temporal_status": None,
                    "is_ambiguous_match": False,
                    "officer_review_required": False,
                },
                confidence_score=1.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message=f"No debarment record found in registry for query '{clean_id}'",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        except Exception as exc:
            # Source failure isolation: must return SUCCESS or ERROR on adapter level without breaking orchestrator
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
                error_message=f"Debarment verification query error: {str(exc)}",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
