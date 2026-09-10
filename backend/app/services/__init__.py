from app.services.nvidia_client import NvidiaClient, get_nvidia_client
from app.services.evidence_fusion_service import EvidenceFusionService
from app.services.cross_source_verifier import CrossSourceVerifier
from app.services.scoring_service import ScoringAndRankingService
from app.services.recommendation_service import RecommendationService
from app.services.ocr_engine import (
    BaseOCREngine,
    MockOCREngine,
    PaddleOCREngine,
    OCRResult,
    get_ocr_engine,
    set_ocr_engine,
)
from app.services.debarment_temporal_service import (
    DebarmentTemporalService,
    DebarmentTemporalEvaluation,
)
from app.services.statutory_adapters import (
    BaseSourceAdapter,
    sanitize_payload,
    GSTNSourceAdapter,
    UdyamSourceAdapter,
    MCASourceAdapter,
    IncomeTaxSourceAdapter,
    MIISourceAdapter,
    DebarmentSourceAdapter,
    StatutoryAdapterRegistry,
    get_statutory_registry,
)
from app.services.statutory_orchestrator import (
    StatutoryVerificationOrchestrator,
    get_statutory_orchestrator,
)

__all__ = [
    "NvidiaClient",
    "get_nvidia_client",
    "EvidenceFusionService",
    "CrossSourceVerifier",
    "ScoringAndRankingService",
    "RecommendationService",
    "BaseOCREngine",
    "MockOCREngine",
    "PaddleOCREngine",
    "OCRResult",
    "get_ocr_engine",
    "set_ocr_engine",
    "BaseSourceAdapter",
    "sanitize_payload",
    "GSTNSourceAdapter",
    "UdyamSourceAdapter",
    "MCASourceAdapter",
    "IncomeTaxSourceAdapter",
    "MIISourceAdapter",
    "DebarmentSourceAdapter",
    "DebarmentTemporalService",
    "DebarmentTemporalEvaluation",
    "StatutoryAdapterRegistry",
    "get_statutory_registry",
    "StatutoryVerificationOrchestrator",
    "get_statutory_orchestrator",
]
