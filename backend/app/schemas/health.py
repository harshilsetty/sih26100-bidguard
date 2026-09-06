from pydantic import BaseModel
from typing import Optional, Dict, Any


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str
    details: Optional[Dict[str, Any]] = None


class NvidiaHealthResponse(BaseModel):
    status: str
    model: str
    base_url: str
    message: str
    latency_ms: Optional[float] = None
    response_sample: Optional[str] = None
