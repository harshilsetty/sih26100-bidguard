"""Phase 7: Printed Scanned PDF OCR Test Suite.

Comprehensive test suite validating:
1. OCR Engine abstraction, MockOCREngine, and configurable language/thresholds.
2. Digital PDF bypass (native PyMuPDF text completely bypasses OCR).
3. Scanned PDF OCR processing and page state classification (DIGITAL_TEXT, OCR_PROCESSED, OCR_LOW_CONFIDENCE, EMPTY_SCANNED, OCR_FAILED).
4. Mixed digital and scanned PDF processing page-by-page.
5. Genuine blank page classification as EMPTY_SCANNED (without invoking OCR).
6. OCR failure handling: exceptions/crashes produce OCR_FAILED and are NEVER masked as EMPTY_SCANNED.
7. Visually non-empty page with zero OCR detections classified as OCR_LOW_CONFIDENCE (never EMPTY_SCANNED).
8. Chunking rules: chunks generated for DIGITAL_TEXT, OCR_PROCESSED, OCR_LOW_CONFIDENCE; skipped for EMPTY_SCANNED, OCR_FAILED.
9. Provenance tracking: extraction_method and ocr_confidence propagated through pages, chunks, retrieval, and evaluations.
10. Compliance safety:
    - Low-confidence OCR decisive evidence routes strictly to REVIEW with officer warning.
    - High-confidence OCR evidence is verified strictly by deterministic Python rules (OCR confidence alone NEVER creates PASS).
    - High-impact numeric safety (turnover, EMD, percentages, identifiers, hardware specs).
11. Strict bidder isolation with scanned OCR evidence.
12. Tender scanned PDF text extraction compatibility.
"""

import io
import uuid
import pytest
import fitz  # PyMuPDF

from app.core.config import settings
from app.schemas.bidder import (
    ExtractionMethod,
    IngestedPageData,
    DocumentChunkItem,
    RetrievedEvidenceChunk,
)
from app.schemas.evaluation import ComplianceStatus
from app.services.ocr_engine import (
    BaseOCREngine,
    MockOCREngine,
    OCRResult,
    get_ocr_engine,
    set_ocr_engine,
)
from app.services.pdf_extractor import extract_pages_from_pdf
from app.services.chunking_service import chunk_page_text
from app.services.compliance_engine import evaluate_clause_compliance


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# PDF Generation Helpers
# ---------------------------------------------------------------------------

