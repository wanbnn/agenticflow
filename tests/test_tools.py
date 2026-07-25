import json

import httpx
import pytest

from agentic_flow.engine import (
    WorkflowEngine,
    WorkflowValidationError,
    validate_workflow,
)
from agentic_flow.mcp import MCPRuntime
from agentic_flow.models import Edge, Node, RunRequest, Workflow


def test_rag_and_mcp_are_attached_to_agent_as_passive_tools():
    class FakeVectorStore:
        def search_vectors(self, **kwargs):
            assert kwargs["node_id"] == "knowledge"
            return [
                {
                    "id": "chunk-1",
                    "content": "O plano Enterprise possui SLA de 99,9%.",
                    "score": 0.91,
                    "metadata": {},
                }
            ]

    class FakeMCP:
        def call_for_agent(self, config, query, data):
            assert config["url"] == "https://tools.example.com/mcp"
            return {
                "server": "CRM",
                "tool": "find_customer",
                "arguments": {"query": query},
                "result": {"name": "Ada"},
            }

        def list_tools(self, config):
            raise AssertionError("O MCP passivo não deve executar sozinho")

    workflow = Workflow(
        name="Agente com tools",
        nodes=[
            Node(id="input", type="input", name="Entrada"),
            Node(id="knowledge", type="vector_database", name="Conhecimento"),
            Node(id="rag", type="rag", name="Consultar conhecimento"),
            Node(
                id="mcp",
                type="mcp_server",
                name="CRM",
                config={"url": "https://tools.example.com/mcp"},
            ),
            Node(
                id="agent",
                type="agent",
                name="Atendente",
                config={
                    "role": "Atendente",
                    "provider_id": "mock",
                    "input_field": "message",
                    "output_field": "response",
                },
            ),
            Node(
                id="output",
                type="output",
                name="Saída",
                config={"field": "response"},
            ),
        ],
        edges=[
            Edge(
                source="knowledge",
                source_handle="database",
                target="rag",
                target_handle="database",
            ),
            Edge(
                source="rag",
                source_handle="tool",
                target="agent",
                target_handle="tools",
            ),
            Edge(
                source="mcp",
                source_handle="tool",
                target="agent",
                target_handle="tools",
            ),
            Edge(source="input", target="agent"),
            Edge(source="agent", target="output"),
        ],
    )
    result = WorkflowEngine(
        vector_store=FakeVectorStore(), mcp_runtime=FakeMCP()
    ).run(workflow, RunRequest(input={"message": "Consulte o SLA e a cliente Ada"}))

    assert result.status == "success"
    assert [event.node_id for event in result.events] == [
        "input",
        "agent",
        "output",
    ]
    assert "SLA de 99,9%" in result.output
    assert "find_customer" in result.output


def test_incompatible_typed_handles_are_rejected():
    workflow = Workflow(
        name="Portas inválidas",
        nodes=[
            Node(id="mcp", type="mcp_server", name="MCP"),
            Node(id="output", type="output", name="Saída"),
        ],
        edges=[
            Edge(
                source="mcp",
                source_handle="tool",
                target="output",
                target_handle="input",
            )
        ],
    )
    with pytest.raises(WorkflowValidationError, match="incompatíveis"):
        validate_workflow(workflow)


def test_streamable_http_mcp_lists_and_calls_a_tool():
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        methods.append(payload["method"])
        headers = {"mcp-session-id": "session-1"}
        if payload["method"] == "initialize":
            return httpx.Response(
                200,
                headers=headers,
                json={"jsonrpc": "2.0", "id": 1, "result": {}},
            )
        assert request.headers["mcp-session-id"] == "session-1"
        assert request.headers["mcp-protocol-version"] == "2025-11-25"
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202, headers=headers)
        if payload["method"] == "tools/list":
            return httpx.Response(
                200,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {
                                "name": "search",
                                "description": "Pesquisa registros",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"query": {"type": "string"}},
                                    "required": ["query"],
                                },
                            }
                        ]
                    },
                },
            )
        return httpx.Response(
            200,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "result": {"content": [{"type": "text", "text": "encontrado"}]},
            },
        )

    runtime = MCPRuntime(httpx.MockTransport(handler))
    result = runtime.call_for_agent(
        {"url": "https://mcp.example.com", "timeout": 5},
        "cliente Ada",
        {},
    )
    assert result["tool"] == "search"
    assert result["arguments"] == {"query": "cliente Ada"}
    assert result["result"]["content"][0]["text"] == "encontrado"
    assert methods == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]
