import asyncio
import os
import sys
import pymupdf
import logging
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Load environment
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.core.config import settings
from app.services.nvidia_client import get_nvidia_client
from app.services.pdf_extractor import extract_pages_from_pdf
from app.services.clause_extractor import (
    build_page_windows,
    extract_clauses_from_tender_pages,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def create_synthetic_tender_pdf() -> bytes:
    """Create a 4-page realistic synthetic GeM tender document."""
    doc = pymupdf.open()

    # Page 1: Technical Specifications
    p1 = doc.new_page()
    p1.insert_text(
        (40, 60),
        "GOVERNMENT OF INDIA - GeM TENDER INVITATION\n"
        "Tender Reference: GEM/2026/B/8912450\n\n"
        "SECTION 1: TECHNICAL SPECIFICATIONS & STANDARDS\n\n"
        "1.1 Server Compute Infrastructure:\n"
        "The bidder must provide rack servers equipped with minimum 64-core processors and 256GB ECC DDR5 RAM.\n"
        "All hardware components must be certified under BIS and comply with ISO 9001:2015 quality standards.\n\n"
        "1.2 Warranty Coverage:\n"
        "Comprehensive on-site OEM warranty of 3 years shall be provided for all supplied equipment.",
        fontsize=11
    )

    # Page 2: Financial Criteria
    p2 = doc.new_page()
    p2.insert_text(
        (40, 60),
        "SECTION 2: FINANCIAL QUALIFICATION CRITERIA\n\n"
        "2.1 Minimum Average Annual Turnover:\n"
        "Average annual turnover of the bidder during the last three financial years must be at least INR 5.0 Crores.\n"
        "Audited balance sheets and chartered accountant certificates must be uploaded.\n\n"
        "2.2 Earnest Money Deposit (EMD):\n"
        "Bidder must submit an Earnest Money Deposit of INR 10,00,000 via online bank guarantee.\n"
        "EMD exemption is permissible for registered Micro and Small Enterprises (MSEs).",
        fontsize=11
    )

    # Page 3: Statutory & Experience
    p3 = doc.new_page()
    p3.insert_text(
        (40, 60),
        "SECTION 3: STATUTORY ELIGIBILITY & PAST EXPERIENCE\n\n"
        "3.1 Make in India (MII) Preference:\n"
        "Minimum 50 percent local content is mandatory for qualification under Class-I Local Supplier category.\n"
        "Self-certification indicating the percentage of local content must be provided.\n\n"
        "3.2 Past Contract Execution:\n"
        "Bidder must have successfully executed at least 2 similar enterprise IT contracts in the last 3 years.",
        fontsize=11
    )

    # Page 4: Delivery SLA & Penalties
    p4 = doc.new_page()
    p4.insert_text(
        (40, 60),
        "SECTION 4: DELIVERY SCHEDULE & SERVICE LEVEL AGREEMENT\n\n"
        "4.1 Delivery Timelines:\n"
        "All hardware items and software licenses must be delivered and installed within 45 days from contract award.\n\n"
        "4.2 Liquidated Damages & SLA Penalty:\n"
        "Delay in supply will attract liquidated damages of 0.5 percent per week of delay subject to a maximum cap of 10 percent.",
        fontsize=11
    )

    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


async def run_live_test():
    print("=" * 70)
    print("LIVE NVIDIA NIM CLAUSE EXTRACTION TEST (WITH TIMEOUT DEGRADATION)")
    print("=" * 70)
    print(f"Target Model : {settings.NVIDIA_MODEL}")
    print(f"Base URL     : {settings.NVIDIA_BASE_URL}")
    print(f"API Key Set  : {'YES' if bool(settings.NVIDIA_API_KEY) else 'NO'}")

    # Check health first
    client = get_nvidia_client()
    health = await client.health_check()
    print(f"Health Check : {health['status']} (latency: {health.get('latency_ms')} ms)")
    if health["status"] != "HEALTHY":
        print(f"WARNING: Health check returned {health}")

    # 1. Create synthetic PDF
    print("\n[Step 1] Creating synthetic 4-page tender PDF...")
    pdf_bytes = create_synthetic_tender_pdf()
    pages_data = extract_pages_from_pdf(pdf_bytes)
    print(f"Successfully extracted {len(pages_data)} pages with PyMuPDF:")
    for p in pages_data:
        print(f"  - Page {p['page_number']}: {p['word_count']} words, {p['char_count']} chars")

    # 2. Form initial windows
    windows = build_page_windows(pages_data, window_size=3, stride=2)
    print(f"\n[Step 2] Formed {len(windows)} initial sliding windows (3-page windows with 1-page overlap):")
    for i, w in enumerate(windows):
        p_nums = [p["page_number"] for p in w]
        print(f"  - Window {i+1}: Pages {p_nums}")

    # 3. Run extraction with degradation fallback
    print("\n[Step 3] Running AI Clause Extraction with NVIDIA NIM GPT-OSS 20B (temperature=0.0)...")
    seq_tracker = {"TECH": 1, "FIN": 1, "STAT": 1, "EXP": 1, "DEL": 1, "GEN": 1}

    try:
        clauses, updated_seq, report = await extract_clauses_from_tender_pages(
            pages_data,
            seq_tracker,
            return_report=True
        )
    except Exception as e:
        print(f"\n[FAILURE] Exception during extract_clauses_from_tender_pages: {e}")
        import traceback
        traceback.print_exc()
        return

    # 4. Detailed Extraction and Audit Report
    print("\n" + "=" * 70)
    print("EXTRACTION & PROVENANCE AUDIT REPORT")
    print("=" * 70)
    print(f"Original Window Count : {report['original_window_count']}")
    print(f"Successful Windows    : {report['successful_windows']}")
    print(f"Fallback Windows      : {report['fallback_windows']}")
    print(f"Rejected Clauses Count: {len(report['rejected_clauses'])}")
    if report["rejected_clauses"]:
        print("Rejected Clauses Details:")
        for rj in report["rejected_clauses"]:
            print(f"  - '{rj['title']}': {rj['reason']} (quote: '{rj['source_text'][:50]}...')")
    print(f"Final Clause Count    : {report['final_clause_count']}")
    print("Updated Sequence Tracker:", updated_seq)
    print("-" * 70)

    # 5. Output Verified Clauses & Exact Source Texts
    print("\nFINAL ACCEPTED CLAUSES (STRICT PROVENANCE VERIFIED):")
    print("-" * 70)
    for c in clauses:
        print(f"Code         : {c['clause_code']}")
        print(f"Category     : {c['category']}")
        print(f"Title        : {c['title']}")
        print(f"Mandatory    : {c.get('mandatory_status')} (is_mandatory={c['is_mandatory']})")
        print(f"Provenance   : Page {c['page_number']}")
        print(f"Rule Config  : {c.get('rule_config')}")
        print(f"Source Text  : \"{c['source_text']}\"")
        print("-" * 70)

    # 6. Quality Assertions
    failures = []
    if len(clauses) == 0:
        failures.append("Zero clauses were accepted.")

    for c in clauses:
        # Check source text does not end with incomplete/truncated tokens
        tokens = c["source_text"].strip().split()
        if tokens:
            last = tokens[-1].lower()
            if last == "pe" or last in {"of", "to", "in", "and", "or"}:
                failures.append(f"Clause {c['clause_code']} contains an incomplete/truncated source quote ending with '{last}'")
            if c["source_text"].endswith(("...", "…")):
                failures.append(f"Clause {c['clause_code']} ends with ellipsis")

    if failures:
        print("\n[STATUS: ISSUES DETECTED]")
        for f in failures:
            print("  -", f)
    else:
        print("\n[STATUS: SUCCESS] All final clauses contain complete, verifiable source quotes without truncation!")


if __name__ == "__main__":
    asyncio.run(run_live_test())