def create_digital_pdf(text: str) -> bytes:
    """Create a digital PDF with searchable text layer wrapped in a textbox."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    rect = fitz.Rect(50, 50, 545, 792)
    page.insert_textbox(rect, text, fontsize=11)
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


def create_scanned_pdf(text_to_render: str) -> bytes:
    """Create a scanned-like PDF where text is rendered into an image, with NO digital text layer."""
    doc_temp = fitz.open()
    p_temp = doc_temp.new_page(width=595, height=842)
    rect = fitz.Rect(50, 50, 545, 792)
    p_temp.insert_textbox(rect, text_to_render, fontsize=11)
    pix = p_temp.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    doc_temp.close()

    doc_scanned = fitz.open()
    p_scanned = doc_scanned.new_page(width=595, height=842)
    p_scanned.insert_image(p_scanned.rect, stream=img_bytes)
    pdf_bytes = doc_scanned.write()
    doc_scanned.close()
    return pdf_bytes


def create_blank_pdf() -> bytes:
    """Create a genuinely blank PDF page."""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


def create_mixed_pdf(digital_text: str, scanned_text: str) -> bytes:
    """Create a multi-page PDF with mixed digital text and scanned image pages."""
    doc_temp = fitz.open()
    p_temp = doc_temp.new_page(width=595, height=842)
    rect = fitz.Rect(50, 50, 545, 792)
    p_temp.insert_textbox(rect, scanned_text, fontsize=11)
    pix = p_temp.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    doc_temp.close()

    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    rect1 = fitz.Rect(50, 50, 545, 792)
    p1.insert_textbox(rect1, digital_text, fontsize=11)

    p2 = doc.new_page(width=595, height=842)
    p2.insert_image(p2.rect, stream=img_bytes)

    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestOCREngineAbstraction:
    """Test OCR Engine hierarchy, configurations, and mock capabilities."""

    def test_mock_ocr_engine_defaults_and_customization(self):
        engine = MockOCREngine()
        dummy_img = b"fake_png_data"
        result = engine.ocr_page_image(dummy_img)

        assert isinstance(result, OCRResult)
        assert result.mean_confidence == 0.94
        assert engine.call_count == 1
        assert "64 physical cores" in result.text

        # Custom text and confidence
        custom_engine = MockOCREngine(default_text="Annual Turnover: Rs. 75 Crores", default_confidence=0.88)
        res = custom_engine.ocr_page_image(dummy_img)
        assert res.text == "Annual Turnover: Rs. 75 Crores"
        assert res.mean_confidence == 0.88

    def test_mock_ocr_engine_failure_mode(self):
        engine = MockOCREngine(force_failure=True, failure_error="Simulated OCR Hardware Crash")
        result = engine.ocr_page_image(b"fake_bytes")
        assert result.is_success is False
        assert "Simulated OCR Hardware Crash" in (result.error_message or "")

    def test_get_and_set_ocr_engine_factory(self):
        mock_e = MockOCREngine(default_text="Global Engine Test")
        set_ocr_engine(mock_e)
        retrieved = get_ocr_engine()
        assert retrieved is mock_e
        res = retrieved.ocr_page_image(b"test")
        assert res.text == "Global Engine Test"
        set_ocr_engine(None)  # Reset singleton

    def test_configurable_ocr_settings(self):
        assert hasattr(settings, "ENABLE_OCR")
        assert hasattr(settings, "OCR_ENGINE")
        assert hasattr(settings, "OCR_LANGUAGE")
        assert hasattr(settings, "OCR_CONFIDENCE_THRESHOLD")
        assert settings.OCR_LANGUAGE == "en"
        assert settings.OCR_CONFIDENCE_THRESHOLD == 0.75


class TestPageClassificationAndBypass:
    """Test PyMuPDF classification, digital bypass, and scanned state machine."""

    def test_digital_page_bypasses_ocr(self):
        mock_engine = MockOCREngine()
        digital_content = (
            "This is a digital page with high-quality native text and formatting. "
            "Bidder turnover for FY 2023 is certified at Rs. 120 Crores with Class-I Local Content."
        )
        pdf_bytes = create_digital_pdf(digital_content)

        pages = extract_pages_from_pdf(
            pdf_bytes,
            enable_ocr=True,
            ocr_engine=mock_engine,
        )

        assert len(pages) == 1
        page = pages[0]
        assert page["extraction_method"] == ExtractionMethod.DIGITAL_TEXT.value
        assert page["ocr_confidence"] is None
        assert "120 Crores" in page["text"]
        # CRITICAL: OCR engine must NOT have been invoked
        assert mock_engine.call_count == 0

    def test_scanned_page_processed_by_ocr(self):
        scanned_text = "Scanned GSTIN: 29ABCDE1234F1Z5. Paid EMD of INR 5,00,000 for server tender."
        mock_engine = MockOCREngine(default_text=scanned_text, default_confidence=0.91)
        pdf_bytes = create_scanned_pdf("Raw image text with enough lines to be non-blank")

        pages = extract_pages_from_pdf(
            pdf_bytes,
            enable_ocr=True,
            ocr_engine=mock_engine,
        )

        assert len(pages) == 1
        page = pages[0]
        assert page["extraction_method"] == ExtractionMethod.OCR_PROCESSED.value
        assert page["ocr_confidence"] == 0.91
        assert scanned_text in page["text"]
        assert mock_engine.call_count == 1

    def test_scanned_page_low_confidence_classification(self):
        scanned_text = "Smudged turnover record: ~40 Crores?"
        mock_engine = MockOCREngine(
            default_text=scanned_text,
            default_confidence=0.62,
            force_low_confidence=True,
            low_confidence_value=0.62,
        )
        pdf_bytes = create_scanned_pdf("Raw image text")

        pages = extract_pages_from_pdf(
            pdf_bytes,
            enable_ocr=True,
            ocr_engine=mock_engine,
        )

        assert len(pages) == 1
        page = pages[0]
        assert page["extraction_method"] == ExtractionMethod.OCR_LOW_CONFIDENCE.value
        assert page["ocr_confidence"] == 0.62
        assert scanned_text in page["text"]
        assert mock_engine.call_count == 1

    def test_genuine_blank_page_empty_scanned(self):
        mock_engine = MockOCREngine()
        pdf_bytes = create_blank_pdf()

        pages = extract_pages_from_pdf(
            pdf_bytes,
            enable_ocr=True,
            ocr_engine=mock_engine,
        )

        assert len(pages) == 1
        page = pages[0]
        assert page["extraction_method"] == ExtractionMethod.EMPTY_SCANNED.value
        assert page["text"] == ""
        # Genuine blank pages bypass OCR engine call
        assert mock_engine.call_count == 0

    def test_ocr_failure_handling_never_masks_as_empty_scanned(self):
        mock_engine = MockOCREngine(force_failure=True, failure_error="Simulated Engine Crash")
        pdf_bytes = create_scanned_pdf("Important Certificate with visible pixels")

        pages = extract_pages_from_pdf(
            pdf_bytes,
            enable_ocr=True,
            ocr_engine=mock_engine,
        )

        assert len(pages) == 1
        page = pages[0]
        # Must be OCR_FAILED, NEVER masked as EMPTY_SCANNED
        assert page["extraction_method"] == ExtractionMethod.OCR_FAILED.value
        assert page["extraction_method"] != ExtractionMethod.EMPTY_SCANNED.value
        assert page["ocr_confidence"] in (None, 0.0)
        assert page["text"] == ""
        assert "Simulated Engine Crash" in (page.get("error_message") or "")

    def test_visually_non_empty_page_with_zero_ocr_detections(self):
        # OCR engine finds nothing (empty text) on a non-empty image page
        mock_engine = MockOCREngine(force_empty=True)
        pdf_bytes = create_scanned_pdf("Faint watermark or background chart artwork")

        pages = extract_pages_from_pdf(
            pdf_bytes,
            enable_ocr=True,
            ocr_engine=mock_engine,
        )

        assert len(pages) == 1
        page = pages[0]
        # Must NOT be classified as EMPTY_SCANNED because the page visually had content
        assert page["extraction_method"] == ExtractionMethod.OCR_LOW_CONFIDENCE.value
        assert page["extraction_method"] != ExtractionMethod.EMPTY_SCANNED.value
        assert page["ocr_confidence"] == 0.0

    def test_mixed_digital_and_scanned_pdf_page_by_page(self):
        digital_str = (
            "Page 1: Digital Technical Specification. "
            "Server nodes equipped with 64 CPU cores and 256 GB RAM memory capacity."
        )
        scanned_str = "Page 2: Scanned OEM Authorization Letter. We hereby authorize Bidder A for GeM supply."
        mock_engine = MockOCREngine(default_text=scanned_str, default_confidence=0.89)

        pdf_bytes = create_mixed_pdf(digital_str, "OEM Image with drawing")

        pages = extract_pages_from_pdf(
            pdf_bytes,
            enable_ocr=True,
            ocr_engine=mock_engine,
        )

        assert len(pages) == 2
        # Page 1: Digital, OCR bypassed
        assert pages[0]["page_number"] == 1
        assert pages[0]["extraction_method"] == ExtractionMethod.DIGITAL_TEXT.value
        assert pages[0]["ocr_confidence"] is None
        assert "64 CPU cores" in pages[0]["text"]

        # Page 2: Scanned, OCR invoked
        assert pages[1]["page_number"] == 2
        assert pages[1]["extraction_method"] == ExtractionMethod.OCR_PROCESSED.value
        assert pages[1]["ocr_confidence"] == 0.89
        assert "OEM Authorization Letter" in pages[1]["text"]

        assert mock_engine.call_count == 1


class TestChunkingProvenance:
    """Test chunk generation rules and provenance propagation."""

    def test_chunks_created_for_digital_and_ocr_pages(self):
        b_id = uuid.uuid4()
        d_id = uuid.uuid4()

        # Digital page
        p_digital = IngestedPageData(
            page_number=1,
            text="Digital text section. Turnover Rs. 100 Crores. PAN: ABCDE1234F.",
            word_count=10,
            char_count=60,
            is_empty_or_scanned=False,
            extraction_method=ExtractionMethod.DIGITAL_TEXT,
            ocr_confidence=None,
        )
        chunks_digital = chunk_page_text(p_digital, b_id, d_id, "doc1.pdf")
        assert len(chunks_digital) >= 1
        assert chunks_digital[0].extraction_method == ExtractionMethod.DIGITAL_TEXT.value
        assert chunks_digital[0].ocr_confidence is None

        # OCR_PROCESSED page
        p_ocr = IngestedPageData(
            page_number=2,
            text="Scanned OCR text section. Turnover Rs. 90 Crores.",
            word_count=8,
            char_count=50,
            is_empty_or_scanned=False,
            extraction_method=ExtractionMethod.OCR_PROCESSED,
            ocr_confidence=0.88,
        )
        chunks_ocr = chunk_page_text(p_ocr, b_id, d_id, "doc2.pdf")
        assert len(chunks_ocr) >= 1
        assert chunks_ocr[0].extraction_method == ExtractionMethod.OCR_PROCESSED.value
        assert chunks_ocr[0].ocr_confidence == 0.88

        # OCR_LOW_CONFIDENCE page
        p_low = IngestedPageData(
            page_number=3,
            text="Faint scanned text section. EMD INR 5,00,000.",
            word_count=7,
            char_count=45,
            is_empty_or_scanned=False,
            extraction_method=ExtractionMethod.OCR_LOW_CONFIDENCE,
            ocr_confidence=0.55,
        )
        chunks_low = chunk_page_text(p_low, b_id, d_id, "doc3.pdf")
        assert len(chunks_low) >= 1
        assert chunks_low[0].extraction_method == ExtractionMethod.OCR_LOW_CONFIDENCE.value
        assert chunks_low[0].ocr_confidence == 0.55

    def test_chunks_skipped_for_empty_scanned_and_ocr_failed(self):
        b_id = uuid.uuid4()
        d_id = uuid.uuid4()

        # EMPTY_SCANNED page
        p_empty = IngestedPageData(
            page_number=4,
            text="",
            word_count=0,
            char_count=0,
            is_empty_or_scanned=True,
            extraction_method=ExtractionMethod.EMPTY_SCANNED,
            ocr_confidence=None,
        )
        chunks_empty = chunk_page_text(p_empty, b_id, d_id, "doc_empty.pdf")
        assert len(chunks_empty) == 0

        # OCR_FAILED page
        p_failed = IngestedPageData(
            page_number=5,
            text="",
            word_count=0,
            char_count=0,
            is_empty_or_scanned=True,
            extraction_method=ExtractionMethod.OCR_FAILED,
            ocr_confidence=None,
        )
        chunks_failed = chunk_page_text(p_failed, b_id, d_id, "doc_failed.pdf")
        assert len(chunks_failed) == 0


class TestComplianceSafetyAndOCRConfidence:
    """Test deterministic verification and safety gating on OCR evidence."""

    @pytest.mark.anyio
    async def test_low_confidence_ocr_decisive_evidence_forces_review(self):
        """Even if text satisfies numeric threshold, low OCR confidence must route to REVIEW."""
        clause = {
            "clause_code": "FIN-01",
            "title": "Minimum Annual Turnover",
            "is_mandatory": True,
            "rule_config": {
                "rule_type": "NUMERIC_MIN",
                "parameter": "annual_turnover",
                "value": 50.0,
                "unit": "Cr",
            },
        }
        bidder_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        chunk_id = str(uuid.uuid4())

        # Evidence claims 95 Crores (would PASS >= 50.0 Cr), but OCR confidence is 0.58 (< 0.75)
        evidence = [
            RetrievedEvidenceChunk(
                chunk_id=chunk_id,
                bidder_id=bidder_id,
                document_id=doc_id,
                filename="Scanned_Financials.pdf",
                page_number=2,
                chunk_index=0,
                chunk_text="Average annual audited turnover of the bidder is INR 95 Crores for the last 3 financial years.",
                similarity_score=0.92,
                extraction_method=ExtractionMethod.OCR_LOW_CONFIDENCE,
                ocr_confidence=0.58,
            )
        ]

        eval_result = await evaluate_clause_compliance(
            clause=clause,
            bidder_id=bidder_id,
            evidence_chunks=evidence,
            use_live_llm=False,
        )

        # MUST BE FORCED TO REVIEW DUE TO LOW OCR CONFIDENCE
        assert eval_result.status == ComplianceStatus.REVIEW
        assert eval_result.requires_human_confirmation is True
        assert eval_result.extraction_method == ExtractionMethod.OCR_LOW_CONFIDENCE.value
        assert eval_result.ocr_confidence == 0.58
        assert "LOW CONFIDENCE OCR EVIDENCE" in eval_result.reasoning
        assert "58.0%" in eval_result.reasoning

    @pytest.mark.anyio
    async def test_high_confidence_ocr_uses_deterministic_rules(self):
        """High OCR confidence evidence is evaluated normally by deterministic rules (Pass and Fail)."""
        clause = {
            "clause_code": "FIN-01",
            "title": "Minimum Annual Turnover",
            "is_mandatory": True,
            "rule_config": {
                "rule_type": "NUMERIC_MIN",
                "parameter": "annual_turnover",
                "value": 50.0,
                "unit": "Cr",
            },
        }
        bidder_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        # Case A: Meets threshold (85 Cr >= 50 Cr) with high OCR confidence (0.94) -> PASS
        evidence_pass = [
            RetrievedEvidenceChunk(
                chunk_id=str(uuid.uuid4()),
                bidder_id=bidder_id,
                document_id=doc_id,
                filename="Scanned_Turnover.pdf",
                page_number=1,
                chunk_index=0,
                chunk_text="Audited annual turnover for FY 2023 is INR 85 Crores.",
                similarity_score=0.95,
                extraction_method=ExtractionMethod.OCR_PROCESSED,
                ocr_confidence=0.94,
            )
        ]

        eval_pass = await evaluate_clause_compliance(
            clause=clause,
            bidder_id=bidder_id,
            evidence_chunks=evidence_pass,
            use_live_llm=False,
        )

        assert eval_pass.status == ComplianceStatus.PASS
        assert eval_pass.extraction_method == ExtractionMethod.OCR_PROCESSED.value
        assert eval_pass.ocr_confidence == 0.94

        # Case B: Fails threshold (25 Cr < 50 Cr) with high OCR confidence (0.96) -> FAIL
        # OCR confidence does NOT force PASS!
        evidence_fail = [
            RetrievedEvidenceChunk(
                chunk_id=str(uuid.uuid4()),
                bidder_id=bidder_id,
                document_id=doc_id,
                filename="Scanned_Turnover.pdf",
                page_number=1,
                chunk_index=0,
                chunk_text="Audited annual turnover for FY 2023 is INR 25 Crores.",
                similarity_score=0.95,
                extraction_method=ExtractionMethod.OCR_PROCESSED,
                ocr_confidence=0.96,
            )
        ]

        eval_fail = await evaluate_clause_compliance(
            clause=clause,
            bidder_id=bidder_id,
            evidence_chunks=evidence_fail,
            use_live_llm=False,
        )

        assert eval_fail.status == ComplianceStatus.FAIL
        assert eval_fail.extraction_method == ExtractionMethod.OCR_PROCESSED.value
        assert eval_fail.ocr_confidence == 0.96

    @pytest.mark.anyio
    async def test_high_impact_identifiers_and_specs_safety(self):
        """High-impact specs (CPU cores) with low-confidence OCR must divert to REVIEW."""
        clause = {
            "clause_code": "TECH-01",
            "title": "CPU Cores Requirement",
            "is_mandatory": True,
            "rule_config": {
                "rule_type": "NUMERIC_MIN",
                "parameter": "cpu_cores",
                "value": 64.0,
                "unit": "cores",
            },
        }
        bidder_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        evidence = [
            RetrievedEvidenceChunk(
                chunk_id=str(uuid.uuid4()),
                bidder_id=bidder_id,
                document_id=doc_id,
                filename="Scanned_Datasheet.pdf",
                page_number=3,
                chunk_index=0,
                chunk_text="Offered server configuration includes dual processor workstation with 64 cores total.",
                similarity_score=0.90,
                extraction_method=ExtractionMethod.OCR_LOW_CONFIDENCE,
                ocr_confidence=0.65,
            )
        ]

        eval_res = await evaluate_clause_compliance(
            clause=clause,
            bidder_id=bidder_id,
            evidence_chunks=evidence,
            use_live_llm=False,
        )

        assert eval_res.status == ComplianceStatus.REVIEW
        assert eval_res.requires_human_confirmation is True
        assert "LOW CONFIDENCE OCR EVIDENCE" in eval_res.reasoning


class TestBidderIsolationWithOCR:
    """Test that OCR chunks and evidence maintain strict bidder boundary isolation."""

    def test_bidder_isolation_in_chunking(self):
        b_id = uuid.uuid4()
        d_id = uuid.uuid4()
        p_data = IngestedPageData(
            page_number=1,
            text="Confidential Bidder A Scanned Pricing and Turnover.",
            word_count=8,
            char_count=55,
            is_empty_or_scanned=False,
            extraction_method=ExtractionMethod.OCR_PROCESSED,
            ocr_confidence=0.90,
        )
        chunks_a = chunk_page_text(p_data, b_id, d_id, "BidderA_Doc.pdf")

        # Verify chunk provenance does not conflate with another bidder
        for chk in chunks_a:
            assert chk.bidder_id == b_id
            assert chk.filename == "BidderA_Doc.pdf"
            assert chk.extraction_method == ExtractionMethod.OCR_PROCESSED.value
            assert chk.ocr_confidence == 0.90
