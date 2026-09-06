import asyncio
import os
from dotenv import load_dotenv

# Load root .env
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.services.pdf_extractor import extract_pages_from_pdf
from app.services.clause_extractor import build_page_windows, extract_clauses_from_tender_pages

async def main():
    print("=== 1. Testing PyMuPDF Page Extraction ===")
    sample_file = "sample_data/sample_gem_tender.pdf"
    pages = extract_pages_from_pdf(sample_file)
    print(f"Total pages extracted: {len(pages)}")
    for p in pages:
        print(f"  Page {p['page_number']}: {p['char_count']} chars")

    print("\n=== 2. Testing 3-Page Window Generation with 1-Page Overlap ===")
    windows = build_page_windows(pages, window_size=3, stride=2)
    print(f"Total windows created: {len(windows)}")
    for i, w in enumerate(windows):
        p_nums = [p['page_number'] for p in w]
        print(f"  Window {i}: Pages {p_nums}")

    print("\n=== 3. Testing NVIDIA NIM Clause Extraction & Grounding ===")
    seq_tracker = {"TECH": 1, "FIN": 1, "STAT": 1, "EXP": 1, "DEL": 1, "GEN": 1}
    clauses, updated_seq = await extract_clauses_from_tender_pages(pages, seq_tracker)
    print(f"Total Unique Clauses Extracted: {len(clauses)}")
    print("Updated Sequence Tracker:", updated_seq)

    print("\n=== 4. Verifying Extracted Clauses Details ===")
    for c in clauses:
        print(f"[{c['clause_code']}] ({c['category']}) {c['title']}")
        print(f"  Provenance: Page {c['page_number']}")
        print(f"  Mandatory: {c['is_mandatory']}")
        print(f"  Rule Config (Draft): {c['rule_config']}")
        print(f"  Source Quote: \"{c['source_text']}\"")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())
