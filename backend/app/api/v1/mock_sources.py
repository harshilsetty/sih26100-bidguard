"""Mock Government Sources Read-Only Data Explorer API.

Phase 6 — SIH26100 Mock Integrated Verification Foundation.
Provides read-only database query endpoints for:
- GET /api/v1/mock-sources: Summary and record counts across all 5 registries
- GET /api/v1/mock-sources/integrity: Comprehensive dataset integrity validation
- GET /api/v1/mock-sources/showcase: Cross-source mappings for showcase bidders (BIDDER-01 to 10)
- GET /api/v1/mock-sources/{source}: Paginated, searchable query endpoint
- GET /api/v1/mock-sources/{source}/{verification_id}: Record detail
- GET /api/v1/mock-sources/{source}/export: Read-only CSV export
"""

import io
import csv
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.mock_sources import (
    MockGSTNRecord,
    MockUdyamRecord,
    MockMCARecord,
    MockIncomeTaxRecord,
    MockMIIRecord,
    MockNSICRecord,
    MockDigiLockerRecord,
    MOCK_SOURCE_TYPE_LABEL,
)

router = APIRouter(tags=["Mock Sources Explorer"])

SOURCE_MODELS: Dict[str, Any] = {
    "gstn": MockGSTNRecord,
    "udyam": MockUdyamRecord,
    "mca": MockMCARecord,
    "income_tax": MockIncomeTaxRecord,
    "income-tax": MockIncomeTaxRecord,
    "mii": MockMIIRecord,
    "nsic": MockNSICRecord,
    "digilocker": MockDigiLockerRecord,
}

CANONICAL_NAMES: Dict[str, str] = {
    "gstn": "GSTN",
    "udyam": "UDYAM",
    "mca": "MCA",
    "income_tax": "INCOME_TAX",
    "income-tax": "INCOME_TAX",
    "mii": "MII",
    "nsic": "NSIC",
    "digilocker": "DIGILOCKER",
}


def _model_to_dict(obj: Any) -> Dict[str, Any]:
    """Serialize SQLAlchemy model instance to clean JSON dictionary."""
    data = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if col.name == "id" and val is not None:
            data[col.name] = str(val)
        elif hasattr(val, "isoformat"):
            data[col.name] = val.isoformat()
        else:
            data[col.name] = val
    return data


def _get_model_or_404(source_key: str):
    source_lower = source_key.lower().strip()
    if source_lower not in SOURCE_MODELS:
        valid_keys = list(SOURCE_MODELS.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Unknown mock source registry '{source_key}'. Valid sources are: {valid_keys}",
        )
    return SOURCE_MODELS[source_lower], CANONICAL_NAMES[source_lower]


# ---------------------------------------------------------------------------
# 1. Source Overview & Summary Endpoint
# ---------------------------------------------------------------------------

