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
from .databases import DATABASE_NODE_TYPES
from .mcp import MCPRuntime
from .media import extract_video_frames, process_image, read_document
from .models import Node, RunEvent, RunRequest, RunResult, Workflow, utc_now
from .vectors import chunk_text, documents_from_value, embed_text


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**left, **right}


class FlowState(TypedDict):
    data: Annotated[dict[str, Any], merge_dicts]
    results: Annotated[dict[str, Any], merge_dicts]
    events: Annotated[list[dict[str, Any]], operator.add]
    output: Annotated[dict[str, Any], merge_dicts]
    session_id: str
    workspace_id: str
    workflow_id: str


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
    nodes_by_id = {node.id: node for node in workflow.nodes}
    node_types = {node.id: node.type for node in workflow.nodes}
    for node in workflow.nodes:
        if node.type not in CATALOG_BY_TYPE:
            raise WorkflowValidationError(f"Tipo de nó desconhecido: {node.type}")
        vector_node_id = node.config.get("vector_db_node_id")
        if vector_node_id and node_types.get(str(vector_node_id)) != "vector_database":
            raise WorkflowValidationError(
                f"“{node.name}” referencia um Banco de Vetores inexistente."
            )
    for edge in workflow.edges:
        if edge.source not in known or edge.target not in known:
            raise WorkflowValidationError(f"Conexão {edge.id} referencia um nó inexistente.")
        if edge.source == edge.target:
            raise WorkflowValidationError("Um nó não pode conectar a si mesmo.")
        source_meta = CATALOG_BY_TYPE[node_types[edge.source]]
        target_meta = CATALOG_BY_TYPE[node_types[edge.target]]
        source_ports = source_meta.get("outputs") or [
            {
                "id": handle,
                "kind": "flow",
            }
            for handle in source_meta.get("handles", ["default"])
        ]
        target_ports = target_meta.get("inputs")
        if target_ports is None:
            target_ports = [{"id": "input", "kind": "flow"}]
        source_port = next(
            (port for port in source_ports if port["id"] == edge.source_handle),
            None,
        )
        target_port = next(
            (port for port in target_ports if port["id"] == edge.target_handle),
            None,
        )
        if not source_port or not target_port:
            raise WorkflowValidationError(
                f"A conexão entre “{nodes_by_id[edge.source].name}” e "
                f"“{nodes_by_id[edge.target].name}” usa uma alça inexistente."
            )
        if source_port.get("kind", "flow") != target_port.get("kind", "flow"):
            raise WorkflowValidationError(
                f"As alças de “{nodes_by_id[edge.source].name}” e "
                f"“{nodes_by_id[edge.target].name}” são incompatíveis."
            )
        source_data_type = source_port.get("data_type", "any")
        target_data_type = target_port.get("data_type", "any")
        if (
            source_port.get("kind", "flow") == "flow"
            and source_data_type != "any"
            and target_data_type != "any"
            and source_data_type != target_data_type
        ):
            raise WorkflowValidationError(
                f"“{nodes_by_id[edge.source].name}” entrega {source_data_type}, "
                f"mas “{nodes_by_id[edge.target].name}” espera {target_data_type}."
            )
    incoming_ports: dict[tuple[str, str], int] = defaultdict(int)
    for edge in workflow.edges:
        key = (edge.target, edge.target_handle)
        incoming_ports[key] += 1
        target_meta = CATALOG_BY_TYPE[node_types[edge.target]]
        target_ports = target_meta.get("inputs")
        if target_ports is None:
            continue
        target_port = next(
            port for port in target_ports if port["id"] == edge.target_handle
        )
        if incoming_ports[key] > 1 and not target_port.get("multiple", False):
            raise WorkflowValidationError(
                f"A alça “{target_port.get('label', edge.target_handle)}” de "
                f"“{nodes_by_id[edge.target].name}” aceita apenas uma conexão."
            )
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
        source_meta = CATALOG_BY_TYPE[node_types[edge.source]]
        source_ports = source_meta.get("outputs") or [
            {"id": handle, "kind": "flow"}
            for handle in source_meta.get("handles", ["default"])
        ]
        source_port = next(
            port for port in source_ports if port["id"] == edge.source_handle
        )
        if source_port.get("kind", "flow") != "flow":
            continue
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
    def __init__(
        self,
        provider_runtime=None,
        vector_store=None,
        mcp_runtime=None,
        database_runtime=None,
    ):
        self.provider_runtime = provider_runtime
        self.vector_store = vector_store
        self.mcp_runtime = mcp_runtime or MCPRuntime()
        self.database_runtime = database_runtime

    @staticmethod
    def _incoming_result(node: Node, state: FlowState) -> tuple[Any, bool]:
        results = state.get("results", {})
        for node_id in reversed(node.config.get("_incoming_node_ids", [])):
            if node_id in results:
                return results[node_id], True
        return None, False

    @classmethod
    def _node_input(
        cls,
        node: Node,
        state: FlowState,
        data: dict[str, Any],
        field: str,
    ) -> tuple[Any, bool]:
        incoming, connected = cls._incoming_result(node, state)
        if connected and isinstance(incoming, dict):
            nested = lookup(incoming, field, None)
            if nested is not None:
                return nested, True
        if connected:
            return incoming, True
        return lookup(data, field, None), False

    def _search_vector_database(
        self,
        *,
        state: FlowState,
        node_id: str,
        query: str,
        top_k: int,
        min_score: float,
    ) -> list[dict[str, Any]]:
        if not self.vector_store:
            raise RuntimeError("O armazenamento vetorial não está configurado.")
        if not node_id:
            raise ValueError("Selecione um nó de Banco de Vetores.")
        return self.vector_store.search_vectors(
            workspace_id=state.get("workspace_id", ""),
            workflow_id=state.get("workflow_id", ""),
            node_id=node_id,
            query_embedding=embed_text(query),
            limit=top_k,
            min_score=min_score,
        )

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
            elif node.type == "text_input":
                input_key = str(config.get("input_key") or "text")
                result = lookup(data, input_key, data.get("message"))
                if result is None:
                    raise ValueError("Informe o texto de entrada no playground.")
                result = str(result)
                data[input_key] = result
                data["text"] = result
                data["message"] = result
            elif node.type == "image_input":
                input_key = str(config.get("input_key") or "image")
                result = lookup(data, input_key, None)
                if result is None:
                    raise ValueError("Selecione uma imagem no playground.")
                data[input_key] = result
                data["image"] = result
            elif node.type == "video_input":
                input_key = str(config.get("input_key") or "video")
                result = lookup(data, input_key, None)
                if result is None:
                    raise ValueError("Selecione um vídeo no playground.")
                data[input_key] = result
                data["video"] = result
            elif node.type == "audio_input":
                input_key = str(config.get("input_key") or "audio")
                result = lookup(data, input_key, None)
                if result is None:
                    raise ValueError("Selecione um áudio no playground.")
                data[input_key] = result
                data["audio"] = result
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
            elif node.type == "file":
                input_field = config.get("input_field", "file")
                output_field = config.get("output_field", "document_text")
                asset, _ = self._node_input(
                    node, state, data, input_field
                )
                if asset is None:
                    raise ValueError(f"O campo de arquivo “{input_field}” não foi informado.")
                result = read_document(asset, config)
                data[output_field] = result["text"]
                data[f"{output_field}_metadata"] = result["metadata"]
            elif node.type == "image":
                input_field = config.get("input_field", "image")
                output_field = config.get("output_field", "processed_image")
                asset, _ = self._node_input(
                    node, state, data, input_field
                )
                if asset is None:
                    raise ValueError(f"O campo de imagem “{input_field}” não foi informado.")
                result = process_image(asset, config)
                data[output_field] = result
            elif node.type == "video_frames":
                input_field = config.get("input_field", "video")
                output_field = config.get("output_field", "frames")
                asset, _ = self._node_input(
                    node, state, data, input_field
                )
                if asset is None:
                    raise ValueError(f"O campo de vídeo “{input_field}” não foi informado.")
                result = extract_video_frames(asset, config)
                data[output_field] = result["frames"]
                data[f"{output_field}_metadata"] = result["metadata"]
            elif node.type == "local_model":
                local_runtime = getattr(self.provider_runtime, "local_runtime", None)
                if not local_runtime:
                    raise RuntimeError("O runtime de modelos locais não está configurado.")
                model_id = str(config.get("model_id") or "")
                if not model_id:
                    raise ValueError("Selecione um modelo local instalado.")
                input_field = str(config.get("input_field") or "prompt")
                output_field = str(config.get("output_field") or "local_output")
                value, connected = self._node_input(node, state, data, input_field)
                if value is None and not connected:
                    value = data.get("prompt", data.get("message"))
                if value is None:
                    raise ValueError(f"O campo de entrada “{input_field}” não foi informado.")
                parameters = config.get("parameters") or {}
                if isinstance(parameters, str):
                    try:
                        parameters = json.loads(parameters)
                    except json.JSONDecodeError as exc:
                        raise ValueError("Os parâmetros de inferência precisam ser JSON válido.") from exc
                if not isinstance(parameters, dict):
                    raise ValueError("Os parâmetros de inferência precisam ser um objeto JSON.")
                result = local_runtime.infer(
                    model_id=model_id,
                    workspace_id=state.get("workspace_id", ""),
                    value=value,
                    parameters=parameters,
                )
                data[output_field] = result
            elif node.type == "vector_database":
                if not self.vector_store:
                    raise RuntimeError("O armazenamento vetorial não está configurado.")
                input_field = config.get("input_field", "document_text")
                output_field = config.get("output_field", "vector_database")
                value, _ = self._node_input(
                    node, state, data, input_field
                )
                if value is None:
                    raise ValueError(
                        f"O campo de conteúdo “{input_field}” não foi informado."
                    )
                configured_metadata = lookup(
                    data, config.get("metadata_field", ""), {}
                )
                chunks: list[dict[str, Any]] = []
                for document_index, document in enumerate(documents_from_value(value)):
                    metadata = {
                        **(
                            configured_metadata
                            if isinstance(configured_metadata, dict)
                            else {}
                        ),
                        **document["metadata"],
                        "document_index": document_index,
                    }
                    for chunk_index, content in enumerate(
                        chunk_text(
                            document["text"],
                            int(config.get("chunk_size", 900)),
                            int(config.get("chunk_overlap", 120)),
                        )
                    ):
                        chunks.append(
                            {
                                "content": content,
                                "embedding": embed_text(content),
                                "metadata": {
                                    **metadata,
                                    "chunk_index": chunk_index,
                                },
                            }
                        )
                if not chunks:
                    raise ValueError("O conteúdo recebido não possui texto para indexar.")
                result = self.vector_store.ingest_vectors(
                    workspace_id=state.get("workspace_id", ""),
                    workflow_id=state.get("workflow_id", ""),
                    node_id=node.id,
                    name=node.name,
                    chunks=chunks,
                    replace=config.get("write_mode", "append") == "replace",
                )
                data[output_field] = result
                data["_last_vector_database_node_id"] = node.id
            elif node.type == "rag":
                query_field = config.get("query_field", "message")
                query = str(
                    lookup(
                        data,
                        query_field,
                        data.get("prompt") or data.get("message") or "",
                    )
                ).strip()
                if not query:
                    raise ValueError(
                        f"O campo de consulta “{query_field}” não foi informado."
                    )
                vector_node_id = (
                    config.get("vector_db_node_id")
                    or config.get("_linked_vector_db_node_id")
                    or data.get("_last_vector_database_node_id")
                )
                matches = self._search_vector_database(
                    state=state,
                    node_id=str(vector_node_id or ""),
                    query=query,
                    top_k=int(config.get("top_k", 5)),
                    min_score=float(config.get("min_score", 0)),
                )
                context_field = config.get("context_field", "rag_context")
                matches_field = config.get("matches_field", "rag_matches")
                separator = config.get("separator", "\n\n---\n\n")
                context = separator.join(match["content"] for match in matches)
                result = {
                    "query": query,
                    "vector_db_node_id": vector_node_id,
                    "context": context,
                    "matches": matches,
                }
                data[context_field] = context
                data[matches_field] = matches
            elif node.type == "mcp_server":
                tools = self.mcp_runtime.list_tools(config)
                result = {
                    "server": node.name,
                    "url": config.get("url"),
                    "tools": tools,
                }
                data[config.get("output_field", "mcp_tools")] = result
            elif node.type in DATABASE_NODE_TYPES:
                if not self.database_runtime:
                    raise RuntimeError(
                        "O gerenciamento de bancos de dados não está configurado."
                    )
                result = self.database_runtime.execute_node(
                    config=config,
                    workspace_id=state.get("workspace_id", ""),
                    data=data,
                    render=render_template,
                )
                data[config.get("output_field", "database_result")] = result
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
                incoming, connected = self._node_input(
                    node, state, data, input_field
                )
                prompt = str(
                    incoming
                    if connected
                    else lookup(
                        data,
                        input_field,
                        data.get("prompt")
                        or data.get("response")
                        or data.get("message")
                        or json.dumps(data),
                    )
                )
                vector_node_id = config.get("vector_db_node_id")
                collected_matches: list[dict[str, Any]] = []
                if vector_node_id:
                    collected_matches.extend(self._search_vector_database(
                        state=state,
                        node_id=str(vector_node_id),
                        query=prompt,
                        top_k=int(config.get("rag_top_k", 5)),
                        min_score=float(config.get("rag_min_score", 0)),
                    ))
                tool_results: list[dict[str, Any]] = []
                for tool_node in config.get("_attached_tools", []):
                    tool_config = dict(tool_node.get("config") or {})
                    if tool_node.get("type") == "rag":
                        linked_database = (
                            tool_config.get("_linked_vector_db_node_id")
                            or tool_config.get("vector_db_node_id")
                        )
                        collected_matches.extend(
                            self._search_vector_database(
                                state=state,
                                node_id=str(linked_database or ""),
                                query=prompt,
                                top_k=int(tool_config.get("top_k", 5)),
                                min_score=float(tool_config.get("min_score", 0)),
                            )
                        )
                    elif tool_node.get("type") == "mcp_server":
                        tool_config["_node_name"] = tool_node.get("name")
                        called = self.mcp_runtime.call_for_agent(
                            tool_config, prompt, data
                        )
                        if called:
                            tool_results.append(called)
                    elif tool_node.get("type") in DATABASE_NODE_TYPES:
                        if not self.database_runtime:
                            raise RuntimeError(
                                "O gerenciamento de bancos de dados não está configurado."
                            )
                        tool_results.append(
                            self.database_runtime.call_for_agent(
                                tool_config,
                                prompt,
                                data,
                                state.get("workspace_id", ""),
                                render_template,
                            )
                        )
                if collected_matches:
                    unique_matches = {
                        match["id"]: match for match in collected_matches
                    }
                    matches = sorted(
                        unique_matches.values(),
                        key=lambda match: match["score"],
                        reverse=True,
                    )
                    data["rag_matches"] = matches
                    data["rag_context"] = "\n\n---\n\n".join(
                        match["content"] for match in matches
                    )
                if tool_results:
                    data["tool_results"] = tool_results
                if data.get("rag_context"):
                    prompt = (
                        f"{prompt}\n\nContexto recuperado da base de conhecimento:\n"
                        f"{data['rag_context']}"
                    )
                if tool_results:
                    prompt = (
                        f"{prompt}\n\nResultados das ferramentas conectadas:\n"
                        f"{json.dumps(tool_results, ensure_ascii=False)}"
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
                incoming, connected = self._incoming_result(node, state)
                configured = lookup(data, field, None)
                result = (
                    configured
                    if configured is not None
                    else incoming
                    if connected
                    else data
                )
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
        nodes = {node.id: node.model_copy(deep=True) for node in workflow.nodes}
        node_types = {node.id: node.type for node in workflow.nodes}
        flow_edges = []
        resource_sources: set[str] = set()
        flow_incident: set[str] = set()
        for edge in workflow.edges:
            meta = CATALOG_BY_TYPE[node_types[edge.source]]
            ports = meta.get("outputs") or [
                {"id": handle, "kind": "flow"}
                for handle in meta.get("handles", ["default"])
            ]
            port = next(item for item in ports if item["id"] == edge.source_handle)
            if port.get("kind", "flow") == "flow":
                flow_edges.append(edge)
                flow_incident.update((edge.source, edge.target))
            else:
                resource_sources.add(edge.source)

        # Resolve resource wiring statically. Resource edges configure capabilities;
        # they do not impose execution order on the LangGraph.
        for agent in (node for node in nodes.values() if node.type == "agent"):
            attached = []
            for edge in workflow.edges:
                if edge.target == agent.id and edge.target_handle == "tools":
                    tool = nodes[edge.source].model_copy(deep=True)
                    if tool.type == "rag":
                        database_edge = next(
                            (
                                candidate
                                for candidate in workflow.edges
                                if candidate.target == tool.id
                                and candidate.target_handle == "database"
                            ),
                            None,
                        )
                        if database_edge:
                            tool.config["_linked_vector_db_node_id"] = (
                                database_edge.source
                            )
                    attached.append(tool.model_dump())
            agent.config["_attached_tools"] = attached

        for rag in (node for node in nodes.values() if node.type == "rag"):
            database_edge = next(
                (
                    edge
                    for edge in workflow.edges
                    if edge.target == rag.id and edge.target_handle == "database"
                ),
                None,
            )
            if database_edge:
                rag.config["_linked_vector_db_node_id"] = database_edge.source

        passive_nodes = resource_sources - flow_incident
        active_nodes = {
            node_id: node for node_id, node in nodes.items()
            if node_id not in passive_nodes
        }
        for node in active_nodes.values():
            node.config["_incoming_node_ids"] = [
                edge.source
                for edge in flow_edges
                if edge.target == node.id and edge.source in active_nodes
            ]
        inbound = {node_id: 0 for node_id in active_nodes}
        outgoing: dict[str, list[Any]] = defaultdict(list)
        for edge in flow_edges:
            if edge.source not in active_nodes or edge.target not in active_nodes:
                continue
            inbound[edge.target] += 1
            outgoing[edge.source].append(edge)

        for node in active_nodes.values():
            graph.add_node(node.id, lambda state, current=node: self._execute_node(current, state))
        if entry_node_id:
            if entry_node_id not in active_nodes:
                raise WorkflowValidationError(
                    "O nó de entrada solicitado é um recurso passivo."
                )
            graph.add_edge(START, entry_node_id)
        else:
            for node_id, count in inbound.items():
                if count == 0:
                    graph.add_edge(START, node_id)

        for source, edges in outgoing.items():
            source_node = active_nodes[source]
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
        for node in active_nodes.values():
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
                    "workflow_id": workflow.id,
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
