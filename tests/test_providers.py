from types import SimpleNamespace

from agentic_flow.providers import PROVIDER_CLIENT_HEADERS, ProviderRuntime


def test_openai_compatible_uses_agentic_flow_user_agent(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content="resposta compatível")
                            )
                        ]
                    )
                )
            )

    class FakeStore:
        provider = None

        def get_provider(self, provider_id, workspace_id, include_secret=False):
            assert provider_id == "prv-compatible"
            assert workspace_id == "ws-test"
            assert include_secret is True
            return self.provider

    store = FakeStore()
    runtime = ProviderRuntime(store, "segredo-de-teste")
    store.provider = {
        "id": "prv-compatible",
        "name": "Compatible",
        "type": "openai_compatible",
        "base_url": "https://provider.example/v1",
        "default_model": "model-test",
        "enabled": True,
        "api_key_encrypted": runtime.encrypt_key("secret-provider-key"),
    }
    monkeypatch.setattr("agentic_flow.providers.OpenAI", FakeOpenAI)

    result = runtime.chat(
        provider_id="prv-compatible",
        workspace_id="ws-test",
        model="",
        instructions="Seja breve.",
        prompt="Olá",
        temperature=0,
    )

    assert result == "resposta compatível"
    assert captured["base_url"] == "https://provider.example/v1"
    assert captured["default_headers"] == PROVIDER_CLIENT_HEADERS
    assert captured["default_headers"]["User-Agent"].startswith("AgenticFlow/")
