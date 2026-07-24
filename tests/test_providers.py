import httpx
import pytest

from agentic_flow.providers import PROVIDER_CLIENT_HEADERS, ProviderRuntime


class FakeStore:
    provider = None

    def get_provider(self, provider_id, workspace_id, include_secret=False):
        assert provider_id == "prv-compatible"
        assert workspace_id == "ws-test"
        assert include_secret is True
        return self.provider


def configured_runtime(handler):
    store = FakeStore()
    runtime = ProviderRuntime(
        store,
        "segredo-de-teste",
        http_transport=httpx.MockTransport(handler),
    )
    store.provider = {
        "id": "prv-compatible",
        "name": "Compatible",
        "type": "openai_compatible",
        "base_url": "https://provider.example/v1",
        "default_model": "model-test",
        "enabled": True,
        "api_key_encrypted": runtime.encrypt_key("secret-provider-key"),
    }
    return runtime


def test_openai_compatible_uses_minimal_postman_like_transport():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "resposta compatível"}}]},
            request=request,
        )

    runtime = configured_runtime(handler)
    result = runtime.chat(
        provider_id="prv-compatible",
        workspace_id="ws-test",
        model="",
        instructions="Seja breve.",
        prompt="Olá",
        temperature=0,
    )

    assert result == "resposta compatível"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://provider.example/v1/chat/completions"
    assert captured["headers"]["user-agent"] == PROVIDER_CLIENT_HEADERS["User-Agent"]
    assert captured["headers"]["authorization"] == "Bearer secret-provider-key"
    assert not any(name.startswith("x-stainless-") for name in captured["headers"])
    assert captured["payload"] == {
        "model": "model-test",
        "messages": [
            {"role": "system", "content": "Seja breve."},
            {"role": "user", "content": "Olá"},
        ],
        "temperature": 0,
        "stream": False,
    }


def test_provider_419_error_is_diagnostic_and_does_not_expose_key():
    def handler(request):
        return httpx.Response(
            419,
            text="Page Expired: secret-provider-key",
            request=request,
        )

    runtime = configured_runtime(handler)
    with pytest.raises(RuntimeError) as error:
        runtime.chat(
            provider_id="prv-compatible",
            workspace_id="ws-test",
            model="",
            instructions="Teste",
            prompt="Teste",
            temperature=0,
        )

    message = str(error.value)
    assert "HTTP 419" in message
    assert "CSRF" in message
    assert "secret-provider-key" not in message
