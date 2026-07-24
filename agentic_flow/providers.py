from __future__ import annotations

import base64
import hashlib
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI


PROVIDER_CLIENT_HEADERS = {
    "User-Agent": "AgenticFlow/0.2.0 (+https://github.com/wanbnn/agenticflow)",
    "Accept": "application/json",
}


PROVIDER_TYPES: list[dict[str, Any]] = [
    {
        "type": "openai",
        "name": "OpenAI",
        "protocol": "openai",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4.1-mini",
        "requires_key": True,
        "description": "API oficial da OpenAI.",
    },
    {
        "type": "anthropic",
        "name": "Anthropic",
        "protocol": "anthropic",
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-5",
        "requires_key": True,
        "description": "API oficial para modelos Claude.",
    },
    {
        "type": "openai_compatible",
        "name": "OpenAI Compatible",
        "protocol": "openai",
        "base_url": "",
        "default_model": "",
        "requires_key": True,
        "description": "Qualquer servidor compatível com Chat Completions /v1.",
    },
    {
        "type": "anthropic_compatible",
        "name": "Anthropic Compatible",
        "protocol": "anthropic",
        "base_url": "",
        "default_model": "",
        "requires_key": True,
        "description": "Servidor compatível com a API Messages da Anthropic.",
    },
    {
        "type": "ollama",
        "name": "Ollama",
        "protocol": "openai",
        "base_url": "http://host.docker.internal:11434/v1",
        "default_model": "llama3.2",
        "requires_key": False,
        "description": "Modelos locais pelo endpoint compatível do Ollama.",
    },
    {
        "type": "groq",
        "name": "Groq",
        "protocol": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "requires_key": True,
        "description": "Inferência rápida usando API compatível com OpenAI.",
    },
    {
        "type": "openrouter",
        "name": "OpenRouter",
        "protocol": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4.1-mini",
        "requires_key": True,
        "description": "Catálogo unificado de modelos via OpenAI-compatible.",
    },
    {
        "type": "gemini",
        "name": "Google Gemini",
        "protocol": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.5-flash",
        "requires_key": True,
        "description": "Gemini pelo endpoint de compatibilidade OpenAI.",
    },
    {
        "type": "mistral",
        "name": "Mistral AI",
        "protocol": "openai",
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest",
        "requires_key": True,
        "description": "Modelos Mistral via API compatível.",
    },
]

PROVIDER_TYPE_MAP = {item["type"]: item for item in PROVIDER_TYPES}


class CredentialCipher:
    def __init__(self, secret: str):
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        if not value:
            return ""
        return self.fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value:
            return ""
        try:
            return self.fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError(
                "Não foi possível descriptografar a credencial. Verifique o SESSION_SECRET."
            ) from exc


class ProviderRuntime:
    def __init__(self, store, encryption_secret: str):
        self.store = store
        self.cipher = CredentialCipher(encryption_secret)

    def encrypt_key(self, api_key: str) -> str:
        return self.cipher.encrypt(api_key)

    def chat(
        self,
        *,
        provider_id: str,
        workspace_id: str,
        model: str,
        instructions: str,
        prompt: str,
        temperature: float,
    ) -> str:
        provider = self.store.get_provider(provider_id, workspace_id, include_secret=True)
        if not provider or not provider["enabled"]:
            raise RuntimeError("O provedor selecionado não existe ou está desativado.")
        definition = PROVIDER_TYPE_MAP.get(provider["type"])
        if not definition:
            raise RuntimeError(f"Tipo de provedor desconhecido: {provider['type']}")
        api_key = self.cipher.decrypt(provider.get("api_key_encrypted", ""))
        if definition["requires_key"] and not api_key:
            raise RuntimeError(f"O provedor “{provider['name']}” não possui uma API key.")
        selected_model = model or provider["default_model"]
        if not selected_model:
            raise RuntimeError("Informe um modelo no nó ou no provedor.")

        if definition["protocol"] == "anthropic":
            base_url = provider["base_url"].rstrip("/")
            with httpx.Client(timeout=90) as client:
                response = client.post(
                    f"{base_url}/v1/messages",
                    headers={
                        **PROVIDER_CLIENT_HEADERS,
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": selected_model,
                        "max_tokens": 4096,
                        "temperature": temperature,
                        "system": instructions,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                response.raise_for_status()
                payload = response.json()
                return "".join(
                    block.get("text", "")
                    for block in payload.get("content", [])
                    if block.get("type") == "text"
                )

        client = OpenAI(
            api_key=api_key or "ollama",
            base_url=provider["base_url"].rstrip("/"),
            default_headers=PROVIDER_CLIENT_HEADERS,
        )
        try:
            response = client.chat.completions.create(
                model=selected_model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
            )
        except APIStatusError as exc:
            request_id = getattr(exc, "request_id", None)
            suffix = f" Request ID: {request_id}." if request_id else ""
            if exc.status_code == 403:
                raise RuntimeError(
                    "O provedor ou WAF recusou a requisição (HTTP 403)."
                    f"{suffix} Revise as regras de firewall/bot do endpoint."
                ) from exc
            raise RuntimeError(
                f"O provedor respondeu com HTTP {exc.status_code}.{suffix}"
            ) from exc
        except APITimeoutError as exc:
            raise RuntimeError("O provedor excedeu o tempo limite da requisição.") from exc
        except APIConnectionError as exc:
            raise RuntimeError(
                "Não foi possível conectar ao provedor. Verifique URL, DNS e TLS."
            ) from exc
        return response.choices[0].message.content or ""
