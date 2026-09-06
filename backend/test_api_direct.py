import os
import time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv("../.env")
load_dotenv(".env")

api_key = os.getenv("NVIDIA_API_KEY")
print(f"API Key present: {bool(api_key)}")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key,
    timeout=60.0
)

print("Testing simple call to openai/gpt-oss-20b...")
t0 = time.time()
try:
    completion = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": "Extract criteria from: Minimum turnover must be 50 Lakhs. Return JSON: {\"turnover\": 5000000}"}],
        temperature=1,
        max_tokens=1024,
    )
    print(f"Success in {time.time()-t0:.2f}s!")
    print("Content:", completion.choices[0].message.content)
except Exception as e:
    print(f"Error after {time.time()-t0:.2f}s: {e}")