@router.get("/mock-sources", response_model=Dict[str, Any])
async def get_mock_sources_summary(db: AsyncSession = Depends(get_db)):
    """Return overview counts and metadata across mock registries."""
    summary: Dict[str, Any] = {}
    total_records = 0

    meta = {
        "gstn": {
            "name": "GSTN",
            "title": "Goods & Services Tax Network",
            "table": "mock_gstn_records",
            "primary_key": "gstin",
            "description": "Verified annual turnover, tax status, and filing regularity",
        },
        "udyam": {
            "name": "UDYAM",
            "title": "Udyam / Ministry of MSME",
            "table": "mock_udyam_records",
            "primary_key": "udyam_registration_number",
            "description": "MSME classification, enterprise scale (Micro/Small/Medium), exemption qualification",
        },
        "mca": {
            "name": "MCA",
            "title": "Ministry of Corporate Affairs",
            "table": "mock_mca_records",
            "primary_key": "cin",
            "description": "Corporate registry, ROC state, company status (Active/Struck-off)",
        },
        "income_tax": {
            "name": "INCOME_TAX",
            "title": "Income Tax Department / PAN",
            "table": "mock_income_tax_records",
            "primary_key": "pan",
            "description": "PAN verification, taxpayer status, fiscal filing compliance",
        },
        "mii": {
            "name": "MII",
            "title": "Make in India (Local Content)",
            "table": "mock_mii_records",
            "primary_key": "verification_id",
            "description": "Audited domestic local content percentage & Class-I preference certification",
        },
        "nsic": {
            "name": "NSIC",
            "title": "National Small Industries Corporation (SPRS)",
            "table": "mock_nsic_records",
            "primary_key": "registration_number",
            "description": "Single Point Registration Scheme validity, monetary limit, and store classification",
        },
        "digilocker": {
            "name": "DIGILOCKER",
            "title": "DigiLocker Document Verification",
            "table": "mock_digilocker_records",
            "primary_key": "document_reference",
            "description": "Electronic document provenance, issuer verification, and digital signature status",
        },
    }

    core_keys = {"gstn", "udyam", "mca", "income_tax", "mii"}
    for key, model in [
        ("gstn", MockGSTNRecord),
        ("udyam", MockUdyamRecord),
        ("mca", MockMCARecord),
        ("income_tax", MockIncomeTaxRecord),
        ("mii", MockMIIRecord),
        ("nsic", MockNSICRecord),
        ("digilocker", MockDigiLockerRecord),
    ]:
        stmt = select(func.count()).select_from(model)
        count_res = await db.execute(stmt)
        count = count_res.scalar_one()
        if key in core_keys:
            total_records += count
        summary[key] = {**meta[key], "count": count}

    return {
        "sources": summary,
        "total_records": total_records,
        "showcase_bidders_count": 10,
        "demo_scenarios_count": 5,
        "is_mock_system": True,
        "disclaimer": "All records are synthetic demonstration data for SIH 2026. No live government APIs are contacted.",
    }


# ---------------------------------------------------------------------------
# 2. Dataset Integrity Validation Endpoint
# ---------------------------------------------------------------------------

