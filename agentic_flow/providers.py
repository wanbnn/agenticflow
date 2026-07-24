from __future__ import annotations

import base64
import hashlib
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken


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
    def __init__(self, store, encryption_secret: str, http_transport=None):
        self.store = store
        self.cipher = CredentialCipher(encryption_secret)
        self.http_transport = http_transport

    def encrypt_key(self, api_key: str) -> str:
        return self.cipher.encrypt(api_key)

    @staticmethod
    def _raise_provider_error(response: httpx.Response, api_key: str) -> None:
        if response.is_success:
            return
        detail = ""
        try:
            payload = response.json()
            error = payload.get("error", payload) if isinstance(payload, dict) else payload
            if isinstance(error, dict):
                detail = str(
                    error.get("message")
                    or error.get("detail")
                    or error.get("error")
                    or ""
                )
            elif error:
                detail = str(error)
        except ValueError:
            detail = response.text.strip()
        if api_key and detail:
            detail = detail.replace(api_key, "[credencial removida]")
        detail = " ".join(detail.split())[:300]
        suffix = f" Detalhe: {detail}" if detail else ""
        if response.status_code == 419:
            raise RuntimeError(
                "O endpoint recusou a chamada com HTTP 419, geralmente causado por "
                f"CSRF, sessão ou WAF aplicado incorretamente à rota de API.{suffix}"
            )
        if response.status_code == 403:
            raise RuntimeError(
                f"O provedor ou WAF recusou a requisição (HTTP 403).{suffix}"
            )
        raise RuntimeError(
            f"O provedor respondeu com HTTP {response.status_code}.{suffix}"
        )

    def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        try:
            with httpx.Client(
                timeout=90,
                follow_redirects=True,
                transport=self.http_transport,
            ) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise RuntimeError("O provedor excedeu o tempo limite da requisição.") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(
                "Não foi possível conectar ao provedor. Verifique URL, DNS e TLS."
            ) from exc
        self._raise_provider_error(response, api_key)
        try:
            result = response.json()
        except ValueError as exc:
            raise RuntimeError("O provedor retornou uma resposta que não é JSON.") from exc
        if not isinstance(result, dict):
            raise RuntimeError("O provedor retornou um JSON em formato inesperado.")
        return result

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
            payload = self._post_json(
                f"{base_url}/v1/messages",
                headers={
                    **PROVIDER_CLIENT_HEADERS,
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                payload={
                    "model": selected_model,
                    "max_tokens": 4096,
                    "temperature": temperature,
                    "system": instructions,
                    "messages": [{"role": "user", "content": prompt}],
                },
                api_key=api_key,
            )
            return "".join(
                block.get("text", "")
                for block in payload.get("content", [])
                if block.get("type") == "text"
            )

        base_url = provider["base_url"].rstrip("/")
        payload = self._post_json(
            f"{base_url}/chat/completions",
            headers={
                **PROVIDER_CLIENT_HEADERS,
                "Authorization": f"Bearer {api_key or 'ollama'}",
                "Content-Type": "application/json",
            },
            payload={
                "model": selected_model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "stream": False,
            },
            api_key=api_key,
        )
        try:
            return payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "O provedor retornou JSON sem choices[0].message.content."
            ) from exc
