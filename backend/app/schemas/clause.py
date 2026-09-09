from enum import Enum
from typing import Optional, Dict, Any, List, Union
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator


class ClauseCategory(str, Enum):
    TECHNICAL = "TECHNICAL"
    FINANCIAL = "FINANCIAL"
    STATUTORY = "STATUTORY"
    EXPERIENCE = "EXPERIENCE"
    DELIVERY_SLA = "DELIVERY_SLA"


class MandatoryStatus(str, Enum):
    MANDATORY = "MANDATORY"
    OPTIONAL = "OPTIONAL"
    UNCLEAR = "UNCLEAR"


class RuleType(str, Enum):
    NUMERIC_MIN = "NUMERIC_MIN"
    NUMERIC_MAX = "NUMERIC_MAX"
    BOOLEAN_CERT = "BOOLEAN_CERT"
    PERCENT_MIN = "PERCENT_MIN"
    DOCUMENT_REQUIRED = "DOCUMENT_REQUIRED"
    CUSTOM = "CUSTOM"


class DraftRuleConfig(BaseModel):
    """Machine-evaluable draft rule with bounded rule types."""
    type: RuleType = RuleType.CUSTOM
    parameter: Optional[str] = None
    value: Optional[Any] = None
    unit: Optional[str] = None
    status: str = "DRAFT"
    requires_human_review: bool = True

    @field_validator("type", mode="before")
    @classmethod
    def validate_rule_type(cls, val: Any) -> RuleType:
        if isinstance(val, RuleType):
            return val
        if isinstance(val, str):
            clean = val.strip().upper()
            try:
                return RuleType(clean)
            except ValueError:
                return RuleType.CUSTOM
        return RuleType.CUSTOM


class ExtractedClauseItem(BaseModel):
    """Strict schema for validating raw clauses extracted by the LLM."""
    category: ClauseCategory = Field(
        ...,
        description="Category: TECHNICAL, FINANCIAL, STATUTORY, EXPERIENCE, or DELIVERY_SLA"
    )
    title: str = Field(..., min_length=3, max_length=300, description="Concise requirement title")
    description: str = Field(..., min_length=5, description="Full details of the specification")
    mandatory_status: MandatoryStatus = Field(
        default=MandatoryStatus.MANDATORY,
        description="Explicitly classified mandatory status: MANDATORY, OPTIONAL, or UNCLEAR"
    )
    is_mandatory: bool = Field(
        default=True,
        description="Boolean qualification flag (MANDATORY and UNCLEAR default to True for strictness)"
    )
    rule_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Draft machine-evaluable rule configuration"
    )
    source_text: str = Field(
        ...,
        min_length=5,
        description="Verbatim sentence or phrase from the tender PDF"
    )
    page_number: int = Field(
        ...,
        ge=1,
        description="Exact 1-indexed page number where source_text appears"
    )

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, val: Any) -> str:
        """Coerce LLM variations or aliases to canonical ClauseCategory."""
        if not isinstance(val, str):
            return ClauseCategory.TECHNICAL.value
        clean = val.strip().upper()
        if "STAT" in clean:
            return ClauseCategory.STATUTORY.value
        elif "FIN" in clean or "COMMERCIAL" in clean or "TURNOVER" in clean:
            return ClauseCategory.FINANCIAL.value
        elif "EXP" in clean or "PAST" in clean or "ELIGIBILITY" in clean:
            return ClauseCategory.EXPERIENCE.value
        elif "DEL" in clean or "SLA" in clean or "PENALTY" in clean:
            return ClauseCategory.DELIVERY_SLA.value
        return ClauseCategory.TECHNICAL.value

    @field_validator("mandatory_status", mode="before")
    @classmethod
    def normalize_mandatory_status(cls, val: Any) -> str:
        if isinstance(val, str):
            clean = val.strip().upper()
            if "UNCLEAR" in clean or "AMBIGUOUS" in clean or "UNKNOWN" in clean:
                return MandatoryStatus.UNCLEAR.value
            elif "OPT" in clean or "PREF" in clean or "DESIR" in clean:
                return MandatoryStatus.OPTIONAL.value
            return MandatoryStatus.MANDATORY.value
        return MandatoryStatus.MANDATORY.value

    @model_validator(mode="after")
    def compute_is_mandatory_and_rule_config(self) -> "ExtractedClauseItem":
        # Handle mandatory status mapping
        if self.mandatory_status == MandatoryStatus.OPTIONAL:
            self.is_mandatory = False
        else:
            self.is_mandatory = True

        # Validate rule_config structure if provided
        if self.rule_config and isinstance(self.rule_config, dict):
            try:
                draft_rule = DraftRuleConfig.model_validate(self.rule_config)
                # If mandatory status was unclear, flag rule as requiring human review
                if self.mandatory_status == MandatoryStatus.UNCLEAR:
                    draft_rule.requires_human_review = True
                self.rule_config = draft_rule.model_dump()
            except Exception:
                self.rule_config = {
                    "type": RuleType.CUSTOM.value,
                    "raw": str(self.rule_config),
                    "status": "DRAFT",
                    "requires_human_review": True
                }
        return self


class LLMExtractionBatch(BaseModel):
    """Top-level batch format expected from NVIDIA NIM LLM."""
    clauses: List[ExtractedClauseItem] = Field(default_factory=list)


class ExtractedRawClause(BaseModel):
    """Internal representation after provenance verification and deduplication."""
    category: str
    title: str
    description: str
    is_mandatory: bool = True
    mandatory_status: str = "MANDATORY"
    rule_config: Optional[Dict[str, Any]] = None
    source_text: str
    page_number: int


# API Request / Response schemas preserved for endpoint compatibility
class ClauseBase(BaseModel):
    category: str = Field(..., description="TECHNICAL, FINANCIAL, STATUTORY, EXPERIENCE, or DELIVERY_SLA")
    title: str = Field(..., min_length=3, max_length=300)
    description: str = Field(..., min_length=5)
    is_mandatory: bool = True
    rule_config: Optional[Dict[str, Any]] = Field(None, description="Draft rule configuration")
    source_text: str = Field(..., description="Verbatim quote from tender PDF")
    page_number: int = Field(..., ge=1, description="Page number where clause was extracted")


class ClauseCreateRequest(BaseModel):
    category: str
    title: str
    description: str
    is_mandatory: bool = True
    rule_config: Optional[Dict[str, Any]] = None
    source_text: str
    page_number: int = 1


class ClauseUpdateRequest(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    is_mandatory: Optional[bool] = None
    rule_config: Optional[Dict[str, Any]] = None
    source_text: Optional[str] = None
    page_number: Optional[int] = None
    is_confirmed: Optional[bool] = None


class ClauseResponse(BaseModel):
    id: UUID
    tender_id: UUID
    clause_code: str
    category: str
    title: str
    description: str
    is_mandatory: bool
    rule_config: Optional[Dict[str, Any]] = None
    source_text: str
    page_number: int
    is_confirmed: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
