import pymupdf as fitz
import logging
from typing import List, Dict, Any, Union

logger = logging.getLogger(__name__)


def extract_pages_from_pdf(pdf_source: Union[bytes, str]) -> List[Dict[str, Any]]:
    """Extract text from PDF pages using PyMuPDF only.
    
    Args:
        pdf_source: Raw PDF bytes or file path string.

    Returns:
        List of dictionaries containing page_number (1-indexed), text, and char_count.
    """
    pages_data = []

    if isinstance(pdf_source, bytes):
        doc = fitz.open(stream=pdf_source, filetype="pdf")
    else:
        doc = fitz.open(pdf_source)

    try:
        total_pages = len(doc)
        logger.info(f"Extracting text from PDF with {total_pages} total pages using PyMuPDF.")

        for page_idx in range(total_pages):
            page = doc[page_idx]
            page_text = page.get_text("text") or ""

            # Normalize clean whitespace while keeping line paragraphs
            cleaned_lines = [line.strip() for line in page_text.splitlines() if line.strip()]
            cleaned_text = "\n".join(cleaned_lines)

            pages_data.append({
                "page_number": page_idx + 1,  # 1-indexed
                "text": cleaned_text,
                "char_count": len(cleaned_text),
            })

        return pages_data
    finally:
        doc.close()
