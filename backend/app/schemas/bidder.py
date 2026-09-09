from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class BidderDocumentType(str, Enum):
    TECHNICAL_PROPOSAL = "TECHNICAL_PROPOSAL"
    FINANCIAL_AUDIT = "FINANCIAL_AUDIT"
    OEM_WARRANTY = "OEM_WARRANTY"
    MII_DECLARATION = "MII_DECLARATION"
    PAST_EXPERIENCE = "PAST_EXPERIENCE"
    EMD_PROOF = "EMD_PROOF"
    GENERAL = "GENERAL"


class DocumentExtractionStatus(str, Enum):
    PENDING = "PENDING"
    EXTRACTED = "EXTRACTED"
    EMPTY_SCANNED = "EMPTY_SCANNED"
    FAILED = "FAILED"


class IngestedPageData(BaseModel):
    page_number: int
    text: str
    word_count: int
    char_count: int
    is_empty_or_scanned: bool = False


class IngestedDocumentResult(BaseModel):
    document_id: UUID
    bidder_id: UUID
    filename: str
    doc_type: Optional[str] = None
    total_pages: int
    empty_pages_count: int = 0
    pages: List[IngestedPageData] = []
    extraction_status: DocumentExtractionStatus = DocumentExtractionStatus.EXTRACTED
    error_message: Optional[str] = None


class DocumentChunkItem(BaseModel):
    chunk_id: str
    bidder_id: UUID
    document_id: UUID
    filename: str
    page_number: int
    chunk_index: int
    chunk_text: str
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    embedding: Optional[List[float]] = None


class EvidenceRetrievalQuery(BaseModel):
    bidder_id: UUID
    clause_code: str
    clause_title: str
    query_text: str
    top_k: int = 3


class RetrievedEvidenceChunk(BaseModel):
    chunk_id: str
    bidder_id: UUID
    document_id: UUID
    filename: str
    page_number: int
    chunk_index: int
    chunk_text: str
    similarity_score: float
    start_char: Optional[int] = None
    end_char: Optional[int] = None


class ClauseEvidenceResponse(BaseModel):
    clause_code: str
    clause_title: str
    bidder_id: UUID
    query_text: str
    top_evidence: List[RetrievedEvidenceChunk] = []


class BidderCreate(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=300)
    tender_id: UUID


class BidderResponse(BaseModel):
    id: UUID
    tender_id: UUID
    company_name: str
    final_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BidderDocumentResponse(BaseModel):
    id: UUID
    bidder_id: UUID
    file_name: str
    doc_type: Optional[str] = None
    total_pages: int
    empty_pages_count: int
    extraction_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class BidderDetailResponse(BaseModel):
    id: UUID
    tender_id: UUID
    company_name: str
    final_status: str
    documents_count: int
    chunks_count: int
    evaluations_count: int = 0
    documents: List[BidderDocumentResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DemoBiddersLoadResponse(BaseModel):
    tender_id: UUID
    message: str
    bidders_count: int
    bidders: List[BidderDetailResponse]

