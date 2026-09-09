import logging
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.config import settings
from app.core.database import get_db
from app.schemas.health import HealthResponse, NvidiaHealthResponse
from app.services.nvidia_client import get_nvidia_client, NvidiaClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health & Diagnostics"])


@router.get("", response_model=HealthResponse, summary="API & Database Health Check")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check for API and PostgreSQL database only (does not require NVIDIA)."""
    db_status = "UNKNOWN"
    details = {}

    try:
        # Check basic DB connectivity
        result = await db.execute(text("SELECT 1;"))
        if result.scalar() == 1:
            db_status = "HEALTHY"

        # Check pgvector extension only if PostgreSQL
        if db.bind.dialect.name == "postgresql":
            ext_result = await db.execute(
                text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
            )
            ext_row = ext_result.first()
            if ext_row:
                details["pgvector_extension"] = {
                    "available": True,
                    "version": ext_row[1]
                }
            else:
                details["pgvector_extension"] = {
                    "available": False,
                    "note": "Extension not yet created in public schema"
                }
        else:
            details["database_mode"] = f"{db.bind.dialect.name.upper()} Local Storage"

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = f"ERROR: {str(e)}"
        details["db_error"] = str(e)

    overall_status = "HEALTHY" if db_status == "HEALTHY" else "DEGRADED"

    return HealthResponse(
        status=overall_status,
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        database=db_status,
        details=details
    )


@router.get("/nvidia", response_model=NvidiaHealthResponse, summary="NVIDIA NIM API Health Check")
async def nvidia_health_check(nvidia: NvidiaClient = Depends(get_nvidia_client)):
    """Dedicated endpoint to test NVIDIA NIM connectivity."""
    result = await nvidia.health_check()
    return NvidiaHealthResponse(**result)
