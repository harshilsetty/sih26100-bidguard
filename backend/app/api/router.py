from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.tenders import router as tenders_router

api_router = APIRouter()

# Mount API v1 routes
api_router.include_router(health_router, prefix="/v1")
api_router.include_router(tenders_router, prefix="/v1")
