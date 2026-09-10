import pymupdf
import logging
from typing import List, Dict, Any, Union, Optional

from app.core.config import settings
from app.schemas.bidder import ExtractionMethod
from app.services.ocr_engine import BaseOCREngine, get_ocr_engine

logger = logging.getLogger(__name__)


def is_pixmap_blank(pix: Any) -> bool:
    """Determine whether a rendered page pixmap is genuinely blank/solid color.

    Checks pixel variance across the entire image buffer.
    """
    try:
        samples = pix.samples
        if not samples or len(samples) < 100:
            return True

        # In a genuinely blank page, pixel range is negligible (< 10)
        return (max(samples) - min(samples)) < 10
    except Exception as e:
        logger.debug(f"Pixmap blank check failed: {e}; assuming non-blank.")
        return False


def extract_pages_from_pdf(
    pdf_source: Union[bytes, str],
    enable_ocr: Optional[bool] = None,
    ocr_engine: Optional[BaseOCREngine] = None,
) -> List[Dict[str, Any]]:
    """Extract page-by-page text from a PDF with unified digital + OCR convergence.

    Classification State Machine:
    1. DIGITAL_TEXT: Native PyMuPDF extracted >= 10 words. OCR completely bypassed.
    2. EMPTY_SCANNED: Visually blank/empty page.
    3. OCR_FAILED: Rasterization, decode, or engine failure. Never masked as EMPTY_SCANNED.
    4. OCR_LOW_CONFIDENCE: OCR completed, but confidence < threshold (or visually non-empty 0 detections).
    5. OCR_PROCESSED: OCR completed with confidence >= threshold.

    Args:
        pdf_source: Raw PDF bytes or a filesystem path string.
        enable_ocr: Optional bool override for OCR activation (defaults to settings.ENABLE_OCR).
        ocr_engine: Optional BaseOCREngine instance override (defaults to configured singleton).

    Returns:
        List of dicts with page text, word counts, extraction_method, and ocr_confidence.
    """
    should_ocr = enable_ocr if enable_ocr is not None else settings.ENABLE_OCR

    if isinstance(pdf_source, bytes):
        if not pdf_source:
            raise ValueError("PDF source bytes are empty.")
        doc = pymupdf.open(stream=pdf_source, filetype="pdf")
    elif isinstance(pdf_source, str):
        doc = pymupdf.open(pdf_source)
    else:
        raise ValueError("pdf_source must be either bytes or a valid file path string.")

    try:
        if doc.is_encrypted:
            raise ValueError("PDF is encrypted and cannot be parsed without credentials.")

        total_pages = len(doc)
        logger.info(f"Processing PDF ({total_pages} total pages) with OCR enabled={should_ocr}.")

        pages_data: List[Dict[str, Any]] = []

        for page_idx in range(total_pages):
            page_num = page_idx + 1
            page = doc[page_idx]

            # 1. Native PyMuPDF digital text extraction
            raw_page_text = page.get_text("text") or ""
            lines = [line.strip() for line in raw_page_text.splitlines()]
            cleaned_lines = [l for l in lines if l]
            normalized_digital_text = "\n".join(cleaned_lines)
            alnum_words = [w for w in normalized_digital_text.split() if any(c.isalnum() for c in w)]

            # Check digital threshold (>= 10 alphanumeric words)
            if len(alnum_words) >= 10:
                pages_data.append({
                    "page_number": page_num,
                    "text": normalized_digital_text,
                    "char_count": len(normalized_digital_text),
                    "word_count": len(alnum_words),
                    "is_empty": False,
                    "extraction_method": ExtractionMethod.DIGITAL_TEXT.value,
                    "ocr_confidence": None,
                    "error_message": None,
                })
                continue

            # 2. If OCR is globally disabled, fallback to pre-Phase 7 digital behavior
            if not should_ocr:
                is_empty = len(alnum_words) == 0
                pages_data.append({
                    "page_number": page_num,
                    "text": normalized_digital_text,
                    "char_count": len(normalized_digital_text),
                    "word_count": len(alnum_words),
                    "is_empty": is_empty,
                    "extraction_method": ExtractionMethod.EMPTY_SCANNED.value if is_empty else ExtractionMethod.DIGITAL_TEXT.value,
                    "ocr_confidence": None,
                    "error_message": None,
                })
                continue

            # 3. Scanned page candidate: Render in-memory at 200 DPI via PyMuPDF
            image_bytes: Optional[bytes] = None
            is_blank = False
            raster_error: Optional[str] = None

            try:
                pix = page.get_pixmap(dpi=200)
                is_blank = is_pixmap_blank(pix)
                if not is_blank:
                    image_bytes = pix.tobytes("png")
            except Exception as e:
                raster_error = f"Rasterization error on page {page_num}: {str(e)}"
                logger.error(raster_error)

            # 4. Handle rasterization failure -> OCR_FAILED
            if raster_error or (not is_blank and not image_bytes):
                pages_data.append({
                    "page_number": page_num,
                    "text": "",
                    "char_count": 0,
                    "word_count": 0,
                    "is_empty": True,
                    "extraction_method": ExtractionMethod.OCR_FAILED.value,
                    "ocr_confidence": 0.0,
                    "error_message": raster_error or f"Image encoding failed on page {page_num}",
                })
                continue

            # 5. Handle genuinely blank page -> EMPTY_SCANNED
            if is_blank:
                pages_data.append({
                    "page_number": page_num,
                    "text": "",
                    "char_count": 0,
                    "word_count": 0,
                    "is_empty": True,
                    "extraction_method": ExtractionMethod.EMPTY_SCANNED.value,
                    "ocr_confidence": 1.0,
                    "error_message": None,
                })
                continue

            # 6. Page has visual content: Invoke OCR engine
            engine = ocr_engine or get_ocr_engine()
            try:
                ocr_result = engine.ocr_page_image(image_bytes, page_number=page_num)
            except Exception as ocr_ex:
                logger.error(f"OCR engine uncaught exception on page {page_num}: {ocr_ex}")
                pages_data.append({
                    "page_number": page_num,
                    "text": "",
                    "char_count": 0,
                    "word_count": 0,
                    "is_empty": True,
                    "extraction_method": ExtractionMethod.OCR_FAILED.value,
                    "ocr_confidence": 0.0,
                    "error_message": f"OCR processing crash: {str(ocr_ex)}",
                })
                continue

            # 7. Engine reported failure -> OCR_FAILED (Never mask as EMPTY_SCANNED)
            if not ocr_result.is_success:
                pages_data.append({
                    "page_number": page_num,
                    "text": "",
                    "char_count": 0,
                    "word_count": 0,
                    "is_empty": True,
                    "extraction_method": ExtractionMethod.OCR_FAILED.value,
                    "ocr_confidence": 0.0,
                    "error_message": ocr_result.error_message or f"OCR engine reported failure on page {page_num}",
                })
                continue

            # 8. Engine succeeded: Evaluate text and confidence
            ocr_text = (ocr_result.text or "").strip()
            ocr_words = [w for w in ocr_text.split() if any(c.isalnum() for c in w)]
            mean_conf = ocr_result.mean_confidence

            # Visually non-empty page with zero OCR detections -> OCR_LOW_CONFIDENCE (not EMPTY_SCANNED)
            if not ocr_text or len(ocr_words) == 0:
                pages_data.append({
                    "page_number": page_num,
                    "text": "",
                    "char_count": 0,
                    "word_count": 0,
                    "is_empty": True,
                    "extraction_method": ExtractionMethod.OCR_LOW_CONFIDENCE.value,
                    "ocr_confidence": 0.0,
                    "error_message": "Visually non-empty page produced zero readable OCR detections.",
                })
                continue

            # Check confidence threshold
            if mean_conf >= settings.OCR_CONFIDENCE_THRESHOLD:
                method = ExtractionMethod.OCR_PROCESSED.value
            else:
                method = ExtractionMethod.OCR_LOW_CONFIDENCE.value

            pages_data.append({
                "page_number": page_num,
                "text": ocr_text,
                "char_count": len(ocr_text),
                "word_count": len(ocr_words),
                "is_empty": False,
                "extraction_method": method,
                "ocr_confidence": mean_conf,
                "error_message": None,
            })

        return pages_data

    finally:
        doc.close()
