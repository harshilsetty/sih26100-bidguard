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
    """Health check for API and PostgreSQL database (with engine detection)."""
    db_status = "UNKNOWN"
    active_database = "unknown"
    overall_status = "degraded"
    details = {}

    try:
        # Check basic DB connectivity
        result = await db.execute(text("SELECT 1;"))
        if result.scalar() == 1:
            db_status = "HEALTHY"

        dialect_name = db.bind.dialect.name if (hasattr(db, "bind") and db.bind) else "unknown"

        # Check pgvector extension if PostgreSQL
        if dialect_name == "postgresql":
            active_database = "postgresql"
            overall_status = "healthy"
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
            active_database = "sqlite_fallback"
            overall_status = "degraded"
            details["database_mode"] = f"{dialect_name.upper()} Local Storage"

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = f"ERROR: {str(e)}"
        active_database = "disconnected"
        overall_status = "degraded"
        details["db_error"] = str(e)

    details["database_engine"] = active_database
    details["database_status"] = db_status

    return HealthResponse(
        status=overall_status,
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        database=active_database,
        details=details
    )


@router.get("/nvidia", response_model=NvidiaHealthResponse, summary="NVIDIA NIM API Health Check")
async def nvidia_health_check(nvidia: NvidiaClient = Depends(get_nvidia_client)):
    """Dedicated endpoint to test NVIDIA NIM connectivity."""
    result = await nvidia.health_check()
    return NvidiaHealthResponse(**result)
