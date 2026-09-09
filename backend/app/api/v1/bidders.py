import os
import uuid
import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.tender import Tender
from app.models.bidder import Bidder, BidDocument
from app.models.chunk import DocumentChunk
from app.models.evaluation import ComplianceEvaluation
from app.schemas.bidder import (
    BidderCreate,
    BidderResponse,
    BidderDetailResponse,
    BidderDocumentResponse,
    DemoBiddersLoadResponse,
)
from app.services.bidder_ingestion import ingest_bidder_document
from app.services.chunking_service import chunk_ingested_document
from app.services.embedding_service import get_embedding_service
from app.utils.synthetic_bidders import (
    generate_bidder_a_pdf,
    generate_bidder_b_pdf,
    generate_bidder_c_pdf,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Bidders & Ingestion"])

DEMO_BIDDERS_CONFIG = [
    {
        "company_name": "Enterprise Tech Solutions Ltd (Bidder A)",
        "generator": generate_bidder_a_pdf,
        "filename": "Bidder_A_EnterpriseTech.pdf",
        "doc_type": "TECHNICAL_PROPOSAL",
    },
    {
        "company_name": "Legacy Hardware Trading Co (Bidder B)",
        "generator": generate_bidder_b_pdf,
        "filename": "Bidder_B_LegacyHardware.pdf",
        "doc_type": "TECHNICAL_PROPOSAL",
    },
    {
        "company_name": "Apex System Integrators (Bidder C)",
        "generator": generate_bidder_c_pdf,
        "filename": "Bidder_C_ApexSystems.pdf",
        "doc_type": "TECHNICAL_PROPOSAL",
    },
]


async def _get_tender_or_404(tender_id: UUID, db: AsyncSession) -> Tender:
    stmt = select(Tender).where(Tender.id == tender_id)
    tender = (await db.execute(stmt)).scalar_one_or_none()
    if not tender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender with ID {tender_id} not found",
        )
    return tender


async def _build_bidder_detail(bidder: Bidder, db: AsyncSession) -> BidderDetailResponse:
    # Documents count & list
    docs_stmt = select(BidDocument).where(BidDocument.bidder_id == bidder.id).order_by(BidDocument.created_at)
    docs = (await db.execute(docs_stmt)).scalars().all()

    # Chunks count
    chunk_stmt = select(func.count(DocumentChunk.id)).where(DocumentChunk.bidder_id == bidder.id)
    chunks_count = (await db.execute(chunk_stmt)).scalar() or 0

    # Evaluations count
    eval_stmt = select(func.count(ComplianceEvaluation.id)).where(ComplianceEvaluation.bidder_id == bidder.id)
    evals_count = (await db.execute(eval_stmt)).scalar() or 0

    doc_responses = [
        BidderDocumentResponse(
            id=d.id,
            bidder_id=d.bidder_id,
            file_name=d.file_name,
            doc_type=d.doc_type,
            total_pages=d.total_pages,
            empty_pages_count=d.empty_pages_count,
            extraction_status=d.extraction_status,
            created_at=d.created_at,
        )
        for d in docs
    ]

    return BidderDetailResponse(
        id=bidder.id,
        tender_id=bidder.tender_id,
        company_name=bidder.company_name,
        final_status=bidder.final_status,
        documents_count=len(docs),
        chunks_count=chunks_count,
        evaluations_count=evals_count,
        documents=doc_responses,
        created_at=bidder.created_at,
        updated_at=bidder.updated_at,
    )


