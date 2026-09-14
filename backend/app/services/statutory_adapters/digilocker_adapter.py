"""
app.services.statutory_adapters.digilocker_adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Statutory Source Adapter for DigiLocker Document Verification & Provenance.
Models an authenticated/requester-style verification workflow using deterministic MOCK records.

Rules:
- DigiLocker is NOT a public company directory and CANNOT be queried by company name alone.
- Supports document lookup by document reference / URI, document ID, subject PAN/CIN, or entity_identifier.
- Cross-validates located document subject against authoritative bidder identity (PAN > CIN > GSTIN > Udyam).
- Conflicting strong identity produces UNVERIFIED + officer review required.
- Explicitly models document provenance:
    signature_status: VALID, INVALID, NOT_VERIFIED
    document_status: ACTIVE, EXPIRED, REVOKED
    verification_result: VERIFIED, NOT_FOUND, UNVERIFIED, FAILED
- Transport failure (AUTH_FAILURE, TIMEOUT) is strictly isolated and NEVER produces bidder FAIL.
- No actual documents, no citizen PII, no Aadhaar, no OAuth secrets stored.
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
from app.models.mock_sources import MockDigiLockerRecord
from app.services.statutory_adapters.base import (
    BaseSourceAdapter,
    sanitize_payload,
    validate_bidder_identity_consistency,
)

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$", re.IGNORECASE)
CIN_REGEX = re.compile(r"^[UL][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$", re.IGNORECASE)
DOC_URI_REGEX = re.compile(r"^(in\.gov\.|uri:|doc:)[a-z0-9_.-]+", re.IGNORECASE)


class DigiLockerSourceAdapter(BaseSourceAdapter):
    """Statutory adapter for DigiLocker document provenance & verification."""

    @property
    def authority(self) -> StatutoryAuthority:
        return StatutoryAuthority.DIGILOCKER

    @property
    def source_name(self) -> str:
        return "DigiLocker Document Verification"

    def get_supported_identifier_types(self) -> List[str]:
        return [
            "document_reference",
            "document_uri",
            "doc_ref",
            "document_id",
            "doc_id",
            "pan",
            "cin",
            "entity_identifier",
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

        # Simulated Gateway Failure Hooks (for demonstration & contract testing)
        upper_id = clean_id.upper()
        if "SIM_AUTH_FAILURE" in upper_id or "AUTH-FAIL" in upper_id or "AUTH_FAIL" in upper_id:
            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=clean_id,
                identifier_type=identifier_type,
                mode=mode,
                connection_status=SourceConnectionStatus.AUTH_FAILURE,
                verification_status=SourceVerificationStatus.FAILED,
                retrieved_at=retrieved_at,
                as_of_date=as_of_date,
                data_payload={
                    "is_verified": False,
                    "is_ambiguous_match": False,
                    "officer_review_required": True,
                    "simulated_error": "AUTH_FAILURE",
                    "source": "DIGILOCKER_SIMULATOR",
                    "is_mock": True,
                },
                confidence_score=0.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message="Authentication failure communicating with DigiLocker verification gateway (simulated)",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        if "SIM_TIMEOUT" in upper_id or "SIM-TIMEOUT" in upper_id or "DEMO-TIMEOUT" in upper_id:
            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=clean_id,
                identifier_type=identifier_type,
                mode=mode,
                connection_status=SourceConnectionStatus.TIMEOUT,
                verification_status=SourceVerificationStatus.FAILED,
                retrieved_at=retrieved_at,
                as_of_date=as_of_date,
                data_payload={
                    "is_verified": False,
                    "is_ambiguous_match": False,
                    "officer_review_required": True,
                    "simulated_error": "TIMEOUT",
                    "source": "DIGILOCKER_SIMULATOR",
                    "is_mock": True,
                },
                confidence_score=0.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message="DigiLocker verification gateway request timed out (simulated)",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        # Extract extra identifier candidates from kwargs
        extra_pan = kwargs.get("pan") or kwargs.get("PAN")
        extra_cin = kwargs.get("cin") or kwargs.get("CIN")
        extra_gstin = kwargs.get("gstin") or kwargs.get("GSTIN") or kwargs.get("gstn")
        extra_doc_ref = (
            kwargs.get("document_reference")
            or kwargs.get("document_uri")
            or kwargs.get("doc_ref")
            or kwargs.get("document_id")
            or kwargs.get("doc_id")
        )
        extra_entity_id = kwargs.get("entity_identifier")
        extra_name = kwargs.get("company_name") or kwargs.get("firm_name") or kwargs.get("entity_name")

        # DigiLocker requires specific document reference or subject identifier
        has_authoritative_key = bool(extra_doc_ref or extra_pan or extra_cin or extra_entity_id or clean_id)
        is_only_name = bool(extra_name and not clean_id and not extra_doc_ref and not extra_pan and not extra_cin and not extra_entity_id)

        if is_only_name or (identifier_type == "company_name" and not extra_doc_ref and not extra_pan and not extra_cin):
            # DigiLocker is NOT a public company directory!
            return SourceVerificationResult(
                verification_id=v_id,
                authority=self.authority,
                source_name=self.source_name,
                query_identifier=clean_id or extra_name or "",
                identifier_type=identifier_type,
                mode=mode,
                connection_status=SourceConnectionStatus.SUCCESS,
                verification_status=SourceVerificationStatus.UNVERIFIED,
                retrieved_at=retrieved_at,
                as_of_date=as_of_date,
                data_payload={
                    "is_verified": False,
                    "is_ambiguous_match": True,
                    "officer_review_required": True,
                    "conflict_detected": False,
                    "source": "DIGILOCKER_SIMULATOR",
                    "is_mock": True,
                },
                confidence_score=0.4,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message="DigiLocker is an authenticated document repository and cannot be queried by company name alone. Document reference or subject PAN/CIN required.",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        if not clean_id and not any([extra_doc_ref, extra_pan, extra_cin, extra_entity_id]):
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
                    "is_verified": False,
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
                error_message="Database session unavailable for DigiLocker query",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        try:
            # 1. Document / Subject Identity Resolution
            # Source lookup order: Document Reference > PAN > CIN > Entity Identifier
            matched_record: Optional[MockDigiLockerRecord] = None
            matched_by: Optional[str] = None

            doc_ref_val = extra_doc_ref or (
                clean_id if (
                    identifier_type in ("document_reference", "document_uri", "doc_ref", "document_id", "doc_id")
                    or DOC_URI_REGEX.match(clean_id)
                    or clean_id.startswith("DL-")
                ) else None
            )
            pan_val = extra_pan or (clean_id if (identifier_type == "pan" or PAN_REGEX.match(clean_id.upper())) else None)
            cin_val = extra_cin or (clean_id if (identifier_type == "cin" or CIN_REGEX.match(clean_id.upper())) else None)
            entity_val = extra_entity_id or (clean_id if identifier_type == "entity_identifier" else None)

            # In auto mode, detect DEMO- or BIDDER- IDs as entity_identifier
            if identifier_type == "auto" and not any([doc_ref_val, pan_val, cin_val]):
                if clean_id.upper().startswith("DEMO-") or clean_id.upper().startswith("BIDDER-") or clean_id.upper().startswith("ENT-"):
                    entity_val = clean_id

            # Priority 1: Document Reference / URI
            if doc_ref_val and not matched_record:
                res = await db.execute(
                    select(MockDigiLockerRecord).where(
                        MockDigiLockerRecord.document_reference == doc_ref_val.strip()
                    )
                )
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "DOCUMENT_REFERENCE"

            # Priority 2: Subject PAN
            if pan_val and not matched_record:
                res = await db.execute(
                    select(MockDigiLockerRecord).where(
                        MockDigiLockerRecord.subject_pan == pan_val.strip().upper()
                    )
                )
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "SUBJECT_PAN"

            # Priority 3: Subject CIN
            if cin_val and not matched_record:
                res = await db.execute(
                    select(MockDigiLockerRecord).where(
                        MockDigiLockerRecord.subject_cin == cin_val.strip().upper()
                    )
                )
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "SUBJECT_CIN"

            # Priority 4: Entity Identifier
            if entity_val and not matched_record:
                res = await db.execute(
                    select(MockDigiLockerRecord).where(
                        MockDigiLockerRecord.entity_identifier == entity_val.strip()
                    )
                )
                rec = res.scalars().first()
                if rec:
                    matched_record = rec
                    matched_by = "ENTITY_IDENTIFIER"

            # Document Match Found
            if matched_record:
                # Cross-validate subject identity against authoritative bidder identity (PAN > CIN > GSTIN > Udyam)
                is_consistent, conflict_reason = validate_bidder_identity_consistency(
                    record_pan=matched_record.subject_pan,
                    record_cin=matched_record.subject_cin,
                    query_pan=pan_val,
                    query_cin=cin_val,
                    query_gstin=extra_gstin,
                )

                if not is_consistent:
                    # Return UNVERIFIED with conflict detected and officer review required
                    data = {
                        "is_verified": False,
                        "is_ambiguous_match": True,
                        "officer_review_required": True,
                        "conflict_detected": True,
                        "conflict_reason": conflict_reason,
                        "matched_by": matched_by,
                        "queried_document_reference": doc_ref_val,
                        "record_subject_pan": matched_record.subject_pan,
                        "record_subject_cin": matched_record.subject_cin,
                        "record_document_reference": matched_record.document_reference,
                        "source": "DIGILOCKER_SIMULATOR",
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

                # Evaluate Document Authenticity & Provenance
                sig_status = str(matched_record.signature_status).upper()
                doc_status = str(matched_record.document_status).upper()
                prov_result = str(matched_record.verification_result).upper()

                if sig_status == "INVALID" or prov_result == "FAILED":
                    v_status = SourceVerificationStatus.FAILED
                    err_msg = "Digital signature is INVALID or document tamper check failed"
                    is_ver = False
                elif doc_status == "REVOKED":
                    v_status = SourceVerificationStatus.INACTIVE
                    err_msg = "Document has been REVOKED by the issuing authority"
                    is_ver = False
                elif doc_status == "EXPIRED":
                    v_status = SourceVerificationStatus.EXPIRED
                    err_msg = "Document validity period has EXPIRED"
                    is_ver = False
                elif sig_status == "NOT_VERIFIED" or prov_result == "UNVERIFIED":
                    v_status = SourceVerificationStatus.UNVERIFIED
                    err_msg = "Document signature status is NOT_VERIFIED"
                    is_ver = False
                elif sig_status == "VALID" and prov_result == "VERIFIED" and doc_status == "ACTIVE":
                    v_status = SourceVerificationStatus.VERIFIED
                    err_msg = None
                    is_ver = True
                else:
                    v_status = SourceVerificationStatus.UNVERIFIED
                    err_msg = f"Document status {doc_status} with signature status {sig_status}"
                    is_ver = False

                data = {
                    "document_reference": matched_record.document_reference,
                    "document_type": matched_record.document_type,
                    "issuer": matched_record.issuer,
                    "issuer_identifier": matched_record.issuer_identifier,
                    "subject_entity_name": matched_record.subject_entity_name,
                    "subject_pan": matched_record.subject_pan,
                    "subject_cin": matched_record.subject_cin,
                    "issued_at": matched_record.issued_at,
                    "document_status": matched_record.document_status,
                    "signature_status": matched_record.signature_status,
                    "verification_result": matched_record.verification_result,
                    "is_verified": is_ver,
                    "matched_by": matched_by,
                    "is_ambiguous_match": False,
                    "officer_review_required": (v_status != SourceVerificationStatus.VERIFIED),
                    "conflict_detected": False,
                    "source": "DIGILOCKER_SIMULATOR",
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
                    confidence_score=1.0 if v_status == SourceVerificationStatus.VERIFIED else 0.7,
                    provenance_note=STATUTORY_MOCK_BANNER,
                    error_message=err_msg,
                    execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
                )

            # Document Not Found in DigiLocker repository
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
                    "is_verified": False,
                    "is_ambiguous_match": False,
                    "officer_review_required": False,
                    "conflict_detected": False,
                    "queried_identifier": clean_id,
                    "source": "DIGILOCKER_SIMULATOR",
                    "is_mock": True,
                },
                confidence_score=1.0,
                provenance_note=STATUTORY_MOCK_BANNER,
                error_message="Document reference not found in DigiLocker repository",
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
                error_message=f"DigiLocker adapter internal execution error: {str(exc)}",
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )
