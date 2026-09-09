import logging
from typing import List, Optional
from uuid import UUID
from app.schemas.bidder import IngestedDocumentResult, IngestedPageData, DocumentChunkItem

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 800  # characters
DEFAULT_CHUNK_OVERLAP = 120  # characters


def chunk_page_text(
    page: IngestedPageData,
    bidder_id: UUID,
    document_id: UUID,
    filename: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[DocumentChunkItem]:
    """Deterministically chunk a single page's text while preserving character offsets.

    Chunks never cross page boundaries to ensure strict page provenance.
    """
    text = page.text.strip()
    if not text or page.is_empty_or_scanned:
        return []

    chunks: List[DocumentChunkItem] = []
    text_len = len(page.text)

    # If the page text fits comfortably in a single chunk
    if text_len <= chunk_size:
        chunk_id = f"{document_id}_p{page.page_number}_c0"
        chunks.append(
            DocumentChunkItem(
                chunk_id=chunk_id,
                bidder_id=bidder_id,
                document_id=document_id,
                filename=filename,
                page_number=page.page_number,
                chunk_index=0,
                chunk_text=page.text,
                start_char=0,
                end_char=text_len,
            )
        )
        return chunks

    # Sliding window chunking within page boundaries
    start = 0
    chunk_idx = 0
    stride = max(chunk_size - chunk_overlap, 100)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # Snap to sentence or line boundary near the end if not at the absolute end of the page
        if end < text_len:
            lookback_zone = page.text[max(start, end - 60):end]
            # Try to snap to newline first, then sentence end, then space
            split_offset = -1
            for separator in ["\n\n", "\n", ". ", "; ", ", ", " "]:
                idx = lookback_zone.rfind(separator)
                if idx != -1:
                    split_offset = max(start, end - 60) + idx + len(separator)
                    break

            if split_offset > start + 100:
                end = split_offset

        chunk_slice = page.text[start:end].strip()
        if chunk_slice:
            chunk_id = f"{document_id}_p{page.page_number}_c{chunk_idx}"
            chunks.append(
                DocumentChunkItem(
                    chunk_id=chunk_id,
                    bidder_id=bidder_id,
                    document_id=document_id,
                    filename=filename,
                    page_number=page.page_number,
                    chunk_index=chunk_idx,
                    chunk_text=chunk_slice,
                    start_char=start,
                    end_char=end,
                )
            )
            chunk_idx += 1

        if end >= text_len:
            break

        start = start + stride

    return chunks


def chunk_ingested_document(
    ingested_doc: IngestedDocumentResult,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[DocumentChunkItem]:
    """Chunk all pages of an ingested bidder document deterministically.

    Preserves:
    - chunk_id
    - bidder_id
    - document_id
    - filename
    - page_number
    - chunk_text
    - start/end character positions
    """
    all_chunks: List[DocumentChunkItem] = []

    for page in ingested_doc.pages:
        page_chunks = chunk_page_text(
            page=page,
            bidder_id=ingested_doc.bidder_id,
            document_id=ingested_doc.document_id,
            filename=ingested_doc.filename,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        all_chunks.extend(page_chunks)

    logger.info(
        f"Generated {len(all_chunks)} chunks for document '{ingested_doc.filename}' "
        f"({ingested_doc.total_pages} pages) for bidder {ingested_doc.bidder_id}."
    )
    return all_chunks


def chunk_multiple_documents(
    ingested_docs: List[IngestedDocumentResult],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[DocumentChunkItem]:
    """Generate deterministic chunks across multiple ingested documents."""
    total_chunks: List[DocumentChunkItem] = []
    for doc in ingested_docs:
        doc_chunks = chunk_ingested_document(doc, chunk_size, chunk_overlap)
        total_chunks.extend(doc_chunks)
    return total_chunks