@router.get("/tenders/{tender_id}/bidders", response_model=List[BidderDetailResponse])
async def list_bidders_for_tender(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all bidders registered under a tender with document and chunk counts."""
    await _get_tender_or_404(tender_id, db)

    stmt = select(Bidder).where(Bidder.tender_id == tender_id).order_by(Bidder.created_at)
    bidders = (await db.execute(stmt)).scalars().all()

    results = []
    for b in bidders:
        detail = await _build_bidder_detail(b, db)
        results.append(detail)
    return results


@router.post("/tenders/{tender_id}/bidders", response_model=BidderDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_bidder(
    tender_id: UUID,
    company_name: str = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    db: AsyncSession = Depends(get_db),
):
    """Register a new bidder for a tender, optionally uploading initial proposal PDFs."""
    await _get_tender_or_404(tender_id, db)

    clean_name = company_name.strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company name must not be empty.",
        )

    # Create bidder
    bidder = Bidder(
        tender_id=tender_id,
        company_name=clean_name,
        final_status="UNDER_REVIEW",
    )
    db.add(bidder)
    await db.flush()

    upload_dir = os.path.join(os.getcwd(), settings.UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    embedder = get_embedding_service()

    # Process files if provided
    if files:
        for file in files:
            if not file.filename:
                continue
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File {file.filename} is not a PDF.",
                )

            contents = await file.read()
            file_uuid = uuid.uuid4()
            saved_filename = f"bid_{file_uuid}_{file.filename}"
            file_path = os.path.join(upload_dir, saved_filename)
            with open(file_path, "wb") as f:
                f.write(contents)

            ingested = ingest_bidder_document(
                pdf_source=contents,
                bidder_id=bidder.id,
                filename=file.filename,
                doc_type="TECHNICAL_PROPOSAL",
            )

            bid_doc = BidDocument(
                bidder_id=bidder.id,
                file_name=file.filename,
                file_path=file_path,
                doc_type="TECHNICAL_PROPOSAL",
                total_pages=ingested.total_pages,
                empty_pages_count=ingested.empty_pages_count,
                extraction_status=ingested.extraction_status.value,
                error_message=ingested.error_message,
            )
            db.add(bid_doc)
            await db.flush()

            # Chunk and embed
            chunks = chunk_ingested_document(ingested)
            if chunks:
                await embedder.embed_chunks(chunks)
                for chunk in chunks:
                    chunk_model = DocumentChunk(
                        bid_document_id=bid_doc.id,
                        bidder_id=bidder.id,
                        page_number=chunk.page_number,
                        chunk_index=chunk.chunk_index,
                        start_char=chunk.start_char,
                        end_char=chunk.end_char,
                        content=chunk.chunk_text,
                        embedding=chunk.embedding,
                    )
                    db.add(chunk_model)
                await db.flush()

    await db.commit()
    await db.refresh(bidder)
    return await _build_bidder_detail(bidder, db)


@router.post("/tenders/{tender_id}/bidders/demo", response_model=DemoBiddersLoadResponse, status_code=status.HTTP_200_OK)
async def load_demo_bidders(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Idempotently load SIH Demo Bidders A, B, and C with full PDF ingestion, chunking, and embedding.

    Guarantees:
    - Running once or multiple times will NEVER duplicate bidders, documents, or chunks.
    - Preserves existing evaluations and officer overrides.
    """
    await _get_tender_or_404(tender_id, db)

    upload_dir = os.path.join(os.getcwd(), settings.UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    embedder = get_embedding_service()

    loaded_bidders: List[Bidder] = []

    for demo_cfg in DEMO_BIDDERS_CONFIG:
        company_name = demo_cfg["company_name"]
        filename = demo_cfg["filename"]
        doc_type = demo_cfg["doc_type"]

        # 1. Idempotent Bidder Retrieval or Creation
        b_stmt = select(Bidder).where(
            Bidder.tender_id == tender_id,
            Bidder.company_name == company_name,
        )
        bidder = (await db.execute(b_stmt)).scalar_one_or_none()

        if not bidder:
            bidder = Bidder(
                tender_id=tender_id,
                company_name=company_name,
                final_status="UNDER_REVIEW",
            )
            db.add(bidder)
            await db.flush()
            logger.info(f"Created demo bidder '{company_name}' ({bidder.id}) for tender {tender_id}")

        # 2. Idempotent Document Retrieval or Creation
        d_stmt = select(BidDocument).where(
            BidDocument.bidder_id == bidder.id,
            BidDocument.file_name == filename,
        )
        bid_doc = (await db.execute(d_stmt)).scalar_one_or_none()

        if not bid_doc:
            pdf_bytes = demo_cfg["generator"]()
            file_path = os.path.join(upload_dir, f"{bidder.id}_{filename}")
            with open(file_path, "wb") as f:
                f.write(pdf_bytes)

            ingested = ingest_bidder_document(
                pdf_source=pdf_bytes,
                bidder_id=bidder.id,
                filename=filename,
                doc_type=doc_type,
            )

            bid_doc = BidDocument(
                bidder_id=bidder.id,
                file_name=filename,
                file_path=file_path,
                doc_type=doc_type,
                total_pages=ingested.total_pages,
                empty_pages_count=ingested.empty_pages_count,
                extraction_status=ingested.extraction_status.value,
                error_message=ingested.error_message,
            )
            db.add(bid_doc)
            await db.flush()

            # Chunk and Embed
            chunks = chunk_ingested_document(ingested)
            if chunks:
                await embedder.embed_chunks(chunks)
                for chunk in chunks:
                    chunk_model = DocumentChunk(
                        bid_document_id=bid_doc.id,
                        bidder_id=bidder.id,
                        page_number=chunk.page_number,
                        chunk_index=chunk.chunk_index,
                        start_char=chunk.start_char,
                        end_char=chunk.end_char,
                        content=chunk.chunk_text,
                        embedding=chunk.embedding,
                    )
                    db.add(chunk_model)
                await db.flush()
            logger.info(f"Ingested and chunked demo document '{filename}' for bidder {bidder.id}")
        else:
            # Check if chunks exist; if missing, re-chunk
            c_check_stmt = select(func.count(DocumentChunk.id)).where(DocumentChunk.bid_document_id == bid_doc.id)
            existing_chunks_count = (await db.execute(c_check_stmt)).scalar() or 0
            if existing_chunks_count == 0 and os.path.exists(bid_doc.file_path):
                with open(bid_doc.file_path, "rb") as f:
                    pdf_bytes = f.read()
                ingested = ingest_bidder_document(
                    pdf_source=pdf_bytes,
                    bidder_id=bidder.id,
                    filename=filename,
                    doc_type=doc_type,
                )
                chunks = chunk_ingested_document(ingested)
                if chunks:
                    await embedder.embed_chunks(chunks)
                    for chunk in chunks:
                        chunk_model = DocumentChunk(
                            bid_document_id=bid_doc.id,
                            bidder_id=bidder.id,
                            page_number=chunk.page_number,
                            chunk_index=chunk.chunk_index,
                            start_char=chunk.start_char,
                            end_char=chunk.end_char,
                            content=chunk.chunk_text,
                            embedding=chunk.embedding,
                        )
                        db.add(chunk_model)
                    await db.flush()

        loaded_bidders.append(bidder)

    await db.commit()

    bidder_details = []
    for b in loaded_bidders:
        await db.refresh(b)
        detail = await _build_bidder_detail(b, db)
        bidder_details.append(detail)

    return DemoBiddersLoadResponse(
        tender_id=tender_id,
        message="SIH Demo Bidders A, B, and C loaded successfully.",
        bidders_count=len(bidder_details),
        bidders=bidder_details,
    )


@router.get("/tenders/{tender_id}/bidders/{bidder_id}", response_model=BidderDetailResponse)
async def get_bidder_detail(
    tender_id: UUID,
    bidder_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Fetch details of a specific bidder, enforcing tender boundary isolation."""
    await _get_tender_or_404(tender_id, db)

    stmt = select(Bidder).where(
        Bidder.id == bidder_id,
        Bidder.tender_id == tender_id,
    )
    bidder = (await db.execute(stmt)).scalar_one_or_none()

    if not bidder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bidder with ID {bidder_id} not found for tender {tender_id}",
        )

    return await _build_bidder_detail(bidder, db)


@router.delete("/tenders/{tender_id}/bidders/{bidder_id}", status_code=status.HTTP_200_OK)
async def delete_bidder(
    tender_id: UUID,
    bidder_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a bidder and all cascading documents, chunks, and evaluations under this tender."""
    await _get_tender_or_404(tender_id, db)

    stmt = select(Bidder).where(
        Bidder.id == bidder_id,
        Bidder.tender_id == tender_id,
    )
    bidder = (await db.execute(stmt)).scalar_one_or_none()

    if not bidder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bidder with ID {bidder_id} not found for tender {tender_id}",
        )

    await db.delete(bidder)
    await db.commit()
    return {"deleted": True, "bidder_id": str(bidder_id), "tender_id": str(tender_id)}
