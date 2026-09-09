import os
import time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv("../.env")
load_dotenv(".env")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY"),
    timeout=30.0
)

# Test 1: With System Prompt
print("--- Test 1: With System Prompt ---")
t0 = time.time()
try:
    resp1 = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Always respond in JSON."},
            {"role": "user", "content": "Return JSON with key 'status' and value 'ok'."}
        ],
        temperature=1,
        max_tokens=512,
    )
    print(f"Test 1 succeeded in {time.time()-t0:.2f}s: {resp1.choices[0].message.content}")
except Exception as e:
    print(f"Test 1 failed in {time.time()-t0:.2f}s: {e}")

# Test 2: User-Only Prompt
print("\n--- Test 2: User-Only Prompt ---")
t0 = time.time()
try:
    resp2 = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "user", "content": "You are a helpful assistant. Always respond in JSON.\n\nReturn JSON with key 'status' and value 'ok'."}
        ],
        temperature=1,
        max_tokens=512,
    )
    print(f"Test 2 succeeded in {time.time()-t0:.2f}s: {resp2.choices[0].message.content}")
except Exception as e:
    print(f"Test 2 failed in {time.time()-t0:.2f}s: {e}")
