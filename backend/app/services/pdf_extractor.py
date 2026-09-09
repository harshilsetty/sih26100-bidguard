import pymupdf
import logging
from typing import List, Dict, Any, Union

logger = logging.getLogger(__name__)


def extract_pages_from_pdf(pdf_source: Union[bytes, str]) -> List[Dict[str, Any]]:
    """Extract page-by-page text from a tender PDF using PyMuPDF only.

    Args:
        pdf_source: Raw PDF bytes or a filesystem path string.

    Returns:
        List of dicts:
        [
            {
                "page_number": 1,       # Strict 1-indexed page number
                "text": "...",          # Cleaned, layout-preserved page text
                "char_count": 1420,     # Character count
                "word_count": 210,      # Word count
                "is_empty": False       # Flag indicating empty/scanned page
            },
            ...
        ]

    Raises:
        ValueError: If pdf_source is invalid, corrupted, or password-protected.
    """
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
        logger.info(f"Extracting text from PDF ({total_pages} total pages) using PyMuPDF.")

        pages_data: List[Dict[str, Any]] = []

        for page_idx in range(total_pages):
            page = doc[page_idx]
            # Extract plain text preserving reading blocks
            raw_page_text = page.get_text("text") or ""

            # Normalize whitespace while preserving paragraphs and line boundaries
            lines = [line.strip() for line in raw_page_text.splitlines()]
            cleaned_lines = [l for l in lines if l]
            normalized_text = "\n".join(cleaned_lines)

            words = normalized_text.split()

            pages_data.append({
                "page_number": page_idx + 1,  # Strict 1-indexed page number
                "text": normalized_text,
                "char_count": len(normalized_text),
                "word_count": len(words),
                "is_empty": len(words) == 0,
            })

        empty_page_count = sum(1 for p in pages_data if p["is_empty"])
        if empty_page_count > 0:
            logger.warning(
                f"{empty_page_count}/{total_pages} pages contain no extractable text. "
                "These pages might contain scanned images or lack an embedded text layer."
            )

        return pages_data

    finally:
        doc.close()
