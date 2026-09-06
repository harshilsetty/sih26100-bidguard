from typing import Optional, List, Dict
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.clause import ClauseResponse


class TenderCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=500)
    gem_tender_id: Optional[str] = Field(None, max_length=100)


class TenderResponse(BaseModel):
    id: UUID
    title: str
    gem_tender_id: Optional[str] = None
    file_name: Optional[str] = None
    total_pages: int
    extraction_status: str
    created_at: datetime
    updated_at: datetime
    clause_count: int = 0

    class Config:
        from_attributes = True


class TenderDetailResponse(BaseModel):
    id: UUID
    title: str
    gem_tender_id: Optional[str] = None
    file_name: Optional[str] = None
    total_pages: int
    extraction_status: str
    created_at: datetime
    updated_at: datetime
    clauses: List[ClauseResponse] = []

    class Config:
        from_attributes = True


class ExtractionResultResponse(BaseModel):
    tender_id: UUID
    extraction_status: str
    total_pages: int
    extracted_count: int
    clauses: List[ClauseResponse]
