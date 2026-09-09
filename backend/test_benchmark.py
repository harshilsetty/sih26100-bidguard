import os
import time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv("../.env")
load_dotenv(".env")

client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY"), timeout=40.0)

text_excerpt = """
SECTION 1: STATUTORY & ELIGIBILITY CONDITIONS
1.1 Make in India (MII) Compliance: The bidder must provide a Class-I Local Supplier certificate showing minimum 50% local content.
1.2 Minimum Annual Turnover: The minimum average annual turnover of the bidder during the last 3 financial years must be at least INR 50,00,000 (Fifty Lakhs). Valid CA Certificate with UDIN is mandatory.
1.3 EMD Exemption: MSEs registered with Udyam are exempt from Earnest Money Deposit. Non-MSE bidders must submit EMD of INR 1,00,000.
"""

print(f"Testing extraction with text of length {len(text_excerpt)} chars...", flush=True)
t0 = time.time()
try:
    resp = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "user", "content": f"Extract all compliance criteria in JSON array with keys category, title, description, is_mandatory, rule_config, source_text, page_number:\n\n{text_excerpt}"}
        ],
        temperature=1,
        max_tokens=1024,
    )
    print(f"Completed in {time.time()-t0:.2f}s!", flush=True)
    content = resp.choices[0].message.content or ""
    safe_content = content.encode("ascii", errors="replace").decode("ascii")
    print("Content preview:\n", safe_content, flush=True)
except Exception as e:
    print(f"Failed in {time.time()-t0:.2f}s: {e}", flush=True)
