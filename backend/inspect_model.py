import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv("../.env")
load_dotenv(".env")

client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY"))

resp = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "Extract the key information in JSON with keys 'result' and 'number': Number is 42"}],
    temperature=1,
    max_tokens=1024
)

msg = resp.choices[0].message
print("message.content:", repr(msg.content))
print("reasoning_content:", repr(getattr(msg, "reasoning_content", None)))
