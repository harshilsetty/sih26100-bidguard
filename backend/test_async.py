import os
import time
import asyncio
from dotenv import load_dotenv
from openai import OpenAI, AsyncOpenAI

load_dotenv("../.env")
load_dotenv(".env")

api_key = os.getenv("NVIDIA_API_KEY")

async def test_async():
    print("Testing AsyncOpenAI...")
    t0 = time.time()
    client = AsyncOpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key, timeout=30.0)
    try:
        resp = await client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": "Return JSON: {\"async\": true}"}],
            temperature=1,
            max_tokens=256,
        )
        print(f"AsyncOpenAI succeeded in {time.time()-t0:.2f}s: {resp.choices[0].message.content}")
    except Exception as e:
        print(f"AsyncOpenAI failed in {time.time()-t0:.2f}s: {e}")

if __name__ == "__main__":
    asyncio.run(test_async())
