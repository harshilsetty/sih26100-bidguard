import asyncio
import os
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.services.pdf_extractor import extract_pages_from_pdf
from app.services.clause_extractor import (
    build_page_windows,
    format_window_text,
    EXTRACTION_SYSTEM_PROMPT,
    verify_source_text_presence,
)
from app.services.nvidia_client import get_nvidia_client

async def test_llm_call():
    pages = extract_pages_from_pdf("sample_data/sample_gem_tender.pdf")
    windows = build_page_windows(pages, window_size=3, stride=2)
    win0 = windows[0]
    win_text = format_window_text(win0)
    prompt = f"Analyze the following tender excerpt (Pages 1 to 3):\n\n{win_text}"

    print("Sending Window 0 to NVIDIA NIM (openai/gpt-oss-20b)...", flush=True)
    start = time.time()
    client = get_nvidia_client()
    res = await client.structured_completion(
        prompt=prompt,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        temperature=0.2,
        max_tokens=4096,
    )
    elapsed = time.time() - start
    print(f"Response received in {elapsed:.2f} seconds!", flush=True)
    print("Parsed JSON Keys:", list(res.keys()), flush=True)
    clauses = res.get("clauses", [])
    print(f"Number of extracted clauses: {len(clauses)}", flush=True)
    for c in clauses:
        title = c.get("title")
        page = c.get("page_number")
        src = c.get("source_text", "")
        verified, matched_page = verify_source_text_presence(src, win0)
        print(f"- [{c.get('category')}] {title} (Page {page}, Verified: {verified}, Matched Page: {matched_page})")

if __name__ == "__main__":
    asyncio.run(test_llm_call())
