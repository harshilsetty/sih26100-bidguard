"""
app.services.statutory_adapters.nsic_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Statutory Source Adapter for NSIC / Single Point Registration Scheme (SPRS).
Canonical Bidder Identity Evidence Priority:
PAN > CIN > GSTIN > Udyam > entity_identifier > company_name (weak)

Rules:
- Source-specific NSIC registration number is a source lookup key.
- After source lookup, cross-validate returned identity using validate_bidder_identity_consistency.
- Conflicting strong identity produces UNVERIFIED + officer review required.
- Name-only matches return UNVERIFIED with officer review required (never VERIFIED on name alone).
- Temporal behavior:
    as_of_date is None -> UNKNOWN_PERIOD / UNVERIFIED (never date.today())
    as_of_date < issue_date -> STARTS_AFTER_DATE / UNVERIFIED
    issue_date <= as_of_date <= expiry_date -> ACTIVE_ON_DATE / VERIFIED (when active)
    as_of_date > expiry_date -> EXPIRED_BEFORE_DATE / EXPIRED
    expiry_date is NULL -> active ONLY if explicitly INDEFINITE or PERMANENT
- All mock records are sanitized and marked with SourceMode.MOCK.
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
from app.models.mock_sources import MockNSICRecord
from app.services.statutory_adapters.base import (
    BaseSourceAdapter,
    sanitize_payload,
    validate_bidder_identity_consistency,
)

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$", re.IGNORECASE)
UDYAM_REGEX = re.compile(r"^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$", re.IGNORECASE)
NSIC_REG_REGEX = re.compile(r"^(NSIC|SPRS|NSIC-SPRS)[-/]?[A-Z0-9]{4,15}$", re.IGNORECASE)


class NSICSourceAdapter(BaseSourceAdapter):
    """Statutory adapter for NSIC / Single Point Registration Scheme verification."""

    @property
    def authority(self) -> StatutoryAuthority:
        return StatutoryAuthority.NSIC

    @property
    def source_name(self) -> str:
        return "NSIC / Single Point Registration Scheme"

    def get_supported_identifier_types(self) -> List[str]:
        return [
            "registration_number",
            "nsic_number",
            "nsic_registration_number",
            "udyam_number",
            "udyam",
            "pan",
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
        extra_gstin = kwargs.get("gstin") or kwargs.get("GSTIN") or kwargs.get("gstn")
        extra_udyam = kwargs.get("udyam_number") or kwargs.get("udyam") or kwargs.get("msme_registration")
        extra_reg = (
            kwargs.get("registration_number")
            or kwargs.get("nsic_number")
            or kwargs.get("nsic_registration_number")
            or kwargs.get("sprs_number")
        )
        extra_entity_id = kwargs.get("entity_identifier")
        extra_name = kwargs.get("company_name") or kwargs.get("firm_name") or kwargs.get("entity_name")

        if not clean_id and not any([extra_pan, extra_udyam, extra_reg, extra_entity_id, extra_name]):
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
                    "is_registered": False,
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
                error_message="Database session unavailable for NSIC query",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        try:
            # 1. Authoritative Identity Resolution
            # Source lookup key order: Registration Number > PAN > Udyam > Entity Identifier
            matched_record: Optional[MockNSICRecord] = None
            matched_by: Optional[str] = None

            reg_val = extra_reg or (
                clean_id if (identifier_type in ("registration_number", "nsic_number", "nsic_registration_number", "sprs_number") or NSIC_REG_REGEX.match(clean_id)) else None
            )
            pan_val = extra_pan or (clean_id if (identifier_type == "pan" or PAN_REGEX.match(clean_id.upper())) else None)
            udyam_val = extra_udyam or (clean_id if (identifier_type in ("udyam", "udyam_number") or UDYAM_REGEX.match(clean_id.upper())) else None)
            entity_val = extra_entity_id or (clean_id if identifier_type == "entity_identifier" else None)

            # In auto mode, detect DEMO- or BIDDER- IDs as entity_identifier
            if identifier_type == "auto" and not any([reg_val, pan_val, udyam_val]):
                if clean_id.upper().startswith("DEMO-") or clean_id.upper().startswith("BIDDER-") or clean_id.upper().startswith("ENT-"):
                    entity_val = clean_id

            # Priority 1: Registration Number (source lookup key)
            if reg_val and not matched_record:
                res = await db.execute(select(MockNSICRecord).where(MockNSICRecord.registration_number == reg_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "REGISTRATION_NUMBER"

            # Priority 2: PAN
            if pan_val and not matched_record:
                res = await db.execute(select(MockNSICRecord).where(MockNSICRecord.pan == pan_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "PAN"

            # Priority 3: Udyam Number
            if udyam_val and not matched_record:
                res = await db.execute(select(MockNSICRecord).where(MockNSICRecord.udyam_number == udyam_val.strip().upper()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "UDYAM_NUMBER"

            # Priority 4: Entity Identifier
            if entity_val and not matched_record:
                res = await db.execute(select(MockNSICRecord).where(MockNSICRecord.entity_identifier == entity_val.strip()))
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "ENTITY_IDENTIFIER"

            # Authoritative Match Found
            if matched_record:
                # Cross-validate located record against authoritative bidder identity (PAN > CIN > GSTIN > Udyam)
                is_consistent, conflict_reason = validate_bidder_identity_consistency(
                    record_pan=matched_record.pan,
                    record_cin=None,
                    query_pan=pan_val,
                    query_cin=extra_cin,
                    query_gstin=extra_gstin,
                    query_udyam=udyam_val,
                    record_udyam=matched_record.udyam_number,
                )

                if not is_consistent:
                    # Return UNVERIFIED with conflict detected and officer review required
                    data = {
                        "is_registered": False,
                        "is_ambiguous_match": True,
                        "officer_review_required": True,
                        "conflict_detected": True,
                        "conflict_reason": conflict_reason,
                        "matched_by": matched_by,
                        "queried_registration_number": reg_val,
                        "record_pan": matched_record.pan,
                        "record_udyam": matched_record.udyam_number,
                        "record_registration_number": matched_record.registration_number,
                        "source": "NSIC_SPRS_SIMULATOR",
                        "is_mock": True,
                    }
                    return SourceVerificationResult(
                        verification_id=v_id,
                        authority=self.authority,
                        source_name=self.source_name,
                        query_identifier=clean_id,
                        identifier_type=identifier_type,
                        mode=mode,
                        connection_status=SourceConnectionStatus.SUCCESS,
                        verification_status=SourceVerificationStatus.UNVERIFIED,
                        retrieved_at=retrieved_at,
                        as_of_date=as_of_date,
                        data_payload=sanitize_payload(data),
                        confidence_score=0.4,
                        provenance_note=STATUTORY_MOCK_BANNER,
                        error_message=conflict_reason,
                        execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                    )

                # Temporal evaluation for NSIC registration validity
                v_status = SourceVerificationStatus.VERIFIED
                temporal_status = "ACTIVE_ON_DATE"
                is_reg_on_date = True
                temporal_details = "NSIC registration verified and active on evaluation date"

                # If as_of_date is None: NEVER use date.today(). Return UNKNOWN_PERIOD / UNVERIFIED
                if as_of_date is None:
                    v_status = SourceVerificationStatus.UNVERIFIED
                    temporal_status = "UNKNOWN_PERIOD"
                    is_reg_on_date = False
                    temporal_details = "No as_of_date provided for temporal registration validity evaluation"
                else:
                    try:
                        iss_date = date.fromisoformat(matched_record.issue_date) if matched_record.issue_date else None
                    except (ValueError, TypeError):
                        iss_date = None

                    try:
                        exp_date = date.fromisoformat(matched_record.expiry_date) if matched_record.expiry_date else None
                    except (ValueError, TypeError):
                        exp_date = None

                    # Check future / not yet valid
                    if iss_date and as_of_date < iss_date:
                        v_status = SourceVerificationStatus.UNVERIFIED
                        temporal_status = "STARTS_AFTER_DATE"
                        is_reg_on_date = False
                        temporal_details = f"Registration starts after as_of_date (issue_date: {iss_date})"
                    # Check expired
                    elif exp_date and as_of_date > exp_date:
                        v_status = SourceVerificationStatus.EXPIRED
                        temporal_status = "EXPIRED_BEFORE_DATE"
                        is_reg_on_date = False
                        temporal_details = f"Registration expired before as_of_date (expiry_date: {exp_date})"
                    # Check open-ended / NULL expiry
                    elif exp_date is None:
                        is_explicit_indefinite = (
                            str(matched_record.status).upper() in ("INDEFINITE", "PERMANENT", "ACTIVE_INDEFINITE")
                            or str(matched_record.registration_status).upper() in ("INDEFINITE", "PERMANENT", "ACTIVE_INDEFINITE")
                        )
                        if not is_explicit_indefinite:
                            # Do NOT assume NULL expiry means active
                            v_status = SourceVerificationStatus.UNVERIFIED
                            temporal_status = "UNKNOWN_PERIOD"
                            is_reg_on_date = False
                            temporal_details = "Registration expiry date is unspecified without explicit indefinite status"
                        else:
                            # Explicitly indefinite and started
                            if matched_record.status.upper() == "ACTIVE":
                                v_status = SourceVerificationStatus.VERIFIED
                                temporal_status = "ACTIVE_ON_DATE"
                                is_reg_on_date = True
                                temporal_details = "Registration is permanent/indefinite and active"
                            else:
                                v_status = SourceVerificationStatus.INACTIVE
                                temporal_status = "INACTIVE"
                                is_reg_on_date = False
                                temporal_details = f"Registration status is {matched_record.status}"
                    else:
                        # issue_date <= as_of_date <= expiry_date
                        if matched_record.status.upper() == "ACTIVE":
                            v_status = SourceVerificationStatus.VERIFIED
                            temporal_status = "ACTIVE_ON_DATE"
                            is_reg_on_date = True
                            temporal_details = "Registration valid and active on date"
                        elif matched_record.status.upper() == "INACTIVE":
                            v_status = SourceVerificationStatus.INACTIVE
                            temporal_status = "INACTIVE"
                            is_reg_on_date = False
                            temporal_details = "Registration status is INACTIVE in registry"
                        elif matched_record.status.upper() == "EXPIRED":
                            v_status = SourceVerificationStatus.EXPIRED
                            temporal_status = "EXPIRED_BEFORE_DATE"
                            is_reg_on_date = False
                            temporal_details = "Registration status is recorded as EXPIRED in registry"
                        else:
                            v_status = SourceVerificationStatus.UNVERIFIED
                            temporal_status = "UNKNOWN"
                            is_reg_on_date = False
                            temporal_details = f"Registration status is {matched_record.status}"

                data = {
                    "registration_number": matched_record.registration_number,
                    "entity_name": matched_record.entity_name,
                    "pan": matched_record.pan,
                    "udyam_number": matched_record.udyam_number,
                    "registration_status": matched_record.registration_status,
                    "status": matched_record.status,
                    "issue_date": matched_record.issue_date,
                    "expiry_date": matched_record.expiry_date,
                    "monetary_limit": matched_record.monetary_limit,
                    "category": matched_record.category,
                    "store_details": matched_record.store_details,
                    "matched_by": matched_by,
                    "is_registered": is_reg_on_date,
                    "temporal_status": temporal_status,
                    "temporal_details": temporal_details,
                    "is_ambiguous_match": False,
                    "officer_review_required": (v_status in (SourceVerificationStatus.UNVERIFIED, SourceVerificationStatus.EXPIRED, SourceVerificationStatus.INACTIVE)),
                    "conflict_detected": False,
                    "source": "NSIC_SPRS_SIMULATOR",
                    "is_mock": True,
                }

                return SourceVerificationResult(
                    verification_id=v_id,
                    authority=self.authority,
                    source_name=self.source_name,
                    query_identifier=clean_id,
                    identifier_type=identifier_type,
                    mode=mode,
                    connection_status=SourceConnectionStatus.SUCCESS,
                    verification_status=v_status,
                    retrieved_at=retrieved_at,
                    as_of_date=as_of_date,
                    data_payload=sanitize_payload(data),
                    confidence_score=1.0 if v_status == SourceVerificationStatus.VERIFIED else 0.8,
                    provenance_note=STATUTORY_MOCK_BANNER,
                    error_message=None if v_status == SourceVerificationStatus.VERIFIED else temporal_details,
                    execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                )

            # Priority 5: Entity Name (Weak Identifier - NEVER authoritative alone)
            name_val = extra_name or clean_id
            if name_val and len(name_val.strip()) >= 3:
                res = await db.execute(
                    select(MockNSICRecord).where(MockNSICRecord.entity_name.ilike(f"%{name_val.strip()}%"))
                )
                ambiguous_rec = res.scalars().first()
                if ambiguous_rec:
                    # Name-only match must NEVER be VERIFIED. Return UNVERIFIED + officer review
                    data = {
                        "is_registered": False,
                        "matched_by": "NAME_ONLY_WEAK_MATCH",
                        "is_ambiguous_match": True,
                        "officer_review_required": True,
                        "candidate_registration_number": ambiguous_rec.registration_number,
                        "candidate_entity_name": ambiguous_rec.entity_name,
                        "candidate_pan": ambiguous_rec.pan,
                        "candidate_status": ambiguous_rec.status,
                        "query_name": name_val,
                        "conflict_detected": False,
                        "source": "NSIC_SPRS_SIMULATOR",
                        "is_mock": True,
                    }
                    return SourceVerificationResult(
                        verification_id=v_id,
                        authority=self.authority,
                        source_name=self.source_name,
                        query_identifier=clean_id,
                        identifier_type=identifier_type,
                        mode=mode,
                        connection_status=SourceConnectionStatus.SUCCESS,
                        verification_status=SourceVerificationStatus.UNVERIFIED,
                        retrieved_at=retrieved_at,
                        as_of_date=as_of_date,
                        data_payload=sanitize_payload(data),
                        confidence_score=0.4,
                        provenance_note=STATUTORY_MOCK_BANNER,
                        error_message="Entity name matched, but company name alone is weak. Authoritative registration code/PAN required.",
                        execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                    )

            # Record Not Found in NSIC Register
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
                    "is_registered": False,
                    "is_ambiguous_match": False,
                    "officer_review_required": False,
                    "conflict_detected": False,
                    "queried_identifier": clean_id,
                    "source": "NSIC_SPRS_SIMULATOR",
                    "is_mock": True,
                },
                confidence_score=1.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message="No matching registration found in NSIC / SPRS register",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        except Exception as exc:
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
                error_message=f"NSIC adapter internal execution error: {str(exc)}",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
