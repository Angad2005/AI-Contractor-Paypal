import json
import re
from typing import Any

import httpx

from app.core.config import settings


class LLMProviderError(RuntimeError):
    """Raised when a configured model cannot return a usable response."""


def is_configured() -> bool:
    provider = settings.llm_provider.strip().lower()
    if provider in {"demo", "deterministic", ""}:
        return False
    if provider in {"lm-studio", "lmstudio"}:
        # LM Studio's local server does not require a key unless API auth is enabled.
        return bool(settings.llm_model and settings.llm_base_url)
    return bool(settings.llm_api_key and settings.llm_model and settings.llm_base_url)


def is_demo_mode() -> bool:
    """Return whether the explicitly selected offline demo generator is active."""
    return settings.llm_provider.lower() in {"demo", "deterministic"}


def _clean_json_escapes(s: str) -> str:
    r"""Fix invalid backslash escapes in JSON string literals.

    In valid JSON, only \", \\, \/, \b, \f, \n, \r, \t, and \uXXXX are valid escapes.
    Code strings often contain raw escapes like \d, \s, \w, \., etc. which cause
    JSONDecodeError: Invalid \escape.
    """
    result = []
    i = 0
    n = len(s)
    valid_chars = set('"\\/bfnrt')
    hex_chars = set('0123456789abcdefABCDEF')
    while i < n:
        if s[i] == '\\':
            if i + 1 < n:
                nxt = s[i + 1]
                if nxt in valid_chars:
                    result.append(s[i:i+2])
                    i += 2
                    continue
                elif nxt == 'u' and i + 5 < n and all(c in hex_chars for c in s[i+2:i+6]):
                    result.append(s[i:i+6])
                    i += 6
                    continue
            result.append('\\\\')
            i += 1
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def _extract_json(content: str) -> dict[str, Any]:
    if not content:
        raise LLMProviderError("The model returned an empty response")
    cleaned = content.strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)

    # Attempt 1: Standard parsing with strict=False
    try:
        value = json.loads(cleaned, strict=False)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    # Attempt 2: Sanitize invalid backslash escapes and parse
    try:
        sanitized = _clean_json_escapes(cleaned)
        value = json.loads(sanitized, strict=False)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    # Attempt 3: Extract outer {...} block, both raw and sanitized
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        block = match.group(0)
        try:
            value = json.loads(block, strict=False)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
        try:
            value = json.loads(_clean_json_escapes(block), strict=False)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

    # Attempt 4: If JSON has code fields (index.html, style.css, script.js), extract via regex
    extracted = {}
    for key in ("index.html", "style.css", "script.js"):
        m = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, flags=re.S)
        if m:
            val = m.group(1)
            try:
                extracted[key] = json.loads(f'"{_clean_json_escapes(val)}"')
            except Exception:
                extracted[key] = val
    if set(extracted) == {"index.html", "style.css", "script.js"}:
        return extracted

    raise LLMProviderError("The model did not return valid JSON")


def _provider_error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""

    error = body.get("error", body) if isinstance(body, dict) else body
    if isinstance(error, dict):
        detail = error.get("message") or error.get("detail") or error.get("code")
    else:
        detail = error if isinstance(error, str) else None
    if not detail:
        return ""

    detail = str(detail).strip()
    if settings.llm_api_key:
        detail = detail.replace(settings.llm_api_key, "[redacted]")
    return detail[:500]


def complete_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    if not is_configured():
        raise LLMProviderError("No external LLM provider is configured")

    # Providers with fragile JSON-mode generation return text; JSON is validated locally.
    endpoint = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    provider = settings.llm_provider.strip().lower()
    response_format = (
        {"type": "text"}
        if provider in {"lm-studio", "lmstudio", "groq"}
        else {"type": "json_object"}
    )
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"

    # Determine primary model and fallback candidates
    primary_model = settings.llm_model
    models_to_try = [primary_model] if primary_model else []
    if provider in {"nvidia-nim", "nvidia"}:
        fallback = "nvidia/nemotron-3.5-bolt-e4b"
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    last_exc = None
    for model_name in models_to_try:
        for attempt in range(2):
            fmt = response_format if attempt == 0 else {"type": "text"}
            payload = {
                "model": model_name,
                "temperature": 0.2,
                "response_format": fmt,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            try:
                with httpx.Client(timeout=None) as client:
                    response = client.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = data["choices"][0]["message"].get("content") or ""
                    return _extract_json(content)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                # Retry on 400 (e.g. JSON schema mismatch), 500, 502, 503, 504, 404
                if (status in {500, 502, 503, 504, 404} or (status == 400 and attempt == 0)) and (attempt < 1 or model_name != models_to_try[-1]):
                    continue
                break
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                last_exc = exc
                if attempt < 1:
                    continue
                break

    if isinstance(last_exc, httpx.HTTPStatusError):
        status = last_exc.response.status_code
        if status in {401, 403}:
            hint = " Check the configured provider API key and model access."
        elif status == 404:
            hint = " Check the configured model ID and API base URL."
        elif status == 429:
            hint = " The provider rate limit or quota was reached."
        elif status == 504:
            hint = " The model timed out on the provider's server."
        else:
            hint = ""
        detail = _provider_error_detail(last_exc.response)
        provider_error = f" Provider error: {detail}" if detail else ""
        raise LLMProviderError(
            f"LLM provider returned HTTP {status}.{hint}{provider_error}"
        ) from last_exc
    raise LLMProviderError(f"LLM request failed: {last_exc}") from last_exc
