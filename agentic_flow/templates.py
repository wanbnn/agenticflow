from __future__ import annotations

from typing import Any

from .databases import DATABASE_TYPES
from .models import Edge, Node, Position, WorkflowCreate


def _node(
    node_id: str,
    node_type: str,
    name: str,
    x: int,
    y: int,
    config: dict[str, Any],
) -> Node:
    return Node(
        id=node_id,
        type=node_type,
        name=name,
        position=Position(x=x, y=y),
        config=config,
    )


def _workflow(
    name: str,
    description: str,
    nodes: list[Node],
    edges: list[Edge] | None = None,
) -> WorkflowCreate:
    return WorkflowCreate(
        name=name,
        description=description,
        nodes=nodes,
        edges=edges
        if edges is not None
        else [
            Edge(
                id=f"edge-{index}",
                source=nodes[index].id,
                target=nodes[index + 1].id,
            )
            for index in range(len(nodes) - 1)
        ],
    )


def _edge(
    edge_id: str,
    source: str,
    target: str,
    source_handle: str = "default",
    target_handle: str = "input",
) -> Edge:
    return Edge(
        id=edge_id,
        source=source,
        target=target,
        source_handle=source_handle,
        target_handle=target_handle,
    )


WORKFLOW_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "document-summary",
        "name": "Resumir documento com IA",
        "description": "Extrai texto de PDF, DOCX, TXT ou Markdown e produz um resumo executivo.",
        "category": "Documentos",
        "icon": "DOC",
        "color": "#14b8a6",
        "featured": True,
        "tags": ["PDF", "DOCX", "IA"],
        "workflow": _workflow(
            "Resumo inteligente de documento",
            "Extrai o conteúdo de um documento e gera um resumo executivo.",
            [
                _node("input", "input", "Receber documento", 80, 220, {"field": "file"}),
                _node(
                    "file",
                    "file",
                    "Extrair conteúdo",
                    360,
                    220,
                    {
                        "input_field": "file",
                        "output_field": "document_text",
                        "format": "auto",
                        "encoding": "utf-8",
                        "max_characters": 200000,
                    },
                ),
                _node(
                    "prompt",
                    "prompt",
                    "Preparar resumo",
                    640,
                    220,
                    {
                        "template": "Resuma o documento abaixo. Destaque decisões, riscos e próximos passos.\n\n{{document_text}}"
                    },
                ),
                _node(
                    "agent",
                    "agent",
                    "Analista de documentos",
                    920,
                    220,
                    {
                        "role": "Analista executivo",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Produza resumos claros, fiéis e estruturados.",
                        "input_field": "prompt",
                        "output_field": "response",
                        "temperature": 0.1,
                    },
                ),
                _node("output", "output", "Resumo final", 1200, 220, {"field": "response"}),
            ],
        ),
    },
    {
        "id": "image-optimizer",
        "name": "Otimizar imagem",
        "description": "Redimensiona e converte PNG, JPEG, WebP, GIF, BMP ou TIFF.",
        "category": "Imagens",
        "icon": "IMG",
        "color": "#0ea5e9",
        "featured": True,
        "tags": ["PNG", "JPEG", "WebP"],
        "workflow": _workflow(
            "Otimização de imagem",
            "Padroniza imagens para publicação e integrações.",
            [
                _node("input", "image_input", "Receber imagem", 140, 230, {"input_key": "image"}),
                _node(
                    "image",
                    "image",
                    "Redimensionar e converter",
                    460,
                    230,
                    {
                        "input_field": "image",
                        "output_field": "processed_image",
                        "operation": "resize",
                        "output_format": "WEBP",
                        "width": 1280,
                        "height": 1280,
                        "quality": 88,
                    },
                ),
                _node(
                    "output",
                    "output",
                    "Imagem otimizada",
                    780,
                    230,
                    {"field": "processed_image"},
                ),
            ],
        ),
    },
    {
        "id": "video-to-frames",
        "name": "Extrair frames de vídeo",
        "description": "Converte vídeos em uma sequência controlada de imagens JPEG ou PNG.",
        "category": "Vídeo",
        "icon": "VID",
        "color": "#6366f1",
        "featured": True,
        "tags": ["MP4", "Frames", "Imagem"],
        "workflow": _workflow(
            "Vídeo para frames",
            "Extrai frames de um vídeo em intervalos configuráveis.",
            [
                _node("input", "video_input", "Receber vídeo", 140, 230, {"input_key": "video"}),
                _node(
                    "video",
                    "video_frames",
                    "Extrair frames",
                    460,
                    230,
                    {
                        "input_field": "video",
                        "output_field": "frames",
                        "interval_seconds": 1,
                        "max_frames": 12,
                        "output_format": "jpeg",
                        "quality": 88,
                    },
                ),
                _node("output", "output", "Frames gerados", 780, 230, {"field": "frames"}),
            ],
        ),
    },
    {
        "id": "webhook-support",
        "name": "Atendimento por webhook",
        "description": "Recebe solicitações externas, processa com um agente e devolve a resposta.",
        "category": "Atendimento",
        "icon": "WH",
        "color": "#f97316",
        "featured": False,
        "tags": ["Webhook", "Agente", "API"],
        "workflow": _workflow(
            "Atendimento inteligente",
            "Atendimento automatizado acionado por webhook.",
            [
                _node(
                    "webhook",
                    "webhook",
                    "Nova solicitação",
                    120,
                    220,
                    {"webhook_id": "", "response_mode": "workflow_result"},
                ),
                _node(
                    "agent",
                    "agent",
                    "Agente de atendimento",
                    440,
                    220,
                    {
                        "role": "Especialista em atendimento",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Responda com clareza, cordialidade e objetividade.",
                        "input_field": "message",
                        "output_field": "response",
                        "temperature": 0.2,
                    },
                ),
                _node("output", "output", "Enviar resposta", 760, 220, {"field": "response"}),
            ],
        ),
    },
    {
        "id": "research-review",
        "name": "Pesquisa com revisão",
        "description": "Dois agentes pesquisam e revisam uma resposta antes da entrega.",
        "category": "Produtividade",
        "icon": "AI",
        "color": "#ec4899",
        "featured": False,
        "tags": ["Multiagente", "Revisão", "Pesquisa"],
        "workflow": _workflow(
            "Pesquisa com revisão",
            "Pipeline multiagente para respostas pesquisadas e revisadas.",
            [
                _node(
                    "input",
                    "text_input",
                    "Nova pesquisa",
                    80,
                    220,
                    {
                        "input_key": "text",
                        "placeholder": "Qual tema devemos pesquisar?",
                    },
                ),
                _node(
                    "prompt",
                    "prompt",
                    "Preparar contexto",
                    360,
                    220,
                    {"template": "Pesquise e responda com evidências:\n\n{{message}}"},
                ),
                _node(
                    "researcher",
                    "agent",
                    "Agente pesquisador",
                    640,
                    220,
                    {
                        "role": "Pesquisador",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Investigue o tema e estruture os achados.",
                        "input_field": "prompt",
                        "output_field": "research",
                        "temperature": 0.2,
                    },
                ),
                _node(
                    "reviewer",
                    "agent",
                    "Agente revisor",
                    920,
                    220,
                    {
                        "role": "Revisor",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Revise os achados e produza uma resposta final.",
                        "input_field": "research",
                        "output_field": "response",
                        "temperature": 0.1,
                    },
                ),
                _node("output", "output", "Resposta final", 1200, 220, {"field": "response"}),
            ],
        ),
    },
    {
        "id": "document-rag-assistant",
        "name": "Conversar com documento usando RAG",
        "description": "Extrai um documento, indexa em uma base vetorial isolada e responde perguntas com contexto recuperado.",
        "category": "Conhecimento",
        "icon": "RAG",
        "color": "#10b981",
        "featured": True,
        "tags": ["RAG", "Banco de Vetores", "PDF", "Agente"],
        "setup_hint": "No playground avançado, anexe o documento em file e informe a pergunta em message.",
        "workflow": _workflow(
            "Assistente RAG para documentos",
            "Ingestão e consulta de documentos com Banco de Vetores e RAG.",
            [
                _node("input", "input", "Documento e pergunta", 60, 240, {"field": "message"}),
                _node(
                    "file",
                    "file",
                    "Extrair documento",
                    320,
                    120,
                    {
                        "input_field": "file",
                        "output_field": "document_text",
                        "format": "auto",
                        "encoding": "utf-8",
                        "max_characters": 200000,
                    },
                ),
                _node(
                    "vector",
                    "vector_database",
                    "Base do documento",
                    580,
                    120,
                    {
                        "input_field": "document_text",
                        "output_field": "vector_database",
                        "metadata_field": "document_text_metadata",
                        "chunk_size": 900,
                        "chunk_overlap": 120,
                        "write_mode": "append",
                    },
                ),
                _node(
                    "rag",
                    "rag",
                    "Consultar documento",
                    580,
                    360,
                    {
                        "query_field": "message",
                        "context_field": "rag_context",
                        "matches_field": "rag_matches",
                        "top_k": 5,
                        "min_score": 0,
                        "separator": "\n\n---\n\n",
                    },
                ),
                _node(
                    "prompt",
                    "prompt",
                    "Preparar pergunta",
                    840,
                    120,
                    {
                        "template": "Responda à pergunta usando somente o documento indexado.\n\nPergunta: {{message}}"
                    },
                ),
                _node(
                    "agent",
                    "agent",
                    "Especialista no documento",
                    1100,
                    220,
                    {
                        "role": "Especialista no documento",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Use o contexto RAG, seja fiel ao documento e sinalize quando a informação não estiver disponível.",
                        "input_field": "prompt",
                        "output_field": "response",
                        "rag_top_k": 5,
                        "rag_min_score": 0,
                        "temperature": 0.1,
                    },
                ),
                _node("output", "output", "Resposta fundamentada", 1360, 220, {"field": "response"}),
            ],
            [
                _edge("e1", "input", "file"),
                _edge("e2", "file", "vector"),
                _edge("e3", "vector", "prompt"),
                _edge("e4", "prompt", "agent"),
                _edge("e5", "agent", "output"),
                _edge("e6", "vector", "rag", "database", "database"),
                _edge("e7", "rag", "agent", "tool", "tools"),
            ],
        ),
    },
    {
        "id": "vector-knowledge-ingestion",
        "name": "Indexar documentos em Banco de Vetores",
        "description": "Pipeline dedicado para extrair, segmentar, vetorizar e armazenar documentos sem duplicar trechos.",
        "category": "Conhecimento",
        "icon": "DB",
        "color": "#22c55e",
        "featured": False,
        "tags": ["Vector DB", "Ingestão", "Documentos"],
        "setup_hint": "Anexe o documento no campo file da entrada avançada.",
        "workflow": _workflow(
            "Ingestão de base de conhecimento",
            "Prepara documentos e persiste seus trechos em uma coleção vetorial exclusiva.",
            [
                _node("input", "input", "Receber arquivo", 100, 220, {"field": "file"}),
                _node(
                    "file",
                    "file",
                    "Extrair texto",
                    380,
                    220,
                    {
                        "input_field": "file",
                        "output_field": "document_text",
                        "format": "auto",
                        "encoding": "utf-8",
                        "max_characters": 200000,
                    },
                ),
                _node(
                    "vector",
                    "vector_database",
                    "Base de conhecimento",
                    660,
                    220,
                    {
                        "input_field": "document_text",
                        "output_field": "vector_database",
                        "metadata_field": "document_text_metadata",
                        "chunk_size": 900,
                        "chunk_overlap": 120,
                        "write_mode": "append",
                    },
                ),
                _node("output", "output", "Relatório de indexação", 940, 220, {"field": "vector_database"}),
            ],
        ),
    },
    {
        "id": "mcp-tool-agent",
        "name": "Agente com ferramentas MCP",
        "description": "Conecta um agente a um MCP Server, descobre ferramentas e utiliza a mais adequada para cada solicitação.",
        "category": "Ferramentas",
        "icon": "MCP",
        "color": "#f97316",
        "featured": True,
        "tags": ["MCP", "Tools", "Agente"],
        "setup_hint": "Configure a URL Streamable HTTP no nó MCP Server antes de executar.",
        "workflow": _workflow(
            "Agente operacional com MCP",
            "Agente equipado com ferramentas remotas via Model Context Protocol.",
            [
                _node(
                    "input",
                    "text_input",
                    "Solicitação",
                    100,
                    180,
                    {"input_key": "text", "placeholder": "O que o agente deve fazer?"},
                ),
                _node(
                    "mcp",
                    "mcp_server",
                    "Servidor de ferramentas",
                    380,
                    380,
                    {
                        "url": "http://localhost:8000/mcp",
                        "tool_name": "",
                        "arguments": "",
                        "timeout": 30,
                    },
                ),
                _node(
                    "agent",
                    "agent",
                    "Agente operacional",
                    660,
                    180,
                    {
                        "role": "Agente operacional",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Use as ferramentas MCP disponíveis quando ajudarem a concluir a solicitação.",
                        "input_field": "text",
                        "output_field": "response",
                        "temperature": 0.1,
                    },
                ),
                _node("output", "output", "Resultado", 940, 180, {"field": "response"}),
            ],
            [
                _edge("e1", "input", "agent"),
                _edge("e2", "agent", "output"),
                _edge("e3", "mcp", "agent", "tool", "tools"),
            ],
        ),
    },
    {
        "id": "rag-mcp-operations",
        "name": "Agente com RAG e MCP",
        "description": "Combina conhecimento privado de documentos com ferramentas MCP para investigar e executar ações.",
        "category": "Automação avançada",
        "icon": "OPS",
        "color": "#a855f7",
        "featured": True,
        "tags": ["RAG", "MCP", "Vector DB", "Tools"],
        "setup_hint": "Anexe file e message na entrada avançada e configure a URL do MCP Server.",
        "workflow": _workflow(
            "Operações com RAG e MCP",
            "Agente que consulta conhecimento interno e usa ferramentas externas.",
            [
                _node("input", "input", "Contexto e solicitação", 60, 220, {"field": "message"}),
                _node(
                    "file",
                    "file",
                    "Ler conhecimento",
                    300,
                    80,
                    {
                        "input_field": "file",
                        "output_field": "document_text",
                        "format": "auto",
                        "encoding": "utf-8",
                        "max_characters": 200000,
                    },
                ),
                _node(
                    "vector",
                    "vector_database",
                    "Conhecimento interno",
                    540,
                    80,
                    {
                        "input_field": "document_text",
                        "output_field": "vector_database",
                        "metadata_field": "document_text_metadata",
                        "chunk_size": 900,
                        "chunk_overlap": 120,
                        "write_mode": "append",
                    },
                ),
                _node(
                    "rag",
                    "rag",
                    "Busca interna",
                    540,
                    300,
                    {
                        "query_field": "message",
                        "context_field": "rag_context",
                        "matches_field": "rag_matches",
                        "top_k": 5,
                        "min_score": 0,
                        "separator": "\n\n---\n\n",
                    },
                ),
                _node(
                    "mcp",
                    "mcp_server",
                    "Ferramentas operacionais",
                    780,
                    420,
                    {
                        "url": "http://localhost:8000/mcp",
                        "tool_name": "",
                        "arguments": "",
                        "timeout": 30,
                    },
                ),
                _node(
                    "prompt",
                    "prompt",
                    "Preparar tarefa",
                    780,
                    80,
                    {"template": "Conclua a solicitação a seguir com base no conhecimento interno e nas ferramentas disponíveis:\n\n{{message}}"},
                ),
                _node(
                    "agent",
                    "agent",
                    "Agente de operações",
                    1040,
                    220,
                    {
                        "role": "Agente de operações",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Consulte o RAG antes de agir e use MCP somente quando necessário.",
                        "input_field": "prompt",
                        "output_field": "response",
                        "temperature": 0.1,
                    },
                ),
                _node("output", "output", "Resultado operacional", 1300, 220, {"field": "response"}),
            ],
            [
                _edge("e1", "input", "file"),
                _edge("e2", "file", "vector"),
                _edge("e3", "vector", "prompt"),
                _edge("e4", "prompt", "agent"),
                _edge("e5", "agent", "output"),
                _edge("e6", "vector", "rag", "database", "database"),
                _edge("e7", "rag", "agent", "tool", "tools"),
                _edge("e8", "mcp", "agent", "tool", "tools"),
            ],
        ),
    },
    {
        "id": "http-api-enrichment",
        "name": "Enriquecer dados com API HTTP",
        "description": "Consulta uma API REST, combina a resposta com a solicitação e entrega uma análise por IA.",
        "category": "Integrações",
        "icon": "HTTP",
        "color": "#06b6d4",
        "featured": False,
        "tags": ["HTTP", "REST", "API", "IA"],
        "setup_hint": "Troque a URL de demonstração pela API que deseja integrar.",
        "workflow": _workflow(
            "Enriquecimento por API",
            "Consulta dados externos e usa um agente para interpretá-los.",
            [
                _node(
                    "input",
                    "text_input",
                    "Termo de consulta",
                    80,
                    220,
                    {"input_key": "text", "placeholder": "O que deseja consultar?"},
                ),
                _node(
                    "http",
                    "http",
                    "Consultar API",
                    360,
                    220,
                    {
                        "method": "GET",
                        "url": "https://httpbin.org/anything?query={{message}}",
                        "timeout": 15,
                    },
                ),
                _node(
                    "prompt",
                    "prompt",
                    "Combinar dados",
                    640,
                    220,
                    {
                        "template": "Solicitação original: {{message}}\n\nDados retornados pela API: {{http_response}}\n\nAnalise e responda objetivamente."
                    },
                ),
                _node(
                    "agent",
                    "agent",
                    "Analista de dados",
                    920,
                    220,
                    {
                        "role": "Analista de dados",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Interprete os dados externos sem inventar informações.",
                        "input_field": "prompt",
                        "output_field": "response",
                        "temperature": 0.1,
                    },
                ),
                _node("output", "output", "Análise enriquecida", 1200, 220, {"field": "response"}),
            ],
        ),
    },
    {
        "id": "webhook-http-relay",
        "name": "Webhook para API externa",
        "description": "Recebe um evento por webhook, encaminha o JSON para uma API REST e devolve a resposta.",
        "category": "Integrações",
        "icon": "API",
        "color": "#f97316",
        "featured": False,
        "tags": ["Webhook", "HTTP", "POST", "Integração"],
        "setup_hint": "Substitua a URL de demonstração pelo endpoint de destino.",
        "workflow": _workflow(
            "Relay de webhook para API",
            "Encaminha eventos externos para outro sistema via HTTP POST.",
            [
                _node(
                    "webhook",
                    "webhook",
                    "Receber evento",
                    120,
                    220,
                    {"webhook_id": "", "response_mode": "workflow_result"},
                ),
                _node(
                    "http",
                    "http",
                    "Enviar para API",
                    440,
                    220,
                    {
                        "method": "POST",
                        "url": "https://httpbin.org/anything",
                        "timeout": 15,
                    },
                ),
                _node("output", "output", "Resposta da API", 760, 220, {"field": "http_response"}),
            ],
        ),
    },
    {
        "id": "memory-context-agent",
        "name": "Agente com memória de contexto",
        "description": "Registra a mensagem no contexto da execução e a entrega estruturada a um agente.",
        "category": "Atendimento",
        "icon": "MEM",
        "color": "#8b5cf6",
        "featured": False,
        "tags": ["Memória", "Contexto", "Agente"],
        "workflow": _workflow(
            "Atendimento com contexto",
            "Organiza o histórico disponível durante a execução antes de responder.",
            [
                _node(
                    "input",
                    "text_input",
                    "Mensagem",
                    80,
                    220,
                    {"input_key": "text", "placeholder": "Digite a mensagem do usuário..."},
                ),
                _node(
                    "memory",
                    "memory",
                    "Registrar contexto",
                    360,
                    220,
                    {"key": "conversation", "source": "message"},
                ),
                _node(
                    "prompt",
                    "prompt",
                    "Preparar conversa",
                    640,
                    220,
                    {
                        "template": "Contexto da conversa: {{conversation}}\n\nMensagem atual: {{message}}"
                    },
                ),
                _node(
                    "agent",
                    "agent",
                    "Agente contextual",
                    920,
                    220,
                    {
                        "role": "Agente de atendimento",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Considere o contexto disponível e responda de forma consistente.",
                        "input_field": "prompt",
                        "output_field": "response",
                        "temperature": 0.2,
                    },
                ),
                _node("output", "output", "Resposta", 1200, 220, {"field": "response"}),
            ],
        ),
    },
    {
        "id": "conditional-priority-triage",
        "name": "Triagem por condição",
        "description": "Classifica uma solicitação por prioridade e encaminha para respostas diferentes.",
        "category": "Lógica",
        "icon": "IF",
        "color": "#f59e0b",
        "featured": False,
        "tags": ["Condição", "Roteamento", "Prioridade"],
        "setup_hint": "Execute com JSON contendo message e priority; use high para o caminho urgente.",
        "workflow": _workflow(
            "Triagem condicional de prioridade",
            "Roteia solicitações urgentes e regulares por caminhos independentes.",
            [
                _node("input", "input", "Nova solicitação", 80, 220, {"field": "message"}),
                _node(
                    "condition",
                    "condition",
                    "É prioridade alta?",
                    360,
                    220,
                    {"field": "priority", "operator": "equals", "value": "high"},
                ),
                _node(
                    "urgent",
                    "transform",
                    "Resposta urgente",
                    660,
                    100,
                    {
                        "target": "response",
                        "template": "URGENTE · Encaminhar imediatamente: {{message}}",
                    },
                ),
                _node(
                    "regular",
                    "transform",
                    "Resposta regular",
                    660,
                    340,
                    {
                        "target": "response",
                        "template": "Solicitação registrada na fila padrão: {{message}}",
                    },
                ),
                _node("urgent-output", "output", "Saída urgente", 960, 100, {"field": "response"}),
                _node("regular-output", "output", "Saída regular", 960, 340, {"field": "response"}),
            ],
            [
                _edge("e1", "input", "condition"),
                _edge("e2", "condition", "urgent", "true"),
                _edge("e3", "condition", "regular", "false"),
                _edge("e4", "urgent", "urgent-output"),
                _edge("e5", "regular", "regular-output"),
            ],
        ),
    },
    {
        "id": "webhook-priority-agent",
        "name": "Webhook com roteamento inteligente",
        "description": "Recebe chamados por webhook e usa condições para separar atendimento urgente e padrão.",
        "category": "Atendimento",
        "icon": "FLOW",
        "color": "#ec4899",
        "featured": False,
        "tags": ["Webhook", "Condição", "Agente", "Atendimento"],
        "setup_hint": "Envie message e urgent no JSON do webhook.",
        "workflow": _workflow(
            "Atendimento roteado por webhook",
            "Direciona chamados recebidos externamente conforme o indicador de urgência.",
            [
                _node(
                    "webhook",
                    "webhook",
                    "Receber chamado",
                    80,
                    220,
                    {"webhook_id": "", "response_mode": "workflow_result"},
                ),
                _node(
                    "condition",
                    "condition",
                    "Chamado urgente?",
                    360,
                    220,
                    {"field": "urgent", "operator": "equals", "value": "true"},
                ),
                _node(
                    "urgent-agent",
                    "agent",
                    "Especialista urgente",
                    660,
                    100,
                    {
                        "role": "Especialista em incidentes críticos",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Priorize contenção, impacto e próximos passos imediatos.",
                        "input_field": "message",
                        "output_field": "response",
                        "temperature": 0.1,
                    },
                ),
                _node(
                    "regular-agent",
                    "agent",
                    "Atendimento padrão",
                    660,
                    340,
                    {
                        "role": "Especialista em atendimento",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Responda com clareza e indique os próximos passos.",
                        "input_field": "message",
                        "output_field": "response",
                        "temperature": 0.2,
                    },
                ),
                _node("urgent-output", "output", "Resposta urgente", 960, 100, {"field": "response"}),
                _node("regular-output", "output", "Resposta padrão", 960, 340, {"field": "response"}),
            ],
            [
                _edge("e1", "webhook", "condition"),
                _edge("e2", "condition", "urgent-agent", "true"),
                _edge("e3", "condition", "regular-agent", "false"),
                _edge("e4", "urgent-agent", "urgent-output"),
                _edge("e5", "regular-agent", "regular-output"),
            ],
        ),
    },
    {
        "id": "direct-llm-content",
        "name": "Geração direta com LLM",
        "description": "Monta um prompt estruturado e chama diretamente um modelo, sem comportamento autônomo de agente.",
        "category": "Produtividade",
        "icon": "LLM",
        "color": "#ec4899",
        "featured": False,
        "tags": ["LLM", "Prompt", "Conteúdo"],
        "workflow": _workflow(
            "Geração de conteúdo com LLM",
            "Fluxo direto e previsível para transformar uma instrução em conteúdo.",
            [
                _node(
                    "input",
                    "text_input",
                    "Instrução",
                    80,
                    220,
                    {
                        "input_key": "text",
                        "placeholder": "Descreva o conteúdo que deseja gerar...",
                    },
                ),
                _node(
                    "prompt",
                    "prompt",
                    "Estruturar prompt",
                    360,
                    220,
                    {
                        "template": "Crie uma resposta clara e estruturada para a solicitação abaixo:\n\n{{message}}"
                    },
                ),
                _node(
                    "llm",
                    "llm",
                    "Gerar conteúdo",
                    640,
                    220,
                    {
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Seja objetivo, correto e organize a resposta em seções quando útil.",
                        "temperature": 0.2,
                    },
                ),
                _node("output", "output", "Conteúdo gerado", 920, 220, {"field": "response"}),
            ],
        ),
    },
]


