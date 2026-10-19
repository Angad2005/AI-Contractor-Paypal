import json
import re
from typing import Any

import httpx

from app.core.config import settings


class LLMProviderError(RuntimeError):
    """Raised when a configured model cannot return a usable response."""


def is_configured() -> bool:
    return settings.llm_provider.lower() not in {"demo", "deterministic", ""} and bool(
        settings.llm_api_key
    )


def _extract_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise LLMProviderError("The model did not return valid JSON") from exc
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise LLMProviderError("The model response must be a JSON object")
    return value


def complete_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    if not is_configured():
        raise LLMProviderError("No external LLM provider is configured")

    endpoint = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.llm_model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return _extract_json(content)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMProviderError(f"LLM request failed: {exc}") from exc
