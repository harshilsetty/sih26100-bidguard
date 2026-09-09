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
                timeout=90.0,
                max_retries=0,
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
                timeout=120.0,
                max_retries=0,
            )
        return self._client

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        max_tokens: int = 4096,
        timeout: Optional[float] = None,
    ) -> str:
        """Send chat messages to NVIDIA NIM LLM and return the assistant text response."""
        client = self._ensure_client()
        call_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if timeout is not None:
            call_kwargs["timeout"] = timeout

        response = await client.chat.completions.create(**call_kwargs)
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
        max_tokens: int = 4096,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Request structured JSON completion from NVIDIA NIM LLM."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        raw_text = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

        clean_text = raw_text.strip()

        # 1. Search for fenced code blocks ```json ... ``` or ``` ... ``` anywhere in response
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text, re.IGNORECASE)
        if fence_match:
            candidate = fence_match.group(1).strip()
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, list):
                    return {"clauses": parsed}
                return parsed
            except json.JSONDecodeError:
                pass

        # 2. Try direct JSON parsing
        try:
            parsed = json.loads(clean_text)
            if isinstance(parsed, list):
                return {"clauses": parsed}
            return parsed
        except json.JSONDecodeError:
            pass

        # 3. Fallback: non-greedy or anchored JSON object / array search
        for pattern in [r"(\{\s*\"clauses\"[\s\S]*\})", r"(\{[\s\S]*\})", r"(\[[\s\S]*\])"]:
            match = re.search(pattern, clean_text)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    if isinstance(parsed, list):
                        return {"clauses": parsed}
                    return parsed
                except json.JSONDecodeError:
                    continue

        # 4. Truncation recovery: rescue completed clause objects if response was cut off
        clause_pattern = r'\{\s*"category"\s*:[\s\S]*?"page_number"\s*:\s*\d+\s*\}'
        found_clauses = re.findall(clause_pattern, clean_text)
        if found_clauses:
            recovered = []
            for item_str in found_clauses:
                try:
                    recovered.append(json.loads(item_str))
                except Exception:
                    pass
            if recovered:
                logger.info(f"Rescued {len(recovered)} completed clauses from truncated LLM response.")
                return {"clauses": recovered}

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
