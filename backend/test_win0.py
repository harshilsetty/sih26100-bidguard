import os
import time
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv("../.env")
load_dotenv(".env")

from app.services.pdf_extractor import extract_pages_from_pdf
from app.services.clause_extractor import (
    build_page_windows,
    format_window_text,
    EXTRACTION_SYSTEM_PROMPT,
)

async def test_extraction():
    pages = extract_pages_from_pdf("sample_data/sample_gem_tender.pdf")
    windows = build_page_windows(pages, window_size=3, stride=2)
    win0 = windows[0]
    win_text = format_window_text(win0)

    client = AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=os.getenv("NVIDIA_API_KEY"),
        timeout=60.0
    )

    print("Sending Window 0 to NVIDIA NIM (timeout=60s)...")
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze these pages and extract clauses in JSON:\n\n{win_text}"}
            ],
            temperature=1,
            max_tokens=2048,
        )
        msg = resp.choices[0].message
        print(f"Success in {time.time()-t0:.2f}s!")
        print("Content:", repr(msg.content)[:500])
        print("Reasoning snippet:", repr(getattr(msg, "reasoning_content", ""))[:300])
    except Exception as e:
        print(f"Error after {time.time()-t0:.2f}s: {e}")

if __name__ == "__main__":
    asyncio.run(test_extraction())