@router.get("/mock-sources/integrity", response_model=Dict[str, Any])
async def get_mock_sources_integrity(db: AsyncSession = Depends(get_db)):
    """Deep read-only validation of synthetic data integrity across all 5 registries."""
    sources_status: Dict[str, Any] = {}
    all_mock = True
    all_labels_valid = True
    total_records = 0

    sources = [
        ("gstn", MockGSTNRecord, "gstin"),
        ("udyam", MockUdyamRecord, "udyam_registration_number"),
        ("mca", MockMCARecord, "cin"),
        ("income_tax", MockIncomeTaxRecord, "pan"),
        ("mii", MockMIIRecord, "verification_id"),
    ]

    for key, model, id_field in sources:
        # Total count
        cnt_res = await db.execute(select(func.count()).select_from(model))
        cnt = cnt_res.scalar_one()
        total_records += cnt

        # Check all marked is_mock = true
        non_mock_res = await db.execute(
            select(func.count()).select_from(model).where(model.is_mock.is_(False))
        )
        non_mock = non_mock_res.scalar_one()

        # Check source_type label
        invalid_label_res = await db.execute(
            select(func.count())
            .select_from(model)
            .where(model.source_type != MOCK_SOURCE_TYPE_LABEL)
        )
        invalid_labels = invalid_label_res.scalar_one()

        # Check unique verification_id
        vid_distinct = await db.execute(
            select(func.count(func.distinct(model.verification_id))).select_from(model)
        )
        vid_count = vid_distinct.scalar_one()

        # Check unique identifier
        id_col = getattr(model, id_field)
        id_distinct = await db.execute(
            select(func.count(func.distinct(id_col))).select_from(model)
        )
        id_count = id_distinct.scalar_one()

        is_source_mock = (non_mock == 0)
        is_source_labels_valid = (invalid_labels == 0)
        is_vid_unique = (vid_count == cnt)
        is_id_unique = (id_count == cnt)

        if not is_source_mock:
            all_mock = False
        if not is_source_labels_valid:
            all_labels_valid = False

        sources_status[key] = {
            "count": cnt,
            "all_mock": is_source_mock,
            "source_type_label_valid": is_source_labels_valid,
            "verification_ids_unique": is_vid_unique,
            "primary_identifiers_unique": is_id_unique,
            "healthy": is_source_mock and is_source_labels_valid and is_vid_unique and is_id_unique,
        }

    # Validate 10 showcase bidder mappings
    showcase_bidders = [f"BIDDER-{i:02d}" for i in range(1, 11)]
    mapping_results: Dict[str, Any] = {}
    all_showcase_mapped = True

    for b_id in showcase_bidders:
        b_mapped = True
        for key, model, _ in sources:
            res = await db.execute(
                select(func.count()).select_from(model).where(model.entity_identifier == b_id)
            )
            c = res.scalar_one()
            if c != 1:
                b_mapped = False
                all_showcase_mapped = False
        mapping_results[b_id] = b_mapped

    # Validate 5 required demo scenarios
    scenarios: Dict[str, Any] = {}

    # Scenario 1: Turnover Contradiction (BIDDER-10 in GSTN has 3.65 Cr)
    b10_gstn = (
        await db.execute(
            select(MockGSTNRecord).where(MockGSTNRecord.entity_identifier == "BIDDER-10")
        )
    ).scalar_one_or_none()
    scenarios["turnover_contradiction"] = {
        "present": (b10_gstn is not None and b10_gstn.verified_turnover == 3.65),
        "target_bidder": "BIDDER-10",
        "verified_turnover_cr": b10_gstn.verified_turnover if b10_gstn else None,
        "description": "Bidder declares ₹8.00 Cr; GSTN mock confirms ₹3.65 Cr",
    }

    # Scenario 2: MSE Exemption (BIDDER-03 in Udyam is ACTIVE MICRO)
    b03_udyam = (
        await db.execute(
            select(MockUdyamRecord).where(MockUdyamRecord.entity_identifier == "BIDDER-03")
        )
    ).scalar_one_or_none()
    scenarios["mse_exemption"] = {
        "present": (
            b03_udyam is not None
            and b03_udyam.status == "ACTIVE"
            and b03_udyam.enterprise_type == "MICRO"
        ),
        "target_bidder": "BIDDER-03",
        "status": b03_udyam.status if b03_udyam else None,
        "enterprise_type": b03_udyam.enterprise_type if b03_udyam else None,
        "description": "Qualifies for MSE tender fee/EMD exemption (ACTIVE MICRO)",
    }

    # Scenario 3: Local Content (BIDDER-10 in MII has 32.0%)
    b10_mii = (
        await db.execute(
            select(MockMIIRecord).where(MockMIIRecord.entity_identifier == "BIDDER-10")
        )
    ).scalar_one_or_none()
    scenarios["local_content"] = {
        "present": (b10_mii is not None and b10_mii.verified_local_content == 32.0),
        "target_bidder": "BIDDER-10",
        "verified_local_content_pct": b10_mii.verified_local_content if b10_mii else None,
        "description": "Bidder declares 50%; BOM & MII verify 32.0% (Class-I deficit)",
    }

    # Scenario 4: Name Variation (BIDDER-04 in MCA has Alpha Technology Private Limited)
    b04_mca = (
        await db.execute(
            select(MockMCARecord).where(MockMCARecord.entity_identifier == "BIDDER-04")
        )
    ).scalar_one_or_none()
    scenarios["name_variation"] = {
        "present": (
            b04_mca is not None and "Alpha Technology Private Limited" in b04_mca.legal_name
        ),
        "target_bidder": "BIDDER-04",
        "mca_legal_name": b04_mca.legal_name if b04_mca else None,
        "description": "Bidder uses 'Alpha Technologies Pvt Ltd' vs MCA 'Alpha Technology Private Limited'",
    }

    # Scenario 5: Inactive Status (BIDDER-08 in GSTN/IT has CANCELLED/INOPERATIVE)
    b08_gstn = (
        await db.execute(
            select(MockGSTNRecord).where(MockGSTNRecord.entity_identifier == "BIDDER-08")
        )
    ).scalar_one_or_none()
    scenarios["inactive_cancelled_status"] = {
        "present": (b08_gstn is not None and b08_gstn.status in ["CANCELLED", "SUSPENDED", "INACTIVE"]),
        "target_bidder": "BIDDER-08",
        "gstn_status": b08_gstn.status if b08_gstn else None,
        "description": "Statutory registration cancelled/inoperative on official registry",
    }

    all_scenarios_valid = all(s["present"] for s in scenarios.values())
    overall_status = (
        "PASS"
        if (total_records == 5000 and all_mock and all_labels_valid and all_showcase_mapped and all_scenarios_valid)
        else "FAIL"
    )

    return {
        "status": overall_status,
        "total_records": total_records,
        "all_records_mock": all_mock,
        "all_labels_valid": all_labels_valid,
        "sources": sources_status,
        "showcase_mappings": {
            "total_mapped": len(showcase_bidders),
            "all_sources_present": all_showcase_mapped,
            "mappings": mapping_results,
        },
        "demo_scenarios": scenarios,
    }


