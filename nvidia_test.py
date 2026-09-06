import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("NVIDIA_API_KEY")

if not api_key:
    raise RuntimeError("NVIDIA_API_KEY is missing")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

completion = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[
        {
            "role": "user",
            "content": "Which number is larger, 9.11 or 9.8?"
        }
    ],
    temperature=1,
    top_p=1,
    max_tokens=4096,
    stream=False
)

reasoning = getattr(
    completion.choices[0].message,
    "reasoning_content",
    None
)

if reasoning:
    print("Reasoning:")
    print(reasoning)

print("\nAnswer:")
print(completion.choices[0].message.content)