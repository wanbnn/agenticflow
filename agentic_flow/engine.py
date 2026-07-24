from __future__ import annotations

import json
import operator
import re
import time
from collections import defaultdict, deque
from typing import Annotated, Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from .catalog import CATALOG_BY_TYPE
from .models import Node, RunEvent, RunRequest, RunResult, Workflow, utc_now


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**left, **right}


class FlowState(TypedDict):
    data: Annotated[dict[str, Any], merge_dicts]
    results: Annotated[dict[str, Any], merge_dicts]
    events: Annotated[list[dict[str, Any]], operator.add]
    output: Annotated[dict[str, Any], merge_dicts]
    session_id: str
    workspace_id: str


class WorkflowValidationError(ValueError):
    pass


TOKEN = re.compile(r"\{\{\s*([\w.-]+)\s*\}\}")


def lookup(data: dict[str, Any], path: str, default: Any = "") -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def render_template(template: str, data: dict[str, Any]) -> str:
    return TOKEN.sub(lambda match: str(lookup(data, match.group(1), "")), template)


def validate_workflow(workflow: Workflow) -> None:
    if not workflow.nodes:
        raise WorkflowValidationError("Adicione pelo menos um nó ao workflow.")
    ids = [node.id for node in workflow.nodes]
    if len(ids) != len(set(ids)):
        raise WorkflowValidationError("Existem nós com IDs duplicados.")
    known = set(ids)
    for node in workflow.nodes:
        if node.type not in CATALOG_BY_TYPE:
            raise WorkflowValidationError(f"Tipo de nó desconhecido: {node.type}")
    for edge in workflow.edges:
        if edge.source not in known or edge.target not in known:
            raise WorkflowValidationError(f"Conexão {edge.id} referencia um nó inexistente.")
        if edge.source == edge.target:
            raise WorkflowValidationError("Um nó não pode conectar a si mesmo.")
    outgoing_handles: dict[str, set[str]] = defaultdict(set)
    for edge in workflow.edges:
        outgoing_handles[edge.source].add(edge.source_handle)
    for node in workflow.nodes:
        if node.type == "condition" and outgoing_handles[node.id]:
            handles = outgoing_handles[node.id]
            if not {"true", "false"}.issubset(handles):
                raise WorkflowValidationError(
                    f"A condição “{node.name}” precisa das saídas true e false."
                )

    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {node_id: 0 for node_id in ids}
    for edge in workflow.edges:
        adjacency[edge.source].append(edge.target)
        indegree[edge.target] += 1
    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if visited != len(ids):
        raise WorkflowValidationError("O workflow contém um ciclo. Use apenas fluxos acíclicos.")