# ---------------------------------------------------------------------------
# 3. Showcase Bidder Cross-Source Inspection Endpoint
# ---------------------------------------------------------------------------

@router.get("/mock-sources/showcase", response_model=Dict[str, Any])
async def get_showcase_bidders(
    bidder_id: Optional[str] = Query(None, description="Optional specific showcase ID, e.g. BIDDER-01"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full cross-source records for showcase bidders (BIDDER-01 through BIDDER-10)."""
    showcase_ids = (
        [bidder_id.upper().strip()]
        if bidder_id
        else [f"BIDDER-{i:02d}" for i in range(1, 11)]
    )

    bidders_data: List[Dict[str, Any]] = []

    for b_id in showcase_ids:
        # Fetch each source record for this bidder
        gstn_rec = (
            await db.execute(select(MockGSTNRecord).where(MockGSTNRecord.entity_identifier == b_id))
        ).scalar_one_or_none()

        udyam_rec = (
            await db.execute(select(MockUdyamRecord).where(MockUdyamRecord.entity_identifier == b_id))
        ).scalar_one_or_none()

        mca_rec = (
            await db.execute(select(MockMCARecord).where(MockMCARecord.entity_identifier == b_id))
        ).scalar_one_or_none()

        it_rec = (
            await db.execute(select(MockIncomeTaxRecord).where(MockIncomeTaxRecord.entity_identifier == b_id))
        ).scalar_one_or_none()

        mii_rec = (
            await db.execute(select(MockMIIRecord).where(MockMIIRecord.entity_identifier == b_id))
        ).scalar_one_or_none()

        bidders_data.append({
            "bidder_id": b_id,
            "records": {
                "gstn": _model_to_dict(gstn_rec) if gstn_rec else None,
                "udyam": _model_to_dict(udyam_rec) if udyam_rec else None,
                "mca": _model_to_dict(mca_rec) if mca_rec else None,
                "income_tax": _model_to_dict(it_rec) if it_rec else None,
                "mii": _model_to_dict(mii_rec) if mii_rec else None,
            },
        })

    return {
        "showcase_bidders": bidders_data,
        "count": len(bidders_data),
        "is_mock": True,
    }


# ---------------------------------------------------------------------------
# 4. Paginated Source Query Endpoint (Search & Filter)
# ---------------------------------------------------------------------------

@router.get("/mock-sources/{source}", response_model=Dict[str, Any])
async def get_mock_source_records(
    source: str,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(25, ge=1, description="Records per page (max 100)"),
    search: Optional[str] = Query(None, description="Search term for identifiers, legal names, or categories"),
    status: Optional[str] = Query(None, description="Filter by status (e.g. ACTIVE, CANCELLED, VERIFIED_CLASS_I)"),
    entity_identifier: Optional[str] = Query(None, description="Filter by exact entity ID (e.g. BIDDER-01)"),
    showcase_only: Optional[bool] = Query(False, description="Filter only showcase bidders (BIDDER-01 to BIDDER-10)"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve paginated and filtered records for a specific mock source registry."""
    if page_size > 100:
        raise HTTPException(
            status_code=400,
            detail="page_size cannot exceed 100 records per page to ensure query stability.",
        )

    model_cls, canonical_name = _get_model_or_404(source)
    source_lower = source.lower().strip()

    stmt = select(model_cls)
    count_stmt = select(func.count()).select_from(model_cls)

    filters = []

    # Status filter
    if status:
        filters.append(model_cls.status == status.strip())

    # Entity identifier filter
    if entity_identifier:
        filters.append(model_cls.entity_identifier == entity_identifier.strip())

    # Showcase bidders only filter
    if showcase_only:
        showcase_ids = [f"BIDDER-{i:02d}" for i in range(1, 11)]
        filters.append(model_cls.entity_identifier.in_(showcase_ids))

    # Search filter (source-specific columns)
    if search and search.strip():
        term = f"%{search.strip()}%"
        if source_lower == "gstn":
            filters.append(
                or_(
                    model_cls.gstin.ilike(term),
                    model_cls.legal_name.ilike(term),
                    model_cls.entity_identifier.ilike(term),
                    model_cls.verification_id.ilike(term),
                )
            )
        elif source_lower == "udyam":
            filters.append(
                or_(
                    model_cls.udyam_registration_number.ilike(term),
                    model_cls.enterprise_name.ilike(term),
                    model_cls.entity_identifier.ilike(term),
                    model_cls.verification_id.ilike(term),
                )
            )
        elif source_lower == "mca":
            filters.append(
                or_(
                    model_cls.cin.ilike(term),
                    model_cls.legal_name.ilike(term),
                    model_cls.entity_identifier.ilike(term),
                    model_cls.verification_id.ilike(term),
                )
            )
        elif source_lower in ["income_tax", "income-tax"]:
            filters.append(
                or_(
                    model_cls.pan.ilike(term),
                    model_cls.entity_name.ilike(term),
                    model_cls.entity_identifier.ilike(term),
                    model_cls.verification_id.ilike(term),
                )
            )
        elif source_lower == "mii":
            filters.append(
                or_(
                    model_cls.product_category.ilike(term),
                    model_cls.entity_identifier.ilike(term),
                    model_cls.verification_id.ilike(term),
                )
            )

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    # Calculate total count
    total_count_res = await db.execute(count_stmt)
    total_count = total_count_res.scalar_one()

    # Pagination calculation
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
    offset = (page - 1) * page_size

    stmt = stmt.offset(offset).limit(page_size)
    res = await db.execute(stmt)
    items = res.scalars().all()

    return {
        "source": canonical_name,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": [_model_to_dict(it) for it in items],
        "is_mock": True,
        "source_type": MOCK_SOURCE_TYPE_LABEL,
    }


# ---------------------------------------------------------------------------
# 5. Single Record Detail Endpoint
# ---------------------------------------------------------------------------

@router.get("/mock-sources/{source}/{verification_id}", response_model=Dict[str, Any])
async def get_mock_source_record_detail(
    source: str,
    verification_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full detailed view of a single mock verification record by verification_id."""
    model_cls, canonical_name = _get_model_or_404(source)

    stmt = select(model_cls).where(model_cls.verification_id == verification_id.strip())
    res = await db.execute(stmt)
    record = res.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"Mock record with verification_id '{verification_id}' not found in registry '{canonical_name}'.",
        )

    return {
        "source": canonical_name,
        "record": _model_to_dict(record),
        "is_mock": True,
        "source_type": MOCK_SOURCE_TYPE_LABEL,
        "disclaimer": "SYNTHETIC / MOCK DATA for SIH demonstration. Not official government verification.",
    }


# ---------------------------------------------------------------------------
# 6. Read-Only CSV Export Endpoint
# ---------------------------------------------------------------------------

@router.get("/mock-sources/{source}/export/csv")
async def export_mock_source_csv(
    source: str,
    db: AsyncSession = Depends(get_db),
):
    """Export all synthetic records of a source to clean CSV for offline inspection."""
    model_cls, canonical_name = _get_model_or_404(source)

    stmt = select(model_cls).order_by(model_cls.verification_id)
    res = await db.execute(stmt)
    records = res.scalars().all()

    if not records:
        raise HTTPException(status_code=404, detail="No records available to export.")

    # Prepare in-memory CSV
    output = io.StringIO()
    col_names = [col.name for col in model_cls.__table__.columns if col.name != "raw_response"]
    writer = csv.DictWriter(output, fieldnames=col_names)
    writer.writeheader()

    for rec in records:
        rec_dict = _model_to_dict(rec)
        row = {k: rec_dict.get(k) for k in col_names}
        writer.writerow(row)

    output.seek(0)
    filename = f"{canonical_name.lower()}_mock_records.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
