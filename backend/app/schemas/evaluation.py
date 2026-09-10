from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field


class ComplianceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class DeterministicRuleResult(BaseModel):
    rule_type: str
    parameter: Optional[str] = None
    required_value: Optional[Union[float, int, str, bool]] = None
    actual_value: Optional[Union[float, int, str, bool]] = None
    unit: Optional[str] = None
    passed: Optional[bool] = None
    margin: Optional[float] = None
    message: str


class ParameterClaim(BaseModel):
    parameter: str
    value: Optional[Union[float, int, str, bool]] = None
    unit: Optional[str] = None
    document: Optional[str] = None
    page: int = 1
    chunk_id: Optional[str] = None
    quote: str = ""


class AIEvidenceInterpretation(BaseModel):
    parameter: Optional[str] = None
    finding: str
    extracted_value: Optional[Union[float, int, str, bool]] = None
    extracted_unit: Optional[str] = None
    supporting_quote: str = ""
    evidence_page: int = 1
    evidence_chunk_id: Optional[str] = None
    parameter_claims: List[ParameterClaim] = Field(default_factory=list)
    contradiction_detected: bool = False
    contradiction_details: Optional[str] = None
    is_ambiguous_or_missing: bool = False
    confidence: float = 1.0


class ClauseComplianceEvaluation(BaseModel):
    clause_code: str
    clause_title: str
    bidder_id: UUID
    status: ComplianceStatus
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    claimed_value: Optional[str] = None
    reasoning: str
    evidence_snippet: Optional[str] = None
    evidence_page_number: Optional[int] = None
    evidence_chunk_id: Optional[str] = None
    rule_result: Optional[DeterministicRuleResult] = None
    contradiction_detected: bool = False
    contradiction_details: Optional[str] = None
    requires_human_confirmation: bool = False
    extraction_method: Optional[str] = "DIGITAL_TEXT"
    ocr_confidence: Optional[float] = None


class BidderComplianceReport(BaseModel):
    bidder_id: UUID
    tender_id: Optional[UUID] = None
    total_clauses: int
    pass_count: int
    fail_count: int
    review_count: int
    evaluations: List[ClauseComplianceEvaluation]
    officer_recommendation: str


class EvaluationCellSummary(BaseModel):
    evaluation_id: UUID
    bidder_id: UUID
    clause_id: UUID
    clause_code: str
    status: ComplianceStatus  # Effective status (override if present, else automated)
    original_status: ComplianceStatus  # Automated engine status
    confidence_score: Optional[float] = None
    claimed_value: Optional[str] = None
    reasoning: Optional[str] = None
    contradiction_detected: bool = False
    evidence_page_number: Optional[int] = None
    evidence_chunk_id: Optional[str] = None
    document_name: Optional[str] = None
    override_status: Optional[ComplianceStatus] = None
    override_reason: Optional[str] = None
    extraction_method: Optional[str] = "DIGITAL_TEXT"
    ocr_confidence: Optional[float] = None


class ClauseSummary(BaseModel):
    id: UUID
    clause_code: str
    category: str
    title: str
    is_mandatory: bool
    rule_type: Optional[str] = None


class BidderSummary(BaseModel):
    id: UUID
    company_name: str
    pass_count: int = 0
    fail_count: int = 0
    review_count: int = 0
    final_status: str = "UNDER_REVIEW"
    officer_recommendation: Optional[str] = None


class ComplianceMatrixResponse(BaseModel):
    tender_id: UUID
    tender_title: str
    bidders: List[BidderSummary]
    clauses: List[ClauseSummary]
    matrix: Dict[str, Dict[str, EvaluationCellSummary]]  # str(bidder_id) -> {clause_code: EvaluationCellSummary}
    summary: Dict[str, Any]


class EvaluationDetailResponse(BaseModel):
    id: UUID
    tender_id: UUID
    bidder_id: UUID
    bidder_name: str
    clause_id: UUID
    clause_code: str
    clause_title: str
    clause_category: str
    clause_source_text: str
    clause_page_number: int
    is_mandatory: bool
    status: ComplianceStatus  # Effective status
    original_status: ComplianceStatus  # Automated engine status
    confidence_score: Optional[float] = None
    claimed_value: Optional[str] = None
    reasoning: Optional[str] = None
    evidence_snippet: Optional[str] = None
    evidence_page_number: Optional[int] = None
    evidence_chunk_id: Optional[str] = None
    document_name: Optional[str] = None
    rule_result: Optional[Dict[str, Any]] = None
    contradiction_detected: bool = False
    contradiction_details: Optional[str] = None
    override_status: Optional[ComplianceStatus] = None
    override_reason: Optional[str] = None
    extraction_method: Optional[str] = "DIGITAL_TEXT"
    ocr_confidence: Optional[float] = None


class OfficerOverrideRequest(BaseModel):
    override_status: ComplianceStatus
    override_reason: str = Field(..., min_length=3, description="Mandatory non-empty officer justification")
    officer_id: Optional[str] = None


class EvaluationRunRequest(BaseModel):
    use_live_llm: bool = False
    bidder_ids: Optional[List[UUID]] = None


class EvaluationRunResponse(BaseModel):
    tender_id: UUID
    bidders_evaluated: int
    total_evaluations: int
    reports: List[BidderComplianceReport]

