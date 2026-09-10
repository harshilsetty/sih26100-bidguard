import logging
from typing import List, Dict, Any, Union, Optional
from uuid import UUID, uuid4
from app.services.pdf_extractor import extract_pages_from_pdf
from app.schemas.bidder import (
    IngestedDocumentResult,
    IngestedPageData,
    DocumentExtractionStatus,
    BidderDocumentType,
    ExtractionMethod,
)

logger = logging.getLogger(__name__)


def ingest_bidder_document(
    pdf_source: Union[bytes, str],
    bidder_id: UUID,
    document_id: Optional[UUID] = None,
    filename: str = "document.pdf",
    doc_type: Optional[str] = None,
    enable_ocr: Optional[bool] = None,
    ocr_engine: Optional[Any] = None,
) -> IngestedDocumentResult:
    """Ingest a single PDF document for a specific bidder using PyMuPDF and OCR convergence.

    Preserves exact page-level text, captures OCR provenance, detects empty or scanned pages,
    and records extraction status without silently discarding failures.
    """
    doc_id = document_id or uuid4()

    try:
        raw_pages = extract_pages_from_pdf(pdf_source, enable_ocr=enable_ocr, ocr_engine=ocr_engine)
    except Exception as e:
        logger.error(f"Failed to ingest document '{filename}' for bidder {bidder_id}: {e}")
        return IngestedDocumentResult(
            document_id=doc_id,
            bidder_id=bidder_id,
            filename=filename,
            doc_type=doc_type,
            total_pages=0,
            empty_pages_count=0,
            pages=[],
            extraction_status=DocumentExtractionStatus.FAILED,
            error_message=str(e),
        )

    ingested_pages: List[IngestedPageData] = []
    empty_pages_count = 0
    ocr_pages_count = 0
    failed_pages_count = 0

    for p in raw_pages:
        method_str = p.get("extraction_method", ExtractionMethod.DIGITAL_TEXT.value)
        try:
            method_enum = ExtractionMethod(method_str)
        except Exception:
            method_enum = ExtractionMethod.DIGITAL_TEXT

        conf = p.get("ocr_confidence")
        is_empty = p.get("is_empty", False)
        if is_empty or method_enum == ExtractionMethod.EMPTY_SCANNED:
            empty_pages_count += 1
        if method_enum in {ExtractionMethod.OCR_PROCESSED, ExtractionMethod.OCR_LOW_CONFIDENCE}:
            ocr_pages_count += 1
        if method_enum == ExtractionMethod.OCR_FAILED:
            failed_pages_count += 1

        ingested_pages.append(
            IngestedPageData(
                page_number=p["page_number"],
                text=p["text"],
                word_count=p["word_count"],
                char_count=p["char_count"],
                is_empty_or_scanned=is_empty,
                extraction_method=method_enum,
                ocr_confidence=conf,
            )
        )

    total_pages = len(ingested_pages)

    if total_pages == 0:
        status = DocumentExtractionStatus.FAILED
        error_msg = "PDF contains 0 pages."
    elif failed_pages_count == total_pages:
        status = DocumentExtractionStatus.FAILED
        error_msg = "All pages in this document failed optical character recognition."
    elif empty_pages_count == total_pages:
        status = DocumentExtractionStatus.EMPTY_SCANNED
        error_msg = "All pages in this document appear to be empty or scanned images without readable text."
    elif ocr_pages_count > 0:
        status = DocumentExtractionStatus.OCR_PROCESSED
        error_msg = None
    else:
        status = DocumentExtractionStatus.EXTRACTED
        error_msg = None

    logger.info(
        f"Ingested bidder document '{filename}' ({doc_id}) for bidder {bidder_id}: "
        f"{total_pages} total pages, {ocr_pages_count} OCR, {empty_pages_count} empty/scanned, status={status.value}."
    )

    return IngestedDocumentResult(
        document_id=doc_id,
        bidder_id=bidder_id,
        filename=filename,
        doc_type=doc_type,
        total_pages=total_pages,
        empty_pages_count=empty_pages_count,
        pages=ingested_pages,
        extraction_status=status,
        error_message=error_msg,
    )


def ingest_multiple_bidder_documents(
    documents: List[Dict[str, Any]],
    bidder_id: UUID,
    enable_ocr: Optional[bool] = None,
    ocr_engine: Optional[Any] = None,
) -> List[IngestedDocumentResult]:
    """Ingest multiple PDF documents for a single bidder with OCR convergence.

    Args:
        documents: List of dicts, each containing:
            - "source": bytes or file path string
            - "filename": str
            - "doc_type": optional str
            - "document_id": optional UUID
        bidder_id: UUID of the bidder owning these documents.
        enable_ocr: Optional OCR activation override.
        ocr_engine: Optional BaseOCREngine override.

    Returns:
        List of IngestedDocumentResult objects preserving exact page provenance.
    """
    results: List[IngestedDocumentResult] = []

    for doc_item in documents:
        pdf_source = doc_item.get("source") or doc_item.get("pdf_source")
        filename = doc_item.get("filename", "unnamed_document.pdf")
        doc_type = doc_item.get("doc_type")
        doc_id = doc_item.get("document_id")

        result = ingest_bidder_document(
            pdf_source=pdf_source,
            bidder_id=bidder_id,
            document_id=doc_id,
            filename=filename,
            doc_type=doc_type,
            enable_ocr=enable_ocr,
            ocr_engine=ocr_engine,
        )
        results.append(result)

    logger.info(f"Ingested {len(results)} total documents for bidder {bidder_id}.")
    return results
