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
from app.models.clause import TenderClause
from app.schemas.tender import (
    TenderResponse,
    TenderDetailResponse,
    ExtractionResultResponse,
)
from app.schemas.clause import (
    ClauseResponse,
    ClauseCreateRequest,
    ClauseUpdateRequest,
)
from app.services.pdf_extractor import extract_pages_from_pdf
from app.services.clause_extractor import (
    extract_clauses_from_tender_pages,
    CATEGORY_PREFIX_MAP,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenders", tags=["Tenders & Requirement Extraction"])


@router.post("/upload", response_model=TenderResponse, status_code=status.HTTP_201_CREATED)
async def upload_tender_pdf(
    file: UploadFile = File(...),
    title: str = Form(...),
    gem_tender_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Upload a GeM Tender PDF and extract initial page structure using PyMuPDF."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported."
        )

    # Ensure upload directory exists
    upload_dir = os.path.join(os.getcwd(), settings.UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)

    file_uuid = uuid.uuid4()
    saved_filename = f"tender_{file_uuid}_{file.filename}"
    file_path = os.path.join(upload_dir, saved_filename)

    # Read and save file content
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    # Extract pages with PyMuPDF
    try:
        pages = extract_pages_from_pdf(contents)
        total_pages = len(pages)
    except Exception as e:
        logger.error(f"Failed to extract PDF: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse PDF document: {str(e)}"
        )

    # Create Tender record
    tender = Tender(
        title=title,
        gem_tender_id=gem_tender_id,
        file_name=file.filename,
        file_path=file_path,
        total_pages=total_pages,
        extraction_status="UPLOADED",
        next_clause_seq={
            "TECH": 1,
            "FIN": 1,
            "STAT": 1,
            "EXP": 1,
            "DEL": 1,
            "GEN": 1
        }
    )
    db.add(tender)
    await db.commit()
    await db.refresh(tender)

    return TenderResponse(
        id=tender.id,
        title=tender.title,
        gem_tender_id=tender.gem_tender_id,
        file_name=tender.file_name,
        total_pages=tender.total_pages,
        extraction_status=tender.extraction_status,
        created_at=tender.created_at,
        updated_at=tender.updated_at,
        clause_count=0
    )


@router.post("/{tender_id}/extract", response_model=ExtractionResultResponse)
async def extract_tender_clauses(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Run AI clause extraction across 3-page sliding windows using NVIDIA NIM GPT-OSS 20B."""
    # Fetch tender
    stmt = select(Tender).where(Tender.id == tender_id)
    result = await db.execute(stmt)
    tender = result.scalar_one_or_none()

    if not tender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")

    if not tender.file_path or not os.path.exists(tender.file_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tender PDF file not found on disk")

    # Update status to EXTRACTING
    tender.extraction_status = "EXTRACTING"
    await db.commit()

    try:
        with open(tender.file_path, "rb") as f:
            pdf_bytes = f.read()

        pages_data = extract_pages_from_pdf(pdf_bytes)

        # Run extraction using sliding windows + NVIDIA NIM
        current_seq = tender.next_clause_seq or {}
        extracted_clauses, updated_seq = await extract_clauses_from_tender_pages(pages_data, current_seq)

        # Delete any prior unconfirmed clauses if re-extracting
        del_stmt = delete(TenderClause).where(
            TenderClause.tender_id == tender_id,
            TenderClause.is_confirmed == False
        )
        await db.execute(del_stmt)

        # Insert new clauses
        created_models = []
        for c in extracted_clauses:
            clause_obj = TenderClause(
                tender_id=tender.id,
                clause_code=c["clause_code"],
                category=c["category"],
                title=c["title"],
                description=c["description"],
                is_mandatory=c["is_mandatory"],
                rule_config=c["rule_config"],
                source_text=c["source_text"],
                page_number=c["page_number"],
                is_confirmed=False
            )
            db.add(clause_obj)
            created_models.append(clause_obj)

        tender.next_clause_seq = updated_seq
        tender.extraction_status = "REVIEW"
        await db.commit()

        # Reload with clauses
        query = select(TenderClause).where(TenderClause.tender_id == tender_id).order_by(TenderClause.clause_code)
        clauses_result = await db.execute(query)
        persisted_clauses = clauses_result.scalars().all()

        return ExtractionResultResponse(
            tender_id=tender.id,
            extraction_status=tender.extraction_status,
            total_pages=tender.total_pages,
            extracted_count=len(persisted_clauses),
            clauses=[ClauseResponse.model_validate(c) for c in persisted_clauses]
        )

    except Exception as e:
        logger.error(f"Clause extraction failed for tender {tender_id}: {e}")
        tender.extraction_status = "FAILED"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Clause extraction failed: {str(e)}"
        )


@router.get("", response_model=List[TenderResponse])
async def list_tenders(db: AsyncSession = Depends(get_db)):
    """List all tenders with status and clause counts."""
    stmt = (
        select(
            Tender,
            func.count(TenderClause.id).label("clause_count")
        )
        .outerjoin(TenderClause, Tender.id == TenderClause.tender_id)
        .group_by(Tender.id)
        .order_by(Tender.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    output = []
    for tender, count in rows:
        resp = TenderResponse(
            id=tender.id,
            title=tender.title,
            gem_tender_id=tender.gem_tender_id,
            file_name=tender.file_name,
            total_pages=tender.total_pages,
            extraction_status=tender.extraction_status,
            created_at=tender.created_at,
            updated_at=tender.updated_at,
            clause_count=count
        )
        output.append(resp)
    return output


@router.get("/{tender_id}", response_model=TenderDetailResponse)
async def get_tender_detail(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get tender details and all associated clauses."""
    stmt = (
        select(Tender)
        .options(selectinload(Tender.clauses))
        .where(Tender.id == tender_id)
    )
    result = await db.execute(stmt)
    tender = result.scalar_one_or_none()

    if not tender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")

    return TenderDetailResponse(
        id=tender.id,
        title=tender.title,
        gem_tender_id=tender.gem_tender_id,
        file_name=tender.file_name,
        total_pages=tender.total_pages,
        extraction_status=tender.extraction_status,
        created_at=tender.created_at,
        updated_at=tender.updated_at,
        clauses=[ClauseResponse.model_validate(c) for c in sorted(tender.clauses, key=lambda x: x.clause_code)]
    )


@router.get("/{tender_id}/clauses", response_model=List[ClauseResponse])
async def get_tender_clauses(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Fetch all clauses for human review."""
    stmt = (
        select(TenderClause)
        .where(TenderClause.tender_id == tender_id)
        .order_by(TenderClause.clause_code)
    )
    result = await db.execute(stmt)
    clauses = result.scalars().all()
    return [ClauseResponse.model_validate(c) for c in clauses]


@router.post("/{tender_id}/clauses", response_model=ClauseResponse, status_code=status.HTTP_201_CREATED)
async def add_manual_clause(
    tender_id: UUID,
    req: ClauseCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Manually add a custom clause with a unique, non-recycled code."""
    stmt = select(Tender).where(Tender.id == tender_id)
    result = await db.execute(stmt)
    tender = result.scalar_one_or_none()

    if not tender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")

    # Generate next code without recycling
    prefix = CATEGORY_PREFIX_MAP.get(req.category.upper(), "GEN")
    tracker = dict(tender.next_clause_seq or {})
    seq = tracker.get(prefix, 1)
    code = f"{prefix}-{seq:02d}"
    tracker[prefix] = seq + 1
    tender.next_clause_seq = tracker

    new_clause = TenderClause(
        tender_id=tender_id,
        clause_code=code,
        category=req.category.upper(),
        title=req.title.strip(),
        description=req.description.strip(),
        is_mandatory=req.is_mandatory,
        rule_config=req.rule_config,
        source_text=req.source_text.strip(),
        page_number=req.page_number,
        is_confirmed=False
    )
    db.add(new_clause)
    await db.commit()
    await db.refresh(new_clause)
    return ClauseResponse.model_validate(new_clause)


@router.put("/{tender_id}/clauses/{clause_id}", response_model=ClauseResponse)
async def update_clause(
    tender_id: UUID,
    clause_id: UUID,
    req: ClauseUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update clause fields during human review."""
    stmt = select(TenderClause).where(
        TenderClause.id == clause_id,
        TenderClause.tender_id == tender_id
    )
    result = await db.execute(stmt)
    clause = result.scalar_one_or_none()

    if not clause:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")

    if req.category is not None:
        clause.category = req.category.upper()
    if req.title is not None:
        clause.title = req.title.strip()
    if req.description is not None:
        clause.description = req.description.strip()
    if req.is_mandatory is not None:
        clause.is_mandatory = req.is_mandatory
    if req.rule_config is not None:
        clause.rule_config = req.rule_config
    if req.source_text is not None:
        clause.source_text = req.source_text.strip()
    if req.page_number is not None:
        clause.page_number = req.page_number
    if req.is_confirmed is not None:
        clause.is_confirmed = req.is_confirmed

    await db.commit()
    await db.refresh(clause)
    return ClauseResponse.model_validate(clause)


@router.delete("/{tender_id}/clauses/{clause_id}", status_code=status.HTTP_200_OK)
async def delete_clause(
    tender_id: UUID,
    clause_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a clause from review. The sequence number is NOT recycled."""
    stmt = select(TenderClause).where(
        TenderClause.id == clause_id,
        TenderClause.tender_id == tender_id
    )
    result = await db.execute(stmt)
    clause = result.scalar_one_or_none()

    if not clause:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found")

    await db.delete(clause)
    await db.commit()
    return {"deleted": True, "clause_id": str(clause_id)}


@router.post("/{tender_id}/confirm", response_model=TenderDetailResponse)
async def confirm_tender_clauses(
    tender_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Human Confirmation: Lock all clauses and mark tender status as READY."""
    stmt = (
        select(Tender)
        .options(selectinload(Tender.clauses))
        .where(Tender.id == tender_id)
    )
    result = await db.execute(stmt)
    tender = result.scalar_one_or_none()

    if not tender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")

    if not tender.clauses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot confirm tender with 0 clauses. Extract or add clauses first."
        )

    # Lock all clauses
    for c in tender.clauses:
        c.is_confirmed = True

    tender.extraction_status = "READY"
    await db.commit()
    await db.refresh(tender)

    return TenderDetailResponse(
        id=tender.id,
        title=tender.title,
        gem_tender_id=tender.gem_tender_id,
        file_name=tender.file_name,
        total_pages=tender.total_pages,
        extraction_status=tender.extraction_status,
        created_at=tender.created_at,
        updated_at=tender.updated_at,
        clauses=[ClauseResponse.model_validate(c) for c in sorted(tender.clauses, key=lambda x: x.clause_code)]
    )