class WorkflowEngine:
    def __init__(self, provider_runtime=None):
        self.provider_runtime = provider_runtime

    def _call_model(
        self,
        *,
        prompt: str,
        config: dict[str, Any],
        instructions: str,
        mock_prefix: str,
        workspace_id: str,
    ) -> str:
        provider_id = config.get("provider_id") or config.get("provider", "mock")
        if provider_id == "mock":
            return f"{mock_prefix}: {prompt[:500]}"
        if not self.provider_runtime:
            raise RuntimeError("O gerenciamento visual de provedores não está configurado.")
        return self.provider_runtime.chat(
            provider_id=provider_id,
            workspace_id=workspace_id,
            model=config.get("model", ""),
            instructions=instructions,
            prompt=prompt,
            temperature=float(config.get("temperature", 0.2)),
        )

    def _execute_node(self, node: Node, state: FlowState) -> dict[str, Any]:
        started = time.perf_counter()
        data = dict(state.get("data", {}))
        config = node.config
        result: Any = None

        try:
            if node.type == "input":
                result = data
            elif node.type == "webhook":
                result = data
                data["_trigger"] = {
                    "type": "webhook",
                    "node_id": node.id,
                    "webhook_id": config.get("webhook_id"),
                }
            elif node.type == "prompt":
                result = render_template(config.get("template", "{{message}}"), data)
                data["prompt"] = result
            elif node.type == "transform":
                target = config.get("target", "result")
                result = render_template(config.get("template", "{{message}}"), data)
                data[target] = result
            elif node.type == "condition":
                actual = lookup(data, config.get("field", ""))
                expected = config.get("value")
                op = config.get("operator", "equals")
                if isinstance(expected, str):
                    if expected.lower() == "true":
                        expected = True
                    elif expected.lower() == "false":
                        expected = False
                comparisons = {
                    "equals": lambda: str(actual).lower() == str(expected).lower(),
                    "not_equals": lambda: str(actual).lower() != str(expected).lower(),
                    "contains": lambda: str(expected).lower() in str(actual).lower(),
                    "gt": lambda: float(actual) > float(expected),
                    "gte": lambda: float(actual) >= float(expected),
                    "lt": lambda: float(actual) < float(expected),
                    "lte": lambda: float(actual) <= float(expected),
                    "exists": lambda: actual not in (None, ""),
                }
                result = bool(comparisons.get(op, comparisons["equals"])())
                data[f"_condition_{node.id}"] = result
            elif node.type == "llm":
                prompt = str(data.get("prompt") or data.get("message") or json.dumps(data))
                result = self._call_model(
                    prompt=prompt,
                    config=config,
                    instructions=config.get("system_prompt", "Seja útil."),
                    mock_prefix="Resposta simulada do agente",
                    workspace_id=state.get("workspace_id", ""),
                )
                data["response"] = result
            elif node.type == "agent":
                role = config.get("role", node.name)
                input_field = config.get("input_field", "prompt")
                output_field = config.get("output_field", "response")
                prompt = str(
                    lookup(
                        data,
                        input_field,
                        data.get("prompt") or data.get("response") or data.get("message") or json.dumps(data),
                    )
                )
                instructions = render_template(
                    config.get("system_prompt", "Atue como {{role}}."),
                    {**data, "role": role},
                )
                result = self._call_model(
                    prompt=prompt,
                    config=config,
                    instructions=instructions,
                    mock_prefix=f"Resposta simulada de {role}",
                    workspace_id=state.get("workspace_id", ""),
                )
                data[output_field] = result
            elif node.type == "http":
                url = render_template(config.get("url", ""), data)
                if not url.startswith(("http://", "https://")):
                    raise ValueError("A URL precisa usar http:// ou https://.")
                method = config.get("method", "GET").upper()
                with httpx.Client(timeout=float(config.get("timeout", 15))) as client:
                    response = client.request(
                        method,
                        url,
                        json=data if method in {"POST", "PUT", "PATCH"} else None,
                    )
                    response.raise_for_status()
                    try:
                        result = response.json()
                    except ValueError:
                        result = response.text
                data["http_response"] = result
            elif node.type == "memory":
                key = config.get("key", "conversation")
                source = config.get("source", "message")
                current = list(data.get(key, []))
                current.append(lookup(data, source))
                data[key] = current
                result = current
            elif node.type == "output":
                field = config.get("field", "response")
                result = lookup(data, field, data)
            else:
                raise ValueError(f"Executor não implementado para {node.type}.")

            event = RunEvent(
                node_id=node.id,
                node_name=node.name,
                status="success",
                output=result,
                duration_ms=round((time.perf_counter() - started) * 1000),
            ).model_dump()
            update: dict[str, Any] = {
                "data": data,
                "results": {node.id: result},
                "events": [event],
            }
            if node.type == "output":
                update["output"] = {"value": result}
            return update
        except Exception as exc:
            event = RunEvent(
                node_id=node.id,
                node_name=node.name,
                status="error",
                output=str(exc),
                duration_ms=round((time.perf_counter() - started) * 1000),
            ).model_dump()
            raise RuntimeError(json.dumps(event, ensure_ascii=False)) from exc

    def compile(self, workflow: Workflow, entry_node_id: str | None = None):
        validate_workflow(workflow)
        if entry_node_id and entry_node_id not in {node.id for node in workflow.nodes}:
            raise WorkflowValidationError("O nó de entrada solicitado não existe.")
        graph = StateGraph(FlowState)
        nodes = {node.id: node for node in workflow.nodes}
        inbound = {node.id: 0 for node in workflow.nodes}
        outgoing: dict[str, list[Any]] = defaultdict(list)
        for edge in workflow.edges:
            inbound[edge.target] += 1
            outgoing[edge.source].append(edge)

        for node in workflow.nodes:
            graph.add_node(node.id, lambda state, current=node: self._execute_node(current, state))
        if entry_node_id:
            graph.add_edge(START, entry_node_id)
        else:
            for node_id, count in inbound.items():
                if count == 0:
                    graph.add_edge(START, node_id)

        for source, edges in outgoing.items():
            source_node = nodes[source]
            if source_node.type == "condition":
                routes = {edge.source_handle: edge.target for edge in edges}
                if "true" in routes or "false" in routes:
                    graph.add_conditional_edges(
                        source,
                        lambda state, node_id=source: (
                            "true" if state["data"].get(f"_condition_{node_id}") else "false"
                        ),
                        {key: value for key, value in routes.items() if key in {"true", "false"}},
                    )
                    continue
            for edge in edges:
                graph.add_edge(edge.source, edge.target)
        for node in workflow.nodes:
            if node.id not in outgoing:
                graph.add_edge(node.id, END)
        return graph.compile()

    def run(
        self,
        workflow: Workflow,
        request: RunRequest,
        entry_node_id: str | None = None,
        workspace_id: str = "",
    ) -> RunResult:
        started_at = utc_now()
        try:
            compiled = self.compile(workflow, entry_node_id=entry_node_id)
            state = compiled.invoke(
                {
                    "data": request.input,
                    "results": {},
                    "events": [],
                    "output": {},
                    "session_id": request.session_id,
                    "workspace_id": workspace_id,
                }
            )
            output = state.get("output", {}).get("value")
            if output is None:
                output = state.get("data")
            return RunResult(
                workflow_id=workflow.id,
                status="success",
                input=request.input,
                output=output,
                events=[RunEvent.model_validate(item) for item in state.get("events", [])],
                started_at=started_at,
                finished_at=utc_now(),
            )
        except Exception as exc:
            message = str(exc)
            events: list[RunEvent] = []
            try:
                decoded = json.loads(message)
                if isinstance(decoded, dict) and "node_id" in decoded:
                    events.append(RunEvent.model_validate(decoded))
                    message = str(decoded.get("output"))
            except (json.JSONDecodeError, TypeError):
                pass
            return RunResult(
                workflow_id=workflow.id,
                status="error",
                input=request.input,
                events=events,
                error=message,
                started_at=started_at,
                finished_at=utc_now(),
            )
