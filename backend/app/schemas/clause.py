from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


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


class ExtractedRawClause(BaseModel):
    """Raw clause extracted by NVIDIA LLM before deduplication & coding."""
    category: str
    title: str
    description: str
    is_mandatory: bool = True
    rule_config: Optional[Dict[str, Any]] = None
    source_text: str
    page_number: int
