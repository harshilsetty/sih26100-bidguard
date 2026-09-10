import io
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class OCRResult(BaseModel):
    """Normalized output contract for any OCR engine implementation."""
    text: str = ""
    mean_confidence: float = 0.0
    boxes: List[Dict[str, Any]] = Field(default_factory=list)
    is_success: bool = True
    error_message: Optional[str] = None


class BaseOCREngine(ABC):
    """Abstract interface for page-level OCR engines."""

    @abstractmethod
    def ocr_page_image(self, image_bytes: bytes, page_number: Optional[int] = None) -> OCRResult:
        """Run optical character recognition on raw raster image bytes (PNG/JPEG).

        Args:
            image_bytes: Rendered page image bytes from PyMuPDF pixmap.
            page_number: Optional 1-indexed page number for context or overrides.

        Returns:
            OCRResult with normalized text, mean confidence (0.0 to 1.0), and bounding details.
        """
        pass


class MockOCREngine(BaseOCREngine):
    """Deterministic Mock OCR Engine for unit, integration, and CI testing.

    Allows tests to simulate high-confidence OCR, low-confidence OCR,
    zero-detection scans, and engine failures deterministically without
    requiring neural network weights or GPU/heavy CPU resources.
    """

    def __init__(
        self,
        default_text: str = "Scanned proposal specification: Equipped with 64 physical cores.",
        default_confidence: float = 0.94,
        force_empty: bool = False,
        force_failure: bool = False,
        failure_error: str = "Simulated OCR engine raster decode error",
        force_low_confidence: bool = False,
        low_confidence_value: float = 0.58,
        per_page_responses: Optional[Dict[int, Dict[str, Any]]] = None,
    ):
        self.default_text = default_text
        self.default_confidence = default_confidence
        self.force_empty = force_empty
        self.force_failure = force_failure
        self.failure_error = failure_error
        self.force_low_confidence = force_low_confidence
        self.low_confidence_value = low_confidence_value
        self.per_page_responses = per_page_responses or {}
        self.call_count = 0

    def ocr_page_image(self, image_bytes: bytes, page_number: Optional[int] = None) -> OCRResult:
        self.call_count += 1

        # Check page-specific override
        if page_number is not None and page_number in self.per_page_responses:
            cfg = self.per_page_responses[page_number]
            return OCRResult(
                text=cfg.get("text", self.default_text),
                mean_confidence=cfg.get("confidence", self.default_confidence),
                is_success=cfg.get("is_success", True),
                error_message=cfg.get("error_message"),
                boxes=cfg.get("boxes", []),
            )

        if self.force_failure:
            return OCRResult(
                text="",
                mean_confidence=0.0,
                boxes=[],
                is_success=False,
                error_message=self.failure_error,
            )

        if self.force_empty:
            return OCRResult(
                text="",
                mean_confidence=0.0,
                boxes=[],
                is_success=True,
                error_message=None,
            )

        conf = self.low_confidence_value if self.force_low_confidence else self.default_confidence
        return OCRResult(
            text=self.default_text,
            mean_confidence=conf,
            boxes=[{"text": self.default_text, "confidence": conf, "box": [[0, 0], [100, 0], [100, 50], [0, 50]]}],
            is_success=True,
            error_message=None,
        )


class PaddleOCREngine(BaseOCREngine):
    """Production OCR Engine using PaddleOCR (PP-OCRv4 Mobile).

    Honest language configuration:
    - Default/verified deployment: English (`settings.OCR_LANGUAGE == "en"`).
    - Lightweight, runs on CPU via in-memory rasterization from PyMuPDF.
    """

    def __init__(self, language: Optional[str] = None):
        self.language = language or settings.OCR_LANGUAGE
        self._ocr = None
        self._is_initialized = False
        self._init_error: Optional[str] = None

    def _ensure_initialized(self):
        if self._is_initialized:
            return
        try:
            from paddleocr import PaddleOCR
            logger.info(f"Initializing PaddleOCR engine with language='{self.language}', use_angle_cls=True")
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self.language,
                show_log=False,
            )
            self._is_initialized = True
        except Exception as e:
            self._init_error = f"Failed to load PaddleOCR engine: {str(e)}"
            logger.warning(f"{self._init_error}. Fallback to error response.")
            self._is_initialized = True

    def ocr_page_image(self, image_bytes: bytes, page_number: Optional[int] = None) -> OCRResult:
        self._ensure_initialized()

        if self._init_error or self._ocr is None:
            return OCRResult(
                text="",
                mean_confidence=0.0,
                boxes=[],
                is_success=False,
                error_message=self._init_error or "PaddleOCR engine is unavailable.",
            )

        try:
            from PIL import Image
            import numpy as np

            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != "RGB":
                image = image.convert("RGB")
            img_np = np.array(image)

            # PaddleOCR returns: [ [ [ [x,y]... ], (text, confidence) ], ... ]
            raw_results = self._ocr.ocr(img_np, cls=True)

            if not raw_results or not raw_results[0]:
                return OCRResult(
                    text="",
                    mean_confidence=0.0,
                    boxes=[],
                    is_success=True,
                    error_message=None,
                )

            extracted_lines: List[str] = []
            confidences: List[float] = []
            boxes_data: List[Dict[str, Any]] = []

            for line in raw_results[0]:
                box_coords = line[0]
                text_content, conf = line[1]
                extracted_lines.append(str(text_content).strip())
                confidences.append(float(conf))
                boxes_data.append({
                    "text": str(text_content).strip(),
                    "confidence": float(conf),
                    "box": box_coords,
                })

            full_text = "\n".join(extracted_lines)
            mean_conf = sum(confidences) / len(confidences) if confidences else 0.0

            return OCRResult(
                text=full_text,
                mean_confidence=round(mean_conf, 4),
                boxes=boxes_data,
                is_success=True,
                error_message=None,
            )

        except Exception as ex:
            logger.error(f"PaddleOCR processing error: {ex}", exc_info=True)
            return OCRResult(
                text="",
                mean_confidence=0.0,
                boxes=[],
                is_success=False,
                error_message=f"PaddleOCR processing exception: {str(ex)}",
            )


# ---------------------------------------------------------------------------
# Singleton Factory & Dependency Injection Hook
# ---------------------------------------------------------------------------

_global_ocr_engine: Optional[BaseOCREngine] = None


def get_ocr_engine() -> BaseOCREngine:
    """Retrieve the configured OCR engine singleton."""
    global _global_ocr_engine
    if _global_ocr_engine is None:
        if settings.OCR_ENGINE == "mock":
            _global_ocr_engine = MockOCREngine()
        else:
            _global_ocr_engine = PaddleOCREngine(language=settings.OCR_LANGUAGE)
    return _global_ocr_engine


def set_ocr_engine(engine: Optional[BaseOCREngine]) -> None:
    """Explicitly override OCR engine instance (primarily for automated unit tests)."""
    global _global_ocr_engine
    _global_ocr_engine = engine
