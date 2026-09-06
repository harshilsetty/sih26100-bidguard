import time
import json
import re
import logging
from typing import List, Dict, Any, Optional, Type
from pydantic import BaseModel
from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


class NvidiaClient:
    """Thin wrapper for NVIDIA NIM API (OpenAI-compatible) exposing chat, structured_completion, and health_check."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.NVIDIA_API_KEY
        self.base_url = base_url or settings.NVIDIA_BASE_URL
        self.model = model or settings.NVIDIA_MODEL

        self._client: Optional[AsyncOpenAI] = None
        if self.api_key:
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=90.0
            )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self._client)

    def _ensure_client(self) -> AsyncOpenAI:
        if not self._client:
            if not self.api_key:
                raise ValueError("NVIDIA_API_KEY is not configured in the environment.")
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=90.0
            )
        return self._client

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        max_tokens: int = 4096
    ) -> str:
        """Send chat messages to NVIDIA NIM LLM and return the assistant text response."""
        client = self._ensure_client()
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        msg = response.choices[0].message
        content = (msg.content or "").strip()
        if not content and hasattr(msg, "reasoning_content"):
            content = (getattr(msg, "reasoning_content") or "").strip()
        return content

    async def structured_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = "You are a precise JSON generator. Output only valid JSON.",
        temperature: float = 1.0,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """Request structured JSON completion from NVIDIA NIM LLM."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        raw_text = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        clean_text = raw_text.strip()
        # Strip markdown fences
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            # Try regex extraction of JSON object or array
            match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", clean_text)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, list):
                        return {"clauses": parsed}
                    return parsed
                except json.JSONDecodeError:
                    pass
            logger.warning(f"Failed to parse JSON response: {raw_text[:200]}")
            return {"raw_response": raw_text}

    async def health_check(self) -> Dict[str, Any]:
        """Test NVIDIA NIM API connectivity with a lightweight test ping."""
        if not self.is_configured:
            return {
                "status": "UNCONFIGURED",
                "model": self.model,
                "base_url": self.base_url,
                "message": "NVIDIA_API_KEY is missing from environment.",
                "latency_ms": None,
                "response_sample": None,
            }

        start_time = time.perf_counter()
        try:
            client = self._ensure_client()
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Respond with 'OK' only."}],
                max_tokens=10,
                temperature=0.0,
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            content = (response.choices[0].message.content or "").strip()
            return {
                "status": "HEALTHY",
                "model": self.model,
                "base_url": self.base_url,
                "message": "Successfully connected to NVIDIA NIM API.",
                "latency_ms": elapsed_ms,
                "response_sample": content,
            }
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "status": "ERROR",
                "model": self.model,
                "base_url": self.base_url,
                "message": f"NVIDIA NIM connection failed: {str(e)}",
                "latency_ms": elapsed_ms,
                "response_sample": None,
            }


# Shared singleton client instance
nvidia_client = NvidiaClient()


def get_nvidia_client() -> NvidiaClient:
    return nvidia_client
