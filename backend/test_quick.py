import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.services.pdf_extractor import extract_pages_from_pdf
from app.services.clause_extractor import build_page_windows, format_window_text
from app.services.nvidia_client import get_nvidia_client

pages = extract_pages_from_pdf("sample_data/sample_gem_tender.pdf")
print(f"Extracted {len(pages)} pages.")

windows = build_page_windows(pages, window_size=3, stride=2)
print(f"Created {len(windows)} windows:")
for i, w in enumerate(windows):
    p_nums = [p["page_number"] for p in w]
    print(f"  Window {i}: Pages {p_nums}")

# Test formatted text of window 0
w0_text = format_window_text(windows[0])
print("\nSample Formatted Window 0 (first 200 chars):")
print(w0_text[:200])

client = get_nvidia_client()
print("\nNVIDIA NIM Configured:", client.is_configured, "Model:", client.model)