def _database_agent_template(definition: dict[str, Any]) -> dict[str, Any]:
    database_name = definition["name"]
    node_type = definition["node_type"]
    return {
        "id": f"{definition['type']}-data-analyst",
        "name": f"Analista de dados {database_name}",
        "description": (
            f"Agente conectado ao {database_name} para inspecionar schemas, "
            "executar consultas de leitura e analisar resultados."
        ),
        "category": "Bancos de dados",
        "icon": definition["icon"],
        "color": definition["color"],
        "featured": definition["type"] in {"postgresql", "mysql"},
        "tags": [database_name, "SQL", "Agente"],
        "setup_hint": (
            f"Cadastre uma conexão {database_name} em Configurações > Bancos "
            "e selecione-a no nó antes de executar."
        ),
        "workflow": _workflow(
            f"Analista {database_name}",
            (
                f"Consulta o schema e dados de uma conexão {database_name} "
                "em modo somente leitura."
            ),
            [
                _node(
                    "question",
                    "text_input",
                    "Pergunta ou SELECT",
                    80,
                    220,
                    {
                        "input_key": "text",
                        "placeholder": (
                            "Pergunte sobre o schema ou cole uma consulta SELECT..."
                        ),
                    },
                ),
                _node(
                    "database",
                    node_type,
                    database_name,
                    380,
                    80,
                    {
                        "connection_id": "",
                        "operation": "auto",
                        "query": "",
                        "schema_name": "",
                        "tables": "",
                        "max_rows": 200,
                        "output_field": "database_result",
                    },
                ),
                _node(
                    "agent",
                    "agent",
                    "Analista de dados",
                    650,
                    220,
                    {
                        "role": f"Analista especialista em {database_name}",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": (
                            "Analise apenas os schemas e resultados fornecidos "
                            "pela ferramenta conectada. Nunca proponha comandos "
                            "de escrita ou alteração de estrutura."
                        ),
                        "input_field": "message",
                        "output_field": "response",
                        "temperature": 0.1,
                    },
                ),
                _node(
                    "output",
                    "output",
                    "Análise",
                    940,
                    220,
                    {"field": "response"},
                ),
            ],
            [
                _edge("e1", "question", "agent"),
                _edge("e2", "database", "agent", "tool", "tools"),
                _edge("e3", "agent", "output"),
            ],
        ),
    }


WORKFLOW_TEMPLATES.extend(
    _database_agent_template(definition) for definition in DATABASE_TYPES
)


TEMPLATES_BY_ID = {item["id"]: item for item in WORKFLOW_TEMPLATES}


def template_catalog() -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in template.items()
            if key != "workflow"
        }
        | {
            "node_types": sorted(
                {node.type for node in template["workflow"].nodes}
            ),
            "nodes_count": len(template["workflow"].nodes),
        }
        for template in WORKFLOW_TEMPLATES
    ]


def instantiate_template(template_id: str, name: str | None = None) -> WorkflowCreate:
    template = TEMPLATES_BY_ID.get(template_id)
    if not template:
        raise KeyError(template_id)
    workflow = template["workflow"].model_copy(deep=True)
    if name and name.strip():
        workflow.name = name.strip()
    return workflow
