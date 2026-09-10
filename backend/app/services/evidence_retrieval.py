import math
import re
import logging
from typing import List, Dict, Any, Optional, Union
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.chunk import DocumentChunk
from app.schemas.bidder import (
    DocumentChunkItem,
    RetrievedEvidenceChunk,
    ClauseEvidenceResponse,
    ExtractionMethod,
)
from app.services.embedding_service import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)


def compute_lexical_overlap(query: str, text: str) -> float:
    """Compute keyword overlap between query and chunk text for hybrid retrieval boost."""
    stop_words = {
        "the", "and", "for", "with", "must", "all", "be", "of", "in", "at", "to", "is",
        "a", "an", "as", "by", "that", "this", "or", "from", "on", "are", "under", "per"
    }
    q_tokens = set(w.lower() for w in re.findall(r"\b[a-zA-Z0-9_]{3,}\b", query) if w.lower() not in stop_words)
    if not q_tokens:
        return 0.0
    text_tokens = set(w.lower() for w in re.findall(r"\b[a-zA-Z0-9_]{3,}\b", text))
    overlap = len(q_tokens & text_tokens)
    return overlap / len(q_tokens)


def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector dimension mismatch in similarity: {len(vec_a)} vs {len(vec_b)}")

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


def build_clause_retrieval_query(clause: Union[Dict[str, Any], Any]) -> str:
    """Formulate a comprehensive compliance retrieval query from clause metadata.

    Combines title, description, rule parameters, and exact tender requirement quote.
    """
    if isinstance(clause, dict):
        title = clause.get("title", "")
        desc = clause.get("description", "")
        src = clause.get("source_text", "")
        category = clause.get("category", "")
        rule_cfg = clause.get("rule_config") or {}
    else:
        title = getattr(clause, "title", "")
        desc = getattr(clause, "description", "")
        src = getattr(clause, "source_text", "")
        category = getattr(clause, "category", "")
        rule_cfg = getattr(clause, "rule_config", None) or {}

    rule_details = []
    if isinstance(rule_cfg, dict):
        param = rule_cfg.get("parameter")
        val = rule_cfg.get("value")
        unit = rule_cfg.get("unit")
        if param:
            rule_details.append(f"{param}: {val} {unit or ''}".strip())

    parts = [title]
    if desc and desc != title:
        parts.append(desc)
    if rule_details:
        parts.append(f"Requirement parameters: {', '.join(rule_details)}")
    if src:
        parts.append(f"Tender specification: {src}")

    query = " ".join(parts).strip()
    return query


def retrieve_evidence_from_memory(
    chunks: List[DocumentChunkItem],
    query_vector: List[float],
    bidder_id: UUID,
    top_k: int = settings.DEFAULT_RETRIEVAL_TOP_K,
    document_id: Optional[UUID] = None,
    page_number: Optional[int] = None,
    query_text: Optional[str] = None,
) -> List[RetrievedEvidenceChunk]:
    """Retrieve top-k evidence chunks from in-memory chunk list with strict bidder isolation.

    Guarantees:
    - Only chunks with chunk.bidder_id == bidder_id are ever evaluated or returned.
    - Chunks are ranked by hybrid similarity score (dense cosine + lexical overlap) in descending order.
    """
    candidates: List[DocumentChunkItem] = []

    for c in chunks:
        # Strict Bidder Isolation Filter
        if c.bidder_id != bidder_id:
            continue
        if document_id and c.document_id != document_id:
            continue
        if page_number and c.page_number != page_number:
            continue
        if not c.embedding:
            continue
        candidates.append(c)

    scored: List[RetrievedEvidenceChunk] = []
    for c in candidates:
        sim = compute_cosine_similarity(query_vector, c.embedding)  # type: ignore
        if query_text:
            lex = compute_lexical_overlap(query_text, c.chunk_text)
            final_score = float(sim) + 0.4 * lex
        else:
            final_score = float(sim)
        scored.append(
            RetrievedEvidenceChunk(
                chunk_id=c.chunk_id,
                bidder_id=c.bidder_id,
                document_id=c.document_id,
                filename=c.filename,
                page_number=c.page_number,
                chunk_index=c.chunk_index,
                chunk_text=c.chunk_text,
                similarity_score=round(float(final_score), 4),
                start_char=c.start_char,
                end_char=c.end_char,
                extraction_method=getattr(c, "extraction_method", ExtractionMethod.DIGITAL_TEXT),
                ocr_confidence=getattr(c, "ocr_confidence", None),
            )
        )

    # Rank by similarity score descending
    scored.sort(key=lambda x: x.similarity_score, reverse=True)
    return scored[:top_k]


