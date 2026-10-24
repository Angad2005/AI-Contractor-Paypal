import json

import httpx
import pytest

from app.core.config import settings
from app.services import llm_provider


@pytest.mark.parametrize(
    ("provider", "api_key", "expected_format"),
    [
        ("lm-studio", "", {"type": "text"}),
        ("groq", "test-api-key", {"type": "text"}),
        ("nvidia-nim", "test-api-key", {"type": "json_object"}),
    ],
)
def test_complete_json_uses_provider_compatible_response_format(
    monkeypatch, provider, api_key, expected_format
):
    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(settings, "llm_api_key", api_key)
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_base_url", "https://provider.example/v1")

    request_data = {}
    client_options = {}

    def respond(request):
        request_data["headers"] = request.headers
        request_data["json"] = request.read()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )

    transport = httpx.MockTransport(respond)
    original_client = httpx.Client

    def make_client(**kwargs):
        client_options.update(kwargs)
        return original_client(transport=transport, **kwargs)

    monkeypatch.setattr(
        llm_provider.httpx,
        "Client",
        make_client,
    )

    assert llm_provider.complete_json("system", "user") == {"ok": True}

    assert client_options["timeout"] is None
    payload = json.loads(request_data["json"])
    assert payload["response_format"] == expected_format
    if api_key:
        assert request_data["headers"]["authorization"] == f"Bearer {api_key}"
    else:
        assert "authorization" not in request_data["headers"]


def test_complete_json_includes_provider_error_without_leaking_api_key(monkeypatch):
    api_key = "test-api-secret"
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "llm_api_key", api_key)
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_base_url", "https://provider.example/v1")

    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            400,
            json={"error": {"message": f"Unsupported model; {api_key}"}},
        )
    )
    original_client = httpx.Client
    monkeypatch.setattr(
        llm_provider.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    with pytest.raises(llm_provider.LLMProviderError) as error:
        llm_provider.complete_json("system", "user")

    assert "HTTP 400" in str(error.value)
    assert "Unsupported model" in str(error.value)
    assert api_key not in str(error.value)
    assert "[redacted]" in str(error.value)


def test_extract_json_handles_invalid_backslash_escapes():
    # LLMs frequently generate code with regex like /\d+/ or /\s+/ inside JSON strings
    malformed_json = r'''{
        "index.html": "<div class=\"hero\"><h1>Test</h1></div>",
        "style.css": ".hero { background: url(\'bg.jpg\'); }",
        "script.js": "const regex = /\d+/; const spaces = /\s+/; const words = /\w+/; console.log(\"done\");"
    }'''

    result = llm_provider._extract_json(malformed_json)
    assert isinstance(result, dict)
    assert result["index.html"] == '<div class="hero"><h1>Test</h1></div>'
    assert r"/\d+/" in result["script.js"]
    assert r"/\s+/" in result["script.js"]
