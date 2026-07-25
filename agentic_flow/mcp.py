from __future__ import annotations

import json
import re
from typing import Any

import httpx


class MCPRuntime:
    def __init__(self, http_transport=None):
        self.http_transport = http_transport

    @staticmethod
    def _headers(
        config: dict[str, Any],
        session_id: str = "",
        protocol_version: str = "",
    ) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        token = str(config.get("auth_token") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        if protocol_version:
            headers["MCP-Protocol-Version"] = protocol_version
        return headers

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for line in reversed(response.text.splitlines()):
                if line.startswith("data:"):
                    value = json.loads(line[5:].strip())
                    if isinstance(value, dict):
                        return value
            raise RuntimeError("O MCP Server não retornou um evento JSON válido.")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("O MCP Server retornou um formato inválido.")
        return payload

    def _post(
        self,
        client: httpx.Client,
        config: dict[str, Any],
        method: str,
        params: dict[str, Any] | None,
        request_id: int | None,
        session_id: str = "",
        protocol_version: str = "",
    ) -> tuple[dict[str, Any], str]:
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if request_id is not None:
            body["id"] = request_id
        if params is not None:
            body["params"] = params
        response = client.post(
            str(config.get("url") or ""),
            headers=self._headers(config, session_id, protocol_version),
            json=body,
        )
        next_session = response.headers.get("mcp-session-id", session_id)
        if request_id is None:
            response.raise_for_status()
            return {}, next_session
        payload = self._payload(response)
        if payload.get("error"):
            message = payload["error"].get("message", "Erro desconhecido")
            raise RuntimeError(f"MCP Server: {message}")
        return dict(payload.get("result") or {}), next_session

    def _session(self, config: dict[str, Any]):
        url = str(config.get("url") or "")
        if not url.startswith(("http://", "https://")):
            raise ValueError("A URL do MCP Server precisa usar http:// ou https://.")
        timeout = max(1.0, min(float(config.get("timeout", 30)), 120.0))
        client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=self.http_transport,
        )
        initialize, session_id = self._post(
            client,
            config,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "Agentic Flow", "version": "0.2.0"},
            },
            1,
        )
        protocol_version = str(
            initialize.get("protocolVersion") or "2025-11-25"
        )
        self._post(
            client,
            config,
            "notifications/initialized",
            None,
            None,
            session_id,
            protocol_version,
        )
        return client, session_id, protocol_version, initialize

    def list_tools(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        client, session_id, protocol_version, _ = self._session(config)
        try:
            result, _ = self._post(
                client,
                config,
                "tools/list",
                {},
                2,
                session_id,
                protocol_version,
            )
            return list(result.get("tools") or [])
        finally:
            client.close()

    @staticmethod
    def choose_tool(
        tools: list[dict[str, Any]], query: str, configured_name: str = ""
    ) -> dict[str, Any] | None:
        if configured_name:
            return next(
                (tool for tool in tools if tool.get("name") == configured_name),
                None,
            )
        if len(tools) == 1:
            return tools[0]
        query_words = set(re.findall(r"[\wÀ-ÿ]+", query.lower()))
        ranked = []
        for tool in tools:
            description = f"{tool.get('name', '')} {tool.get('description', '')}"
            words = set(re.findall(r"[\wÀ-ÿ]+", description.lower()))
            ranked.append((len(query_words & words), tool))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1] if ranked and ranked[0][0] else None

    @staticmethod
    def arguments_for(
        tool: dict[str, Any],
        query: str,
        configured_arguments: Any,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(configured_arguments, str) and configured_arguments.strip():
            rendered = configured_arguments
            for key, value in data.items():
                rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
            rendered = rendered.replace("{{query}}", query)
            parsed = json.loads(rendered)
            if not isinstance(parsed, dict):
                raise ValueError("Os argumentos MCP precisam ser um objeto JSON.")
            return parsed
        if isinstance(configured_arguments, dict):
            return dict(configured_arguments)
        schema = tool.get("inputSchema") or {}
        properties = schema.get("properties") or {}
        preferred = ("query", "prompt", "message", "text", "input")
        field = next((name for name in preferred if name in properties), None)
        if not field:
            required = schema.get("required") or []
            field = required[0] if required else None
        return {field: query} if field else {}

    def call_for_agent(
        self, config: dict[str, Any], query: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        client, session_id, protocol_version, _ = self._session(config)
        try:
            listed, session_id = self._post(
                client,
                config,
                "tools/list",
                {},
                2,
                session_id,
                protocol_version,
            )
            tools = list(listed.get("tools") or [])
            tool = self.choose_tool(
                tools, query, str(config.get("tool_name") or "")
            )
            if not tool:
                return None
            arguments = self.arguments_for(
                tool,
                query,
                config.get("arguments"),
                data,
            )
            result, _ = self._post(
                client,
                config,
                "tools/call",
                {"name": tool["name"], "arguments": arguments},
                3,
                session_id,
                protocol_version,
            )
            return {
                "server": config.get("name") or config.get("_node_name"),
                "tool": tool["name"],
                "arguments": arguments,
                "result": result,
            }
        finally:
            client.close()