async def retrieve_evidence_from_db(
    db: AsyncSession,
    query_vector: List[float],
    bidder_id: UUID,
    top_k: int = settings.DEFAULT_RETRIEVAL_TOP_K,
    document_id: Optional[UUID] = None,
    page_number: Optional[int] = None,
) -> List[RetrievedEvidenceChunk]:
    """Retrieve top-k evidence chunks from PostgreSQL + pgvector with strict bidder isolation."""
    # Build query strictly filtered by bidder_id
    query = select(DocumentChunk).where(DocumentChunk.bidder_id == bidder_id)

    if document_id:
        query = query.where(DocumentChunk.bid_document_id == document_id)
    if page_number:
        query = query.where(DocumentChunk.page_number == page_number)

    # Order by cosine distance via pgvector operator <=>
    query = query.order_by(DocumentChunk.embedding.cosine_distance(query_vector)).limit(top_k)

    result = await db.execute(query)
    chunks_db = result.scalars().all()

    retrieved: List[RetrievedEvidenceChunk] = []
    for c in chunks_db:
        # pgvector cosine distance to cosine similarity: similarity = 1 - distance
        # We also compute exact cosine similarity against query_vector
        sim = compute_cosine_similarity(query_vector, list(c.embedding)) if c.embedding is not None else 0.0
        retrieved.append(
            RetrievedEvidenceChunk(
                chunk_id=str(c.id),
                bidder_id=c.bidder_id,
                document_id=c.bid_document_id,
                filename=getattr(c.document, "file_name", "document.pdf") if c.document else "document.pdf",
                page_number=c.page_number,
                chunk_index=c.chunk_index,
                chunk_text=c.content,
                similarity_score=round(float(sim), 4),
                start_char=c.start_char,
                end_char=c.end_char,
                extraction_method=getattr(c, "extraction_method", ExtractionMethod.DIGITAL_TEXT.value),
                ocr_confidence=float(c.ocr_confidence) if c.ocr_confidence is not None else None,
            )
        )

    return retrieved


async def retrieve_evidence_for_clause(
    clause: Union[Dict[str, Any], Any],
    bidder_id: UUID,
    chunks: Optional[List[DocumentChunkItem]] = None,
    db: Optional[AsyncSession] = None,
    embedding_service: Optional[EmbeddingService] = None,
    top_k: int = settings.DEFAULT_RETRIEVAL_TOP_K,
    document_id: Optional[UUID] = None,
    page_number: Optional[int] = None,
) -> ClauseEvidenceResponse:
    """Prepare and execute evidence retrieval for a single tender clause against a specific bidder.

    Strict boundary: Stops at ranked evidence chunks + provenance.
    Does NOT implement PASS/FAIL or scoring.
    """
    code = clause.get("clause_code") if isinstance(clause, dict) else getattr(clause, "clause_code", "GEN-01")
    title = clause.get("title") if isinstance(clause, dict) else getattr(clause, "title", "Requirement")

    # 1. Build rich retrieval query
    query_text = build_clause_retrieval_query(clause)

    # 2. Embed query
    embedder = embedding_service or get_embedding_service()
    query_vector = await embedder.embed_query(query_text)

    # 3. Retrieve ranked chunks under strict bidder isolation
    if chunks is not None:
        top_evidence = retrieve_evidence_from_memory(
            chunks=chunks,
            query_vector=query_vector,
            bidder_id=bidder_id,
            top_k=top_k,
            document_id=document_id,
            page_number=page_number,
            query_text=query_text,
        )
    elif db is not None:
        top_evidence = await retrieve_evidence_from_db(
            db=db,
            query_vector=query_vector,
            bidder_id=bidder_id,
            top_k=top_k,
            document_id=document_id,
            page_number=page_number,
        )
    else:
        raise ValueError("Either 'chunks' or 'db' must be provided for evidence retrieval.")

    return ClauseEvidenceResponse(
        clause_code=code,
        clause_title=title,
        bidder_id=bidder_id,
        query_text=query_text,
        top_evidence=top_evidence,
    )


async def retrieve_evidence_for_tender_clauses(
    clauses: List[Union[Dict[str, Any], Any]],
    bidder_id: UUID,
    chunks: Optional[List[DocumentChunkItem]] = None,
    db: Optional[AsyncSession] = None,
    embedding_service: Optional[EmbeddingService] = None,
    top_k: int = settings.DEFAULT_RETRIEVAL_TOP_K,
) -> List[ClauseEvidenceResponse]:
    """Retrieve top-k evidence chunks for all clauses of a tender against a specific bidder."""
    results: List[ClauseEvidenceResponse] = []
    embedder = embedding_service or get_embedding_service()

    for c in clauses:
        clause_evidence = await retrieve_evidence_for_clause(
            clause=c,
            bidder_id=bidder_id,
            chunks=chunks,
            db=db,
            embedding_service=embedder,
            top_k=top_k,
        )
        results.append(clause_evidence)

    return results
